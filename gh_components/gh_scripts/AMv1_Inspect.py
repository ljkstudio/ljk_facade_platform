# -*- coding: utf-8 -*-
# AMv1 Inspect — 몰드를 눈으로 보고 판단하기 위한 GhPython 컴포넌트
#
# 목적:
#   Phase B(곡면 정렬)의 회전 방식을 숫자가 아니라 형상으로 판단한다.
#   normalized 토글을 껐다 켜면서 몰드가 어떻게 달라지는지 본다.
#
#   normalized = False → 현재 구현 (진단상 기울기를 2배로 키움)
#   normalized = True  → fit 법선을 +Z 반구로 정규화한 뒤 +각도 회전
#
# GhPython 컴포넌트 Inputs (전부 item access, 없으면 기본값):
#   platform_path   str    repo root 경로 (필수)
#   target_srf      Surface/Brep  목표 곡면 (필수)
#   base_plane      Plane  기본 WorldXY
#   width           float  1000
#   length          float  1000
#   spacing         float  200
#   max_height      float  400
#   min_height      float  0
#   pin_radius      float  0 이면 spacing*0.12 자동
#   normalized      bool   False (현재 코드는 사용하지 않음 — 정규화가 본체가 됨)
#   wire_extend     float  강선 오버행, 없으면 250 (실물 관측 200~300)
#   wire_d_main     float  U 굵은 강선 지름, 없으면 12   ← 가정치
#   wire_d_sub      float  V·보조 U 강선 지름, 없으면 6  ← 가정치
#   sub_per_gap     int    굵은 U 사이 보조 U 개수, 없으면 2
#   v_per_gap       int    핀 열 사이 V 강선 개수, 없으면 2
#   sheet_si_t      float  실리콘 시트 두께, 없으면 8    ← 가정치
#   sheet_ht_t      float  내열 시트 두께, 없으면 2      ← 가정치
#   compute         bool   False
#
# Outputs:
#   pins_ok        정상 핀 (Brep)         — 회색 프리뷰 권장
#   pins_clamped   stroke 한계에 걸린 핀   — 빨강 권장
#   pins_ext       확장영역 핀             — 노랑 권장
#   pin_tops       핀 상단 점
#   wires          U방향 굵은 강선 (핀 위, 3차 보간곡선, 양 끝 오버행)
#   wires_sub      U방향 보조 강선 (굵은 것 사이, V 아래로 엮임)
#   wires_v        V방향 강선 (굵은 U 위를 가로지름)
#   sheet_si       실리콘 시트 상면 (= 내열 시트 하면)
#   sheet_ht       내열 시트 상면 = 실제 성형면
#   deck           핀 상단을 잇는 메시 (실제로 성형되는 면)
#   positioned     정렬된 목표 곡면
#   extended       확장된 곡면
#   envelope       stroke 범위 상자 (핀이 움직일 수 있는 공간)
#   deviation      핀 상단과 목표 곡면 사이 거리 (핀별)
#   info           통계 리포트

import sys
import os

import Rhino.Geometry as rg


# ── src 경로 등록 + 모듈 캐시 비우기 ────────────────────────
# Rhino의 Python은 프로세스가 살아 있는 동안 모듈을 캐시한다.
# src/를 고쳐도 반영되지 않으므로 매번 비운다.

_src = os.path.join(platform_path, "adaptive_mold", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_norm = os.path.normcase(os.path.normpath(_src))
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

from adaptive_mold_v1 import run_adaptive_mold


# ── Guid 방어 ───────────────────────────────────────────
# GhPython 입력에 타입 힌트가 걸려 있지 않으면 Rhino 문서 객체가
# 지오메트리가 아니라 Guid로 넘어온다. 그러면 "target_srf is invalid"
# 또는 "expected Plane, got Guid"가 난다. 힌트가 정상이면 이 함수는
# 아무 일도 하지 않는다.

import System
import Rhino


def resolve(x):
    """Guid면 활성 Rhino 문서에서 지오메트리를 찾아 돌려준다."""
    if not isinstance(x, System.Guid):
        return x
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return None
    obj = doc.Objects.FindId(x)
    return obj.Geometry if obj is not None else None


target_srf = resolve(target_srf)
base_plane = resolve(base_plane)


# ── 기본값 ──────────────────────────────────────────────

if base_plane is None:
    base_plane = rg.Plane.WorldXY
if width is None:
    width = 1000.0
if length is None:
    length = 1000.0
if spacing is None:
    spacing = 200.0
if max_height is None:
    max_height = 400.0
if min_height is None:
    min_height = 0.0
if not pin_radius:
    pin_radius = spacing * 0.12
if normalized is None:
    normalized = False

def _default(name, value, positive=False):
    """연결되지 않았거나 아직 파라미터가 없는 입력에 기본값을 넣는다.

    globals().get()을 쓰면 파라미터가 없어도 NameError가 나지 않는다 —
    컴포넌트에 입력을 추가하기 전에도 코드가 돈다.
    """
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


# 강선 오버행 — 액추에이터 영역 밖으로 더 나가는 길이.
# 실물 사진(image/adaptiveMold_image.png)에서 200~300mm로 관측된다.
# 주의: 강선을 따라 잰 길이다. 접선이 기울어져 있으면 수평 돌출은 이보다 짧다.
_default("wire_extend", 250.0, positive=True)

# 강선 지름과 밀도 — **전부 가정치.** 실물 장비 사양이 확정되면 교체할 것.
_default("wire_d_main", 12.0, positive=True)   # U 굵은 강선 (핀 위)
_default("wire_d_sub", 6.0, positive=True)     # V 강선 및 U 보조 강선
_default("sub_per_gap", 2)                     # 굵은 U 사이에 넣을 보조 U 개수
_default("v_per_gap", 2)                       # 핀 열 사이에 넣을 V 강선 개수
_default("sheet_si_t", 8.0, positive=True)     # 실리콘 시트 두께
_default("sheet_ht_t", 2.0, positive=True)     # 내열 시트 두께


pins_ok = []
pins_clamped = []
pins_ext = []
pin_tops = []
wires = []
wires_v = []
wires_sub = []
sheet_si = None
sheet_ht = None
deck = None
positioned = None
extended = None
envelope = None
deviation = []
info = ""


def make_pin(base_pt, normal, height, radius):
    """베이스 점에서 height 만큼 올라간 원기둥 하나."""
    if height <= 1e-9:
        height = 1e-9
    plane = rg.Plane(base_pt, normal)
    circle = rg.Circle(plane, radius)
    cyl = rg.Cylinder(circle, height)
    return cyl.ToBrep(True, True)


def make_deck_mesh(tops, nx, ny):
    """핀 상단을 잇는 쿼드 메시. 실제로 성형되는 면에 해당한다."""
    if len(tops) != nx * ny:
        return None
    mesh = rg.Mesh()
    for p in tops:
        mesh.Vertices.Add(p)
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = a + 1
            c = a + nx + 1
            d = a + nx
            mesh.Faces.AddFace(a, b, c, d)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


# ── 강선 메쉬 · 시트 적층 ─────────────────────────────────
#
# 적층 순서 (아래 → 위):
#   핀 상단 ─ U 굵은 강선(핀 위) ─ V 강선(굵은 U 위를 가로지름)
#            ─ U 보조 강선(V 아래로 엮임, 굵은 U 사이) ─ 실리콘 ─ 내열 시트
#
# 굵은 U와 보조 U는 **상단면이 같다** — 둘 다 V 강선의 밑면에 닿는다.
# 굵은 U는 핀이 받치고, 보조 U는 핀이 없어 V 강선에 엮여 매달린다.
#
# 강선 형상 두 가지 규칙:
#
# 1. **직선 폴리라인이 아니라 3차 보간곡선.** 탄성 스트립은 변형에너지(∫κ²)를
#    최소화하는 형상으로 안정되고 그 해가 자연 3차 스플라인이다. 직선 데크는
#    물리 모델이 아니라 상한선이며 새그를 26배 과대평가한다(J-004 FACT-01).
#
# 2. **오버행은 접선 직선**(`CurveExtensionStyle.Line`). 마지막 핀 바깥은
#    하중도 모멘트도 없는 자유단이라 직선이 된다. 곡률을 이어가는 Smooth
#    연장은 자유단에 모멘트가 남아 있다는 뜻이어서, 끝을 붙잡는 장치가
#    실제로 있을 때만 맞다.

def deck_surface(tops, nx, ny):
    """핀 상단을 지나는 쌍3차 곡면. (u,v)가 어느 인덱스인지 스스로 확인한다.

    `NurbsSurface.CreateThroughPoints(points, uCount, vCount, ...)`의 점 순서
    규약을 이름으로 추측하면 nx != ny일 때 U/V가 뒤바뀐 채로 그려지고,
    그림은 그럴듯하게 나오므로 한참 뒤에 발견된다. 그래서 두 조합을 만들어
    **모서리가 맞는 쪽**을 고른다.

    돌려주는 것: (surface, u_is_j)
      u_is_j=True  → u가 j(행, Y) 방향, v가 i(열, X) 방향
    """
    corner_j = tops[(ny - 1) * nx]      # i=0, j=max
    corner_i = tops[nx - 1]             # i=max, j=0
    for u_count, v_count, u_is_j in ((ny, nx, True), (nx, ny, False)):
        srf = rg.NurbsSurface.CreateThroughPoints(tops, u_count, v_count, 3, 3,
                                                  False, False)
        if srf is None:
            continue
        du, dv = srf.Domain(0), srf.Domain(1)
        want = corner_j if u_is_j else corner_i
        if srf.PointAt(du.T1, dv.T0).DistanceTo(want) < 1e-6:
            return srf, u_is_j
    return None, True


def _up_normal(srf, u, v, up):
    """곡면 법선을 up 쪽 반구로 정규화한다. 법선 방향은 보장되지 않는다."""
    n = srf.NormalAt(u, v)
    if n.IsValid and n * up < 0:
        n.Reverse()
    return n


def offset_iso(srf, u_is_j, along_x, const_param, dist, up, overhang,
               samples=48):
    """곡면의 아이소커브를 법선 방향으로 dist 띄운 곡선.

    곡면을 오프셋한 뒤 아이소커브를 뽑지 않는다 — 오프셋 곡면의 매개화가
    같다는 보장이 없다. 점을 샘플링해 각 점의 법선으로 옮기고 다시 보간한다.

    along_x=True 이면 X(=i) 방향 강선, False 이면 Y(=j) 방향 강선.
    """
    # X방향 강선은 (u_is_j일 때) v를 따라 변한다 → IsoCurve(1, u)
    iso_dir = 1 if (along_x == u_is_j) else 0
    iso = srf.IsoCurve(iso_dir, const_param)
    if iso is None:
        return None

    dom = iso.Domain
    pts = []
    for k in range(samples + 1):
        t = dom.T0 + dom.Length * k / float(samples)
        p = iso.PointAt(t)
        ok, u, v = srf.ClosestPoint(p)
        if not ok:
            continue
        pts.append(p + _up_normal(srf, u, v, up) * dist)
    if len(pts) < 4:
        return None

    crv = rg.Curve.CreateInterpolatedCurve(pts, 3)
    if crv is None:
        return None
    if overhang and overhang > 0:
        ext = crv.Extend(rg.CurveEnd.Both, overhang, rg.CurveExtensionStyle.Line)
        if ext is not None:
            crv = ext
    return crv


def offset_sheet(srf, tops_uv, nx, ny, dist, up):
    """핀 격자 위치의 점들을 법선으로 dist 띄워 만든 시트 곡면."""
    pts = []
    for (u, v) in tops_uv:
        pts.append(srf.PointAt(u, v) + _up_normal(srf, u, v, up) * dist)
    sheet, _ = deck_surface(pts, nx, ny)
    return sheet


def make_envelope(plane, w, l, hmin, hmax):
    """핀이 움직일 수 있는 공간. 여기를 벗어나면 클램핑이다."""
    box = rg.Box(plane,
                 rg.Interval(0, w),
                 rg.Interval(0, l),
                 rg.Interval(hmin, hmax))
    return box.ToBrep()


if compute and target_srf is not None:
    r = run_adaptive_mold(
        target_srf,
        base_plane=base_plane,
        width=width, length=length, spacing=spacing,
        max_height=max_height, min_height=min_height,
        compute=True,
        component=ghenv.Component,
    )

    positioned = r.positioned_srf
    extended = r.extended_srf
    pin_tops = list(r.pin_tops)
    envelope = make_envelope(base_plane, width, length, min_height, max_height)

    normal = base_plane.ZAxis
    for idx, (pt, h) in enumerate(zip(r.grid_pts, r.pin_heights)):
        pin = make_pin(pt, normal, h, pin_radius)
        if pin is None:
            continue
        if r.clamp_flags[idx]:
            pins_clamped.append(pin)
        elif r.extension_flags[idx]:
            pins_ext.append(pin)
        else:
            pins_ok.append(pin)

    nx = int(width // spacing) + 1
    ny = int(length // spacing) + 1
    deck = make_deck_mesh(pin_tops, nx, ny)

    # ── 강선 메쉬 ────────────────────────────────────────
    up = base_plane.ZAxis
    r_main = wire_d_main / 2.0
    r_sub = wire_d_sub / 2.0

    z_main = r_main                        # 굵은 U 중심 — 밑면이 핀 상단에 닿는다
    z_v = 2.0 * r_main + r_sub             # V 중심 — 굵은 U 위에 얹힌다
    z_sub = 2.0 * r_main - r_sub           # 보조 U 중심 — V 밑면에 닿는다
    mesh_top = 2.0 * r_main + 2.0 * r_sub  # 메쉬 상단 = V 강선 윗면

    srf0, u_is_j = deck_surface(pin_tops, nx, ny)

    if srf0 is not None:
        tops_uv = []
        for p in pin_tops:
            ok, u, v = srf0.ClosestPoint(p)
            tops_uv.append((u, v) if ok else (0.0, 0.0))

        def row_param(j):
            """X(=U)방향 강선의 상수 파라미터 — 행 j."""
            u, v = tops_uv[j * nx]
            return u if u_is_j else v

        def col_param(i):
            """Y(=V)방향 강선의 상수 파라미터 — 열 i."""
            u, v = tops_uv[i]
            return v if u_is_j else u

        def span(params, per_gap):
            """격자선 파라미터 사이에 per_gap개씩 끼운 목록."""
            out = []
            for k in range(len(params) - 1):
                a, b = params[k], params[k + 1]
                for m in range(1, per_gap + 1):
                    out.append(a + (b - a) * m / float(per_gap + 1))
            return out

        # 굵은 U — 핀 행마다 1본
        for j in range(ny):
            c = offset_iso(srf0, u_is_j, True, row_param(j), z_main, up,
                           wire_extend)
            if c is not None:
                wires.append(c)

        # 보조 U — 굵은 U 사이에 sub_per_gap개씩, V 강선 아래로
        for prm in span([row_param(j) for j in range(ny)], int(sub_per_gap)):
            c = offset_iso(srf0, u_is_j, True, prm, z_sub, up, wire_extend)
            if c is not None:
                wires_sub.append(c)

        # V — 핀 열마다 1본 + 열 사이에 v_per_gap개씩
        col_params = [col_param(i) for i in range(nx)]
        for prm in col_params + span(col_params, int(v_per_gap)):
            c = offset_iso(srf0, u_is_j, False, prm, z_v, up, wire_extend)
            if c is not None:
                wires_v.append(c)

        # 시트 — 메쉬 상단에 실리콘, 그 위에 내열. 출력은 각 시트의 상면이고
        # 내열 상면이 실제 성형면이다.
        sheet_si = offset_sheet(srf0, tops_uv, nx, ny,
                                mesh_top + sheet_si_t, up)
        sheet_ht = offset_sheet(srf0, tops_uv, nx, ny,
                                mesh_top + sheet_si_t + sheet_ht_t, up)

    # ── 이탈량 — 몰드 품질의 핵심 지표 ────────────────────
    #
    # 핀 상단을 재면 안 된다. 핀 높이는 목표 곡면에 레이캐스트해서 구하므로
    # 핀 상단은 정의상 곡면 위에 있고, 그 거리는 항상 0이다(동어반복).
    #
    # 실제로 재야 하는 것은 **핀과 핀 사이**다. 핀은 이산적인 지지점이고
    # 그 사이의 데크는 목표 곡면을 따라가지 못한다. 이 새그(sagitta)가
    # 몰드가 그 형상을 재현할 수 있는지를 말해준다.
    #   - 평면·단곡: 거의 0 (핀 격자로 잘 근사됨)
    #   - 안장형:    커짐 (핀 격자로 근사하기 어려운 형상)

    probe = positioned
    if probe is not None and not isinstance(probe, rg.Brep):
        probe = probe.ToBrep()

    if probe is not None and deck is not None:
        samples = []
        for f in range(deck.Faces.Count):
            samples.append(deck.Faces.GetFaceCenter(f))
        for e in range(deck.TopologyEdges.Count):
            ln = deck.TopologyEdges.EdgeLine(e)
            samples.append(ln.PointAt(0.5))
        for p in samples:
            cp = probe.ClosestPoint(p)
            deviation.append(p.DistanceTo(cp) if cp is not None else None)

    valid_dev = [d for d in deviation if d is not None]
    n_clamped = sum(1 for c in r.clamp_flags if c)
    n_ext = sum(1 for e in r.extension_flags if e)
    heights = [h for h in r.pin_heights if h is not None]

    branch_counts = {}
    for b in r.branch_taken:
        branch_counts[b] = branch_counts.get(b, 0) + 1

    stack_total = mesh_top + sheet_si_t + sheet_ht_t

    lines = [
        "AMv1 Inspect",
        "=" * 40,
        "그리드:      {} x {} = {} 핀".format(nx, ny, nx * ny),
        "stroke:      {:.0f} ~ {:.0f} mm".format(min_height, max_height),
        "",
        "핀 높이:     min={:.1f}  max={:.1f}  폭={:.1f} mm".format(
            min(heights) if heights else 0,
            max(heights) if heights else 0,
            (max(heights) - min(heights)) if heights else 0),
        "             <- 평면 패널이면 폭이 0이어야 정렬이 맞은 것",
        "클램핑:      {} / {}   <- 0이 아니면 그 지점은 목표를 재현 못 함".format(
            n_clamped, len(r.pin_heights)),
        "확장영역:    {} / {}   <- 원본 곡면 밖, 높이가 외삽값".format(
            n_ext, len(r.pin_heights)),
        "",
        "강선 메쉬:",
        "  U 굵은 (ø{:.0f}): {:>3}본  길이 {:.0f} mm  오버행 {:.0f} mm/끝(곡선따라)".format(
            wire_d_main, len(wires),
            max(c.GetLength() for c in wires) if wires else 0, wire_extend),
        "  U 보조 (ø{:.0f}): {:>3}본  굵은 강선 사이 {}개씩, V 아래로 엮임".format(
            wire_d_sub, len(wires_sub), int(sub_per_gap)),
        "  V      (ø{:.0f}): {:>3}본  핀 열마다 + 열 사이 {}개씩".format(
            wire_d_sub, len(wires_v), int(v_per_gap)),
        "  적층(핀 상단 기준): U중심 {:.1f} / 보조U중심 {:.1f} / V중심 {:.1f} / 메쉬상단 {:.1f} mm".format(
            z_main, z_sub, z_v, mesh_top),
        "  시트: 실리콘 {:.0f} + 내열 {:.0f}  ->  성형면 = 핀 상단 +{:.1f} mm".format(
            sheet_si_t, sheet_ht_t, stack_total),
        "  ** 핀 높이는 목표곡면에 맞춰 계산된다. 그 위에 스택이 얹히므로",
        "     성형면이 목표곡면보다 {:.1f} mm 위로 뜬다 — 핀 높이에서 그만큼".format(stack_total),
        "     빼야 맞는다. 지금은 미반영(Phase A~D 동작을 바꾸지 않기 위해).",
        "  ** 강선 지름·개수·시트 두께는 전부 가정치. 실물 사양 필요.",
        "",
        "핀 사이 새그: max={:.3f}  avg={:.3f} mm  ({}점 샘플)".format(
            max(valid_dev) if valid_dev else 0,
            sum(valid_dev) / len(valid_dev) if valid_dev else 0,
            len(valid_dev)),
        "             <- 핀 격자가 그 형상을 못 따라가는 정도",
        "폴백 가지:   {}".format(branch_counts),
        "",
        r.info,
    ]
    info = "\n".join(lines)

else:
    info = "compute=True 로 설정하고 target_srf를 연결하세요."

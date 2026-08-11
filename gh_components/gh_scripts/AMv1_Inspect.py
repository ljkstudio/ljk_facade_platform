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
#   compute         bool   False
#
# Outputs:
#   pins_ok        정상 핀 (Brep)         — 회색 프리뷰 권장
#   pins_clamped   stroke 한계에 걸린 핀   — 빨강 권장
#   pins_ext       확장영역 핀             — 노랑 권장
#   pin_tops       핀 상단 점
#   wires          U방향 강선 (3차 보간곡선, 양 끝 오버행)
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

# 강선 오버행 — 액추에이터 영역 밖으로 더 나가는 길이.
# 실물 사진(image/adaptiveMold_image.png)에서 200~300mm로 관측된다.
try:
    wire_extend
except NameError:
    wire_extend = None
if wire_extend is None:
    wire_extend = 250.0


pins_ok = []
pins_clamped = []
pins_ext = []
pin_tops = []
wires = []
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


def make_wires(tops, nx, ny, overhang):
    """U 방향(X, i가 변하는 방향) 강선. 핀 상단을 잇고 양 끝을 내민다.

    **직선 폴리라인이 아니라 3차 보간곡선이다.** 탄성 스트립은 변형에너지
    (∫κ²)를 최소화하는 형상으로 안정되고 그 해가 자연 3차 스플라인이다.
    직선 데크는 물리 모델이 아니라 상한선이며, 새그를 26배 과대평가한다.

    **오버행은 접선 직선으로 뻗는다** (`CurveExtensionStyle.Line`).
    마지막 핀 바깥은 하중도 모멘트도 없는 자유단이므로 직선이 된다.
    곡률을 이어가는 Smooth 연장은 자유단에 모멘트가 남아 있다는 뜻이어서,
    끝을 붙잡는 장치가 실제로 있을 때만 맞다.
    """
    if len(tops) != nx * ny or nx < 2:
        return []
    out = []
    for j in range(ny):
        row = [tops[j * nx + i] for i in range(nx)]
        crv = rg.Curve.CreateInterpolatedCurve(row, 3)
        if crv is None:
            continue
        if overhang and overhang > 0:
            ext = crv.Extend(rg.CurveEnd.Both, overhang,
                             rg.CurveExtensionStyle.Line)
            if ext is not None:
                crv = ext
        out.append(crv)
    return out


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
    wires = make_wires(pin_tops, nx, ny, wire_extend)

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
        "강선(U방향): {}본  오버행 {:.0f} mm/끝  길이 {:.0f} ~ {:.0f} mm".format(
            len(wires), wire_extend,
            min(c.GetLength() for c in wires) if wires else 0,
            max(c.GetLength() for c in wires) if wires else 0),
        "             <- 3차 보간곡선(탄성 스트립), 오버행은 접선 직선",
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

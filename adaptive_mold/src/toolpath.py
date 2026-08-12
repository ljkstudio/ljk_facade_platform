# -*- coding: utf-8 -*-
"""롤러 패스 생성 — 로봇암 롤러로 금속 박판을 몰드면에 눌러 앉히는 경로.

RhinoCommon만 쓴다(Grasshopper 미참조). GH 컴포넌트는 얇은 어댑터다.

──────────────────────────────────────────────────────────
왜 방향을 마음대로 못 정하는가
──────────────────────────────────────────────────────────

롤러는 **접촉선이 축과 평행한 강체**다. 그래서

- **진행 방향으로만 굽힘을 준다.** 롤러가 굴러가며 판재를 아래로 누르면
  진행 방향 단면이 롤러 밑을 지나며 굽는다.
- **축 방향으로는 굽힘을 줄 수 없다.** 축 방향으로 곡률이 있으면 접촉선이
  곡면에 앉지 못하고 점 접촉이 되며, 하중이 한 점에 몰려 판재에 흠이 난다.

따라서 **축 = |곡률|이 작은 주방향, 진행 = |곡률|이 큰 주방향**이다.
쌍곡포물면(안장)은 ruled surface라 직선 방향이 존재하므로 축을 거기에 두면
접촉선이 정확히 앉는다. 반대로 돔처럼 두 주곡률이 같은 부호로 큰 형상은
어느 방향에도 직선이 없어 **롤러 폭이 길수록 접촉이 나빠진다** — 이 판정을
`seat_error`로 계산해서 보고한다. 형상이 안 되는 것을 경로 탓으로 오해하지
않기 위한 수치다.

──────────────────────────────────────────────────────────
좌표 규약
──────────────────────────────────────────────────────────

로봇 타겟은 Plane으로 준다.
  origin = 롤러 **중심**(접촉점에서 법선으로 sheet_t + roller_d/2)
  ZAxis  = 곡면 법선의 **반대**(공구가 내려누르는 방향)
  XAxis  = 진행 방향 접선
  YAxis  = 롤러 축 방향
포스트프로세서는 이 규약만 알면 된다.
"""

import math

import Rhino.Geometry as rg


TOL = 0.001


class RollerPathResult(object):
    def __init__(self):
        self.paths = []          # 롤러 중심 경로 (Curve) — 진행 순서대로
        self.targets = []        # [[Plane, ...], ...] 경로별 로봇 타겟
        self.move_kinds = []     # targets와 같은 구조. "approach"/"form"/"retract"
        self.roller_lines = []   # 각 경로 시작점의 롤러 축 표시선 (Line)
        self.contact = []        # 경로별 접촉점 목록 (Point3d)
        self.info = {}


def _as_surface(geo):
    """Surface / Brep / BrepFace를 Surface로 맞춘다."""
    if isinstance(geo, rg.Brep):
        if geo.Faces.Count == 0:
            return None
        return geo.Faces[0]
    if isinstance(geo, rg.BrepFace):
        return geo
    if isinstance(geo, rg.Surface):
        return geo
    return None


def _up_normal(srf, u, v, up):
    """법선을 up 반구로 정규화. FitPlane 계열과 마찬가지로 방향이 보장되지 않는다."""
    n = srf.NormalAt(u, v)
    if not n.IsValid:
        return None
    if n * up < 0:
        n.Reverse()
    return n


def _param_tangents(srf, u, v):
    """(u,v)에서 u방향·v방향 접선. Evaluate의 도함수를 쓴다."""
    ok, pt, ders = srf.Evaluate(u, v, 1)
    if not ok or len(ders) < 2:
        return None, None
    du, dv = rg.Vector3d(ders[0]), rg.Vector3d(ders[1])
    du.Unitize()
    dv.Unitize()
    return du, dv


def choose_travel_direction(srf, up, axis_mode="auto"):
    """진행 방향에 해당하는 **매개변수 방향**(0=u, 1=v)을 고른다.

    axis_mode:
      "auto" — 곡면 중앙의 주곡률을 재서 |κ|가 큰 주방향에 가까운 매개방향
      "u" / "v" — 강제 지정 (진행 방향)

    돌려주는 것: (travel_dir, diag)  travel_dir ∈ {0, 1}
    """
    du_dom, dv_dom = srf.Domain(0), srf.Domain(1)
    um, vm = du_dom.Mid, dv_dom.Mid
    diag = {}

    if axis_mode == "u":
        return 0, {"mode": "forced-u"}
    if axis_mode == "v":
        return 1, {"mode": "forced-v"}

    cur = srf.CurvatureAt(um, vm)
    if cur is None:
        return 0, {"mode": "auto-failed", "note": "CurvatureAt None"}

    k = [abs(cur.Kappa(0)), abs(cur.Kappa(1))]
    hi = 0 if k[0] >= k[1] else 1        # 굽혀야 하는 방향 = |κ| 큰 쪽
    d_hi = cur.Direction(hi)

    du, dv = _param_tangents(srf, um, vm)
    if du is None:
        return 0, {"mode": "auto-failed", "note": "Evaluate 실패"}

    # 주방향이 어느 매개방향에 더 가까운가
    travel = 0 if abs(du * d_hi) >= abs(dv * d_hi) else 1
    diag = {
        "mode": "auto",
        "kappa_max": max(k),
        "kappa_min": min(k),
        "travel_param": "u" if travel == 0 else "v",
        "align": max(abs(du * d_hi), abs(dv * d_hi)),
    }
    return travel, diag


def seat_error(srf, u_or_v_const, travel_dir, roller_w, up, samples=9):
    """롤러 접촉선이 곡면에 앉는 정도 — 축 방향 곡률 때문에 생기는 틈(mm).

    접촉점에서 축 방향으로 ±roller_w/2 만큼 간 지점이 접촉선(직선)에서
    얼마나 떨어지는지 잰다. 0이면 완전히 앉고, 크면 점 접촉에 가까워진다.
    """
    axis_dir = 1 - travel_dir
    dom_axis = srf.Domain(axis_dir)
    dom_travel = srf.Domain(travel_dir)

    t_mid = dom_travel.Mid
    if travel_dir == 0:
        u, v = t_mid, u_or_v_const
    else:
        u, v = u_or_v_const, t_mid

    n = _up_normal(srf, u, v, up)
    if n is None:
        return None
    p0 = srf.PointAt(u, v)

    du, dv = _param_tangents(srf, u, v)
    if du is None:
        return None
    a_dir = dv if axis_dir == 1 else du       # 축 방향 접선
    line = rg.Line(p0 - a_dir * (roller_w / 2.0), p0 + a_dir * (roller_w / 2.0))

    worst = 0.0
    for k in range(samples):
        s = -0.5 + k / float(samples - 1)     # -0.5 ~ +0.5
        target = p0 + a_dir * (roller_w * s)
        ok, uu, vv = srf.ClosestPoint(target)
        if not ok:
            continue
        p_srf = srf.PointAt(uu, vv)
        worst = max(worst, p_srf.DistanceTo(line.ClosestPoint(p_srf, True)))
    return worst


def _offset_iso(srf, iso_dir, const_param, dist, up, samples):
    """아이소커브를 법선으로 dist 띄운 곡선과, 접촉점·법선·접선 목록.

    오프셋 곡면의 매개화를 신뢰하지 않고 점을 샘플링해 옮긴 뒤 재보간한다.
    """
    iso = srf.IsoCurve(iso_dir, const_param)
    if iso is None:
        return None, [], [], []

    dom = iso.Domain
    pts, contact, normals, tangents = [], [], [], []
    for k in range(samples + 1):
        t = dom.T0 + dom.Length * k / float(samples)
        p = iso.PointAt(t)
        ok, u, v = srf.ClosestPoint(p)
        if not ok:
            continue
        n = _up_normal(srf, u, v, up)
        if n is None:
            continue
        tan = iso.TangentAt(t)
        if not tan.IsValid:
            continue
        tan.Unitize()
        contact.append(p)
        normals.append(n)
        tangents.append(tan)
        pts.append(p + n * dist)

    if len(pts) < 4:
        return None, [], [], []
    return rg.Curve.CreateInterpolatedCurve(pts, 3), contact, normals, tangents


def order_paths(values, mode="center-alt"):
    """패스를 어떤 순서로 지날지.

    주름은 자유 경계에서 시작해 안으로 밀려 들어온다. 중앙을 먼저 앉히고
    바깥으로 밀어내면 여분 재료가 경계로 빠져나갈 길이 남는다. 한쪽 끝에서
    시작하면 그 여분이 반대쪽에 쌓인다.

    다만 순서가 공중 이동거리를 크게 바꾼다(실측치는 info에 나온다).

    center-alt  중앙에서 좌우 번갈아. 재료 흐름이 대칭이지만 홉이 계속 커진다
    center-half 중앙→한쪽 끝, 다시 중앙→반대쪽. 각 반쪽은 여전히 밖으로
                밀어내고, 긴 홉이 한 번(중앙 복귀)으로 줄어든다
    sequential  한쪽 끝에서 순서대로. 이동은 최소지만 여분이 반대쪽에 쌓인다
    """
    n = len(values)
    mid = n // 2

    if mode == "sequential":
        return list(values)

    if mode == "center-half":
        return list(values[mid:]) + list(reversed(values[:mid]))

    order = [mid]
    step = 1
    while len(order) < n:
        for s in (mid - step, mid + step):
            if 0 <= s < n and s not in order:
                order.append(s)
        step += 1
    return [values[i] for i in order]


def generate_roller_paths(mold_srf, base_plane=None, sheet_t=1.5, roller_d=60.0,
                          roller_w=80.0, stepover=0.0, passes=1,
                          axis_mode="auto", start_center=True, samples=40,
                          zigzag=True, clearance=30.0, order_mode=None):
    """몰드면 위의 롤러 패스를 만든다.

    mold_srf : 성형면(= 내열 시트 상면). Surface / Brep / BrepFace
    sheet_t  : 금속 박판 두께 (mm)
    roller_d : 롤러 지름 (mm)
    roller_w : 롤러 폭 (mm) — 접촉선 길이. seat_error 판정에 쓴다
    stepover : 패스 간격 (mm). 0이면 roller_w * 0.5
    passes   : 점진 가압 패스 수. 2 이상이면 베이스 평면에서 몰드면까지
               선형 보간한 중간 깊이를 먼저 지난다. **기하 가정이며 실제
               중간 형상은 해석이 필요하다** — info에 명시한다
    """
    res = RollerPathResult()

    srf = _as_surface(mold_srf)
    if srf is None:
        res.info["error"] = "몰드면을 Surface로 변환할 수 없다"
        return res

    if base_plane is None:
        base_plane = rg.Plane.WorldXY
    up = base_plane.ZAxis

    if stepover is None or stepover <= 0:
        stepover = roller_w * 0.5

    travel_dir, diag = choose_travel_direction(srf, up, axis_mode)
    axis_dir = 1 - travel_dir

    # 패스 개수 — 축 방향 길이를 stepover로 나눈다
    dom_axis = srf.Domain(axis_dir)
    dom_travel = srf.Domain(travel_dir)
    span_iso = srf.IsoCurve(axis_dir, dom_travel.Mid)
    axis_len = span_iso.GetLength() if span_iso is not None else dom_axis.Length
    # ceil을 쓴다 — floor면 실측 간격이 설정보다 **커져** 겹침이 요청보다
    # 적어진다(실측 41.7 vs 설정 40). 겹침은 부족한 쪽으로 틀리면 안 된다.
    n_paths = max(2, int(math.ceil(axis_len / float(stepover))) + 1)

    consts = [dom_axis.T0 + dom_axis.Length * i / float(n_paths - 1)
              for i in range(n_paths)]
    # order_mode가 주어지면 그것이 우선. 없으면 기존 start_center 동작 유지.
    mode = order_mode if order_mode else ("center-alt" if start_center
                                          else "sequential")
    consts = order_paths(consts, mode)

    r_off = sheet_t + roller_d / 2.0
    seat = []
    idx = 0                      # 실행 순서 index — 지그재그 방향 판정에 쓴다

    for p in range(int(max(1, passes))):
        # 점진 가압: 마지막 패스만 몰드면까지 간다
        depth_frac = (p + 1) / float(max(1, passes))
        for c in consts:
            crv, contact, normals, tangents = _offset_iso(
                srf, travel_dir, c, r_off, up, samples)
            if crv is None:
                continue

            if depth_frac < 1.0:
                # 베이스 평면 쪽으로 (1-frac) 만큼 되돌린 중간 깊이
                pts = []
                for q, n in zip(contact, normals):
                    h = base_plane.DistanceTo(q)
                    q_mid = q - up * (h * (1.0 - depth_frac))
                    pts.append(q_mid + n * r_off)
                crv_mid = rg.Curve.CreateInterpolatedCurve(pts, 3)
                if crv_mid is not None:
                    crv = crv_mid

            # 왕복(지그재그) — 홀수 번째 패스는 거꾸로 간다.
            # **접선도 함께 뒤집는다.** 순서만 뒤집으면 타겟의 XAxis가 실제
            # 진행 방향과 반대가 되어, 자세는 그대로인데 방향만 바뀐 경로가
            # 나온다. 눈으로는 멀쩡해 보이고 로봇에서 틀어진다.
            reverse = bool(zigzag) and (idx % 2 == 1)
            if reverse:
                contact = list(reversed(contact))
                normals = list(reversed(normals))
                tangents = [-t for t in reversed(tangents)]
                crv = crv.DuplicateCurve()
                crv.Reverse()

            res.paths.append(crv)
            res.contact.append(contact)

            planes = []
            for q, n, tan in zip(contact, normals, tangents):
                z = rg.Vector3d(n)
                z.Reverse()                      # 공구는 내려누른다
                x = rg.Vector3d(tan)
                y = rg.Vector3d.CrossProduct(z, x)
                if not y.Unitize():
                    continue
                x = rg.Vector3d.CrossProduct(y, z)
                x.Unitize()
                planes.append(rg.Plane(q + n * r_off, x, y))

            # 접근·후퇴 — 이것이 없으면 다음 패스로 넘어갈 때 롤러가 판재를
            # 누른 채 가로질러 긁는다. 성형 자세를 유지한 채 법선으로만 띄운다.
            kinds = ["form"] * len(planes)
            if planes and clearance and clearance > 0:
                lift = rg.Vector3d(planes[0].ZAxis)
                lift.Reverse()
                ap = rg.Plane(planes[0])
                ap.Origin = planes[0].Origin + lift * clearance
                rt = rg.Plane(planes[-1])
                rt.Origin = planes[-1].Origin + rg.Vector3d(
                    -planes[-1].ZAxis.X, -planes[-1].ZAxis.Y,
                    -planes[-1].ZAxis.Z) * clearance
                planes = [ap] + planes + [rt]
                kinds = ["approach"] + kinds + ["retract"]

            res.targets.append(planes)
            res.move_kinds.append(kinds)

            if planes:
                pl = planes[0]
                res.roller_lines.append(rg.Line(
                    pl.Origin - pl.YAxis * (roller_w / 2.0),
                    pl.Origin + pl.YAxis * (roller_w / 2.0)))

            e = seat_error(srf, c, travel_dir, roller_w, up)
            if e is not None:
                seat.append(e)
            idx += 1

    # 실제 패스 간격 — 매개변수 등분이 공간 등분과 다를 수 있으므로 실측한다
    gaps = []
    ordered = sorted([dom_axis.T0 + dom_axis.Length * i / float(n_paths - 1)
                      for i in range(n_paths)])
    for a, b in zip(ordered, ordered[1:]):
        ca = srf.IsoCurve(travel_dir, a)
        cb = srf.IsoCurve(travel_dir, b)
        if ca is None or cb is None:
            continue
        rc = rg.Curve.ClosestPoints(ca, cb)
        if rc[0]:
            gaps.append(rc[1].DistanceTo(rc[2]))

    # 패스 사이 이동거리 — 후퇴 지점에서 다음 접근 지점까지.
    # 지그재그가 실제로 이 값을 줄이는지 확인하기 위한 실측이다.
    links = []
    for a, b in zip(res.targets, res.targets[1:]):
        if a and b:
            links.append(a[-1].Origin.DistanceTo(b[0].Origin))

    n_form = sum(1 for ks in res.move_kinds for k in ks if k == "form")
    n_air = sum(1 for ks in res.move_kinds for k in ks if k != "form")

    res.info = {
        "order_mode": mode,
        "zigzag": bool(zigzag),
        "clearance": clearance,
        "form_targets": n_form,
        "air_targets": n_air,
        "link_min": min(links) if links else None,
        "link_max": max(links) if links else None,
        "link_total": sum(links) if links else 0.0,
        "travel": diag.get("travel_param", "?"),
        "travel_diag": diag,
        "n_paths_per_pass": n_paths,
        "passes": int(max(1, passes)),
        "path_count": len(res.paths),
        "target_count": sum(len(t) for t in res.targets),
        "stepover_set": stepover,
        "stepover_measured": (min(gaps), max(gaps)) if gaps else None,
        "axis_span": axis_len,
        "roller_center_offset": r_off,
        "seat_error_max": max(seat) if seat else None,
        "seat_error_min": min(seat) if seat else None,
        "progressive_is_geometric": int(max(1, passes)) > 1,
    }
    return res

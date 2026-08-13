# -*- coding: utf-8 -*-
"""로봇 베이스를 어디 세울지 격자로 훑어 찾는다.

J-010 에서 판정 축이 넷이 되었다 — 도달·간섭·가동범위·이송. 그러면 탐색의
목적함수를 쓸 수 있다. 이 모듈이 그것을 한다.

──────────────────────────────────────────────────────────
목적함수 — 가동범위 여유를 최대화한다
──────────────────────────────────────────────────────────

**단일 점수로 넷을 섞지 않는다.** mm 와 deg 와 % 를 더하려면 가중치를 발명해야
하고, 그 가중치가 결론을 정하게 된다. 대신:

    하드 제약   도달 실패 0 / 베이스 겹침 없음 / 팔 간섭 없음 / 정격 이내
    목적        min(관절 여유) 를 최대화

**왜 관절 여유인가:** 실측(J-010 FACT-02)에서 이 경로의 병목이 j2 였다.
베이스를 멀리 놓으면 j2 가 상한(85)에, 가까이 놓으면 하한(-65)에 닿는다.
즉 세울 수 있는 구간을 **j2 하나가 양쪽에서 정한다.** 다른 축은 여유가
수백 deg 거나(j1·j4·j6) 간섭처럼 별개 축이다.

도달 실패·간섭은 **정도가 아니라 가부**로 쓴다. "실패 3개짜리 위치"는
쓸 수 없으므로 점수를 매길 필요가 없다.

──────────────────────────────────────────────────────────
지도를 낸다 — 승자 하나로는 판단할 수 없다
──────────────────────────────────────────────────────────

최적점 하나만 보고하면 그 최적이 **평지인지 칼날인지** 모른다. 평지라면
설치 오차를 감당하고, 칼날이라면 몇 cm 틀어져도 못 쓴다. 그래서 격자 전체를
지도로 낸다.

──────────────────────────────────────────────────────────
타겟을 솎지 않는다 (실측)
──────────────────────────────────────────────────────────

후보 하나 평가가 **IK 1.52초 + 기구 0.20초**다(타겟 1,175개, Rhino 8.33).
전수로 돌 수 있으므로 솎을 이유가 없고, **솎으면 틀린다:**

    stride  1  → j 최소여유  7.1  (참값)
    stride  5  → 9.2
    stride 20  → 13.7      ← 두 배 낙관적이다

두 가지 이유로 근사가 아니다. (1) 병목 자세가 표본에서 빠진다. (2)
`track_toolpath` 가 앞 해를 다음 시드로 쓰므로 **솎으면 궤적 자체가 달라진다.**
"빠른 근사"로 쓰면 실제보다 여유 있는 자리를 골라 놓고 안전하다고 믿게 된다.
"""

import math

import Rhino.Geometry as rg

import robot as rb
import mechanics as mc


# 격자 간격 (mm). 200 은 핀 간격과 같아 읽기 쉽다.
DEFAULT_STEP_MM = 200.0

# 도달 판정 허용오차 (mm) — AMv1 Robot·playback 과 같은 값
REACH_TOL_MM = 2.0

# 사전 기각용 도달 반경 (mm). 정격 3,200 + 여유 400.
# **넉넉해야 한다** — 사전 기각은 IK 를 아끼려는 것이고, 되는 자리를 하나라도
# 버리면 탐색이 거짓말을 한다. 어깨(j2 피벗)를 중심으로 재므로 축1 기준
# 정격과 최대 320 mm 어긋난다. 그 오차를 여유로 덮는다.
PREFILTER_REACH_MM = 3600.0

# 어깨(j2 피벗) 위치 — 베이스 평면 좌표 (mm)
_SH = (rb.PIVOTS_M["j2"][0] * rb.MM, 0.0, rb.PIVOTS_M["j2"][2] * rb.MM)


def far_target(targets, plane, limit=PREFILTER_REACH_MM):
    """어깨에서 가장 먼 타겟까지의 거리가 limit 을 넘으면 그 거리, 아니면 None.

    IK 를 돌리기 전의 값싼 기각이다 (타겟 1,175개에 수 ms).
    """
    sh = plane.PointAt(_SH[0], _SH[1], _SH[2])
    worst = 0.0
    for t in targets:
        d = sh.DistanceTo(t.Origin)
        if d > worst:
            worst = d
    return worst if worst > limit else None


def grid_points(x0, x1, y0, y1, step=DEFAULT_STEP_MM):
    """(x, y) 후보 목록과 축 값. 경계를 포함한다.

    돌려주는 것: (points, x_vals, y_vals)
    """
    step = abs(float(step))
    if step <= 0.0:
        return [], [], []
    xs = _axis(x0, x1, step)
    ys = _axis(y0, y1, step)
    pts = [(x, y) for y in ys for x in xs]
    return pts, xs, ys


def polar_points(center, r0, r1, dr, a0=0.0, a1=345.0, da=15.0):
    """몰드 중심을 둘러싼 고리 격자. `(points, angles, radii)`

    **사각 격자보다 이쪽이 맞다 (실측).** 가능한 자리는 고리 모양이다 — 너무
    가까우면 팔을 접다가 j2 하한에, 너무 멀면 j2 상한·도달 실패에 걸린다.
    사각 격자로 훑으면 후보의 대부분이 그 고리 밖이라 IK 를 헛돈다
    (5x5 = 25개 중 통과 5개, 그리고 **기각되는 후보가 더 느리다** — IK 가
    수렴하지 못해 반복을 다 쓴다).

    각도는 월드 +X 에서 반시계로 잰다. `points` 는 `(x, y, angle, radius)`.
    """
    dr = abs(float(dr))
    da = abs(float(da))
    if dr <= 0.0 or da <= 0.0:
        return [], [], []
    radii = _axis(r0, r1, dr)
    angles = _axis(a0, a1, da)
    pts = []
    for r in radii:
        for a in angles:
            t = float(a) * 3.141592653589793 / 180.0
            pts.append((center.X + r * math.cos(t),
                        center.Y + r * math.sin(t), a, r))
    return pts, angles, radii


def _axis(a, b, step):
    lo = min(float(a), float(b))
    hi = max(float(a), float(b))
    out = []
    v = lo
    # 부동소수 누적을 피하려고 인덱스로 만든다
    n = int(round((hi - lo) / step))
    for i in range(n + 1):
        v = lo + i * step
        out.append(v)
    if out and out[-1] < hi - 1e-9:
        out.append(hi)
    return out


def evaluate(targets, origin, kinds=None, mold_pts=None,
             feed=50.0, joint_scale=0.25, hit=None, tol=REACH_TOL_MM,
             ik_opts=None, direction=None):
    """후보 하나를 평가한다.

    `origin` 은 Point3d. `direction` 이 없으면 방향을 **몰드 중심을 향하도록
    유도한다**(아래 주석). `hit` 은 `(samples, heightfield, margin)` 이거나
    None(간섭 검사 생략).

    돌려주는 dict:
        origin, ok, reason, fails, err_max, j_margin, j_worst,
        min_override, clear, flips, overlap
    """
    res = {"origin": origin, "ok": False, "reason": "", "fails": None,
           "err_max": None, "j_margin": None, "j_worst": None,
           "min_override": None, "clear": None, "flips": None,
           "overlap": None, "hit_checked": hit is not None}

    # 방향은 기본적으로 탐색하지 않는다 — 몰드 중심을 향하는 것이 자명한
    # 선택이고, j1 여유가 146deg 라 방향이 병목이 아니다(J-010). 대신 최적점에서
    # 한 번 각도를 흔들어 이 가정을 확인한다 (tools/search_base.py 의 spin).
    #
    # direction 을 주면 그 방향으로 고정한다. 선을 이미 그어 둔 상태에서
    # **위치만** 옮겨 보고 싶을 때 쓴다 — 그래야 탐색 결과와 살아 있는
    # 파이프라인(resolve_base_plane 이 선 방향을 쓴다)이 일치한다.
    guide = None
    if direction is not None:
        guide = rg.Line(origin, rg.Point3d(origin.X + direction.X,
                                           origin.Y + direction.Y,
                                           origin.Z + direction.Z))
    plane, _note = rb.base_plane_from(point=origin, line=guide,
                                      targets=targets)
    if plane is None:
        res["reason"] = "베이스 평면을 만들 수 없다"
        return res

    # 값싼 기각부터 — 몰드 발자국과 겹치면 세울 수 없는 자리다
    if mold_pts:
        ov = rb.base_overlap(plane, mold_pts)
        res["overlap"] = ov
        if ov > 0.0:
            res["reason"] = "몰드와 {:.0f}mm 겹침".format(ov)
            return res

    far = far_target(targets, plane)
    if far is not None:
        res["reason"] = "도달 범위 밖 {:.0f}mm (사전 기각)".format(far)
        res["prefiltered"] = True
        return res

    opts = dict(ik_opts or {})
    poses, results, flips = rb.track_toolpath(targets, base_plane=plane, **opts)
    errs = [r.pos_err_mm for r in results]
    res["flips"] = flips
    res["fails"] = sum(1 for e in errs if e > tol)
    res["err_max"] = max(errs) if errs else 0.0

    pts = [t.Origin for t in targets]
    chk = mc.check(poses, pts, kinds, feed=feed, joint_scale=joint_scale)
    res["j_margin"] = chk["limits"]["worst"]
    res["j_worst"] = chk["limits"]["worst_joint"]
    res["min_override"] = chk["speed"]["min_override"]

    if hit is not None:
        samples, field, margin = hit
        import collision as col
        pens, whos = col.scan_poses(poses, samples, field,
                                    base_plane=plane, margin=margin)
        summ = col.summarize(pens, whos, margin=margin)
        res["clear"] = summ["min_clear"]
        res["hits"] = summ["hits"]

    res["reason"] = classify(res, tol)
    res["ok"] = (res["reason"] == "")
    return res


def classify(r, tol=REACH_TOL_MM):
    """하드 제약을 어겼으면 그 이유, 통과면 빈 문자열.

    **첫 번째로 걸린 것만 돌려준다** — 순서는 값싸고 결정적인 것부터다.
    """
    if r.get("overlap") is not None and r["overlap"] > 0.0:
        return "몰드와 {:.0f}mm 겹침".format(r["overlap"])
    if r.get("fails"):
        return "도달 실패 {}개".format(r["fails"])
    if r.get("j_margin") is not None and r["j_margin"] < 0.0:
        return "{} 가동범위 {:.1f}deg 초과".format(r["j_worst"], -r["j_margin"])
    if r.get("min_override") is not None and r["min_override"] > 1.0:
        return "정격 속도 {:.0f}% 필요".format(r["min_override"] * 100.0)
    if r.get("hits"):
        return "팔 간섭 {}포즈".format(r["hits"])
    return ""


def rank(results):
    """통과한 후보를 관절 여유 내림차순으로.

    동점이면 간섭 여유가 큰 쪽, 그 다음 이송 여유가 큰 쪽을 앞에 둔다.
    """
    ok = [r for r in results if r.get("ok")]
    return sorted(ok, key=lambda r: (
        -(r["j_margin"] if r["j_margin"] is not None else -1e9),
        -(r["clear"] if r.get("clear") is not None else -1e9),
        (r["min_override"] if r["min_override"] is not None else 1e9)))


def render_map(results, x_vals, y_vals, axes=("x", "y")):
    """격자를 문자 지도로. 통과한 칸은 관절 여유(deg)를 정수로 쓴다.

    기호: `.` 몰드 겹침 / `x` 도달 실패 / `!` 가동범위 초과 / `>` 속도 초과
          `#` 간섭 / `-` 사전 기각 / 숫자 = 관절 여유(deg)

    `axes` 는 (가로축 이름, 세로축 이름). 극좌표 훑기에서는 ("각도", "반경").
    """
    # 칸 좌표는 결과가 갖고 있으면 그것을 쓴다 (극좌표 훑기는 각도·반경이 축이다).
    # 없으면 원점의 x·y 다.
    by_xy = {}
    for r in results:
        o = r["origin"]
        cell = r.get("cell") or (o.X, o.Y)
        by_xy[(round(cell[0], 3), round(cell[1], 3))] = r

    def cell(r):
        if r is None:
            return "  ?"
        if not r["ok"]:
            why = r["reason"]
            if "겹침" in why:
                return "  ."
            if "사전 기각" in why:
                return "  -"
            if "도달" in why:
                return "  x"
            if "가동범위" in why:
                return "  !"
            if "속도" in why:
                return "  >"
            if "간섭" in why:
                return "  #"
            return "  ?"
        return "{:>3.0f}".format(r["j_margin"])

    out = []
    out.append("{:>4}\\{:<2}".format(axes[1], axes[0])
               + "".join("{:>7.0f}".format(x) for x in x_vals))
    for y in reversed(y_vals):
        row = ["{:>7.0f}".format(y)]
        for x in x_vals:
            row.append("    " + cell(by_xy.get((round(x, 3), round(y, 3)))))
        out.append("".join(row))
    return "\n".join(out)


def report(results, x_vals, y_vals, top=5, skipped=None, axes=("x", "y")):
    """탐색 결과 요약."""
    lines = []
    n_ok = sum(1 for r in results if r.get("ok"))
    lines.append("베이스 위치 탐색 — 후보 {}개 (격자 {}x{}), 통과 {}개".format(
        len(results), len(x_vals), len(y_vals), n_ok))
    if skipped:
        lines.append("** 생략: {}".format(skipped))
    lines.append("")
    n_pre = sum(1 for r in results if r.get("prefiltered"))
    if n_pre:
        lines.append("사전 기각 {}개 (어깨에서 {:.0f}mm 밖) — IK 를 돌리지 않았다".format(
            n_pre, PREFILTER_REACH_MM))
    lines.append("관절 여유 지도 (deg). - 사전기각  . 겹침  x 도달실패"
                 "  ! 범위초과  > 속도초과  # 간섭")
    lines.append(render_map(results, x_vals, y_vals, axes=axes))
    lines.append("")

    best = rank(results)
    if not best:
        lines.append("통과한 후보가 없다.")
        why = {}
        for r in results:
            k = r["reason"].split(" ")[0] if r["reason"] else "?"
            why[k] = why.get(k, 0) + 1
        for k in sorted(why, key=lambda k: -why[k]):
            lines.append("  {:<14} {}개".format(k, why[k]))
        return "\n".join(lines)

    lines.append("상위 {}개:".format(min(top, len(best))))
    lines.append("     원점(x, y)        관절여유   축   간섭여유   최소오버라이드"
                 "  최대오차")
    for r in best[:top]:
        o = r["origin"]
        lines.append("  ({:>7.0f},{:>6.0f})  {:>8.1f}  {:>4}  {:>8}  {:>13}"
                     "  {:>7.2f}".format(
                         o.X, o.Y, r["j_margin"], r["j_worst"],
                         ("{:.0f}mm".format(r["clear"])
                          if r.get("clear") is not None else "미검사"),
                         ("{:.1f}%".format(r["min_override"] * 100.0)
                          if r["min_override"] is not None else "-"),
                         r["err_max"]))
    return "\n".join(lines)

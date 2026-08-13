# -*- coding: utf-8 -*-
"""그 경로를 로봇이 **기구적으로** 갈 수 있는가 — 포즈 목록만 보고 판정한다.

도달성(reach_err)은 "그 점에 닿는가"이고 간섭(collision)은 "몰드를 치는가"다.
여기는 그 사이에 빠져 있던 것을 본다 — **닿기는 하는데 그렇게 움직일 수 있는가.**

    1. 가동범위     각 관절이 한계 안에 있는가, 여유가 얼마인가
    2. 이송 유지     그 feed 로 가려면 관절이 정격 속도를 넘겨야 하는가
    3. 자세 연속성   구간 사이에 자세가 튀는가 (손목 뒤집힘 등)
    4. 특이점       손목·어깨 특이점에 가까운가, 팔이 얼마나 뻗었는가

──────────────────────────────────────────────────────────
판정이 아니라 여유를 돌려준다
──────────────────────────────────────────────────────────

"된다/안 된다"는 베이스를 어디 놓았는지에 달린 이진값이다. 위치를 잡을 때
필요한 것은 **얼마나 아슬아슬한가**다. 그래서 이 모듈은 전부 여유(margin)로
답한다 — collision.py 의 min_clear 와 같은 원칙이다.

**전부 포즈 목록의 함수다.** 메시도 몰드도 필요 없다. 베이스를 옮기면 IK 가
다른 포즈를 내므로 여유도 따라 변한다 — 점을 끌면서 읽을 수 있다.

──────────────────────────────────────────────────────────
안 보는 것
──────────────────────────────────────────────────────────

- **가감속.** 데이터시트에 축별 가속도가 없다. 모든 속도 판정은 등속 가정이고
  따라서 **낙관적**이다. 실제 장비는 구간 끝에서 감속한다.
- **자기 간섭.** 원통 근사로는 안 된다 — 실측: 베이스를 반경 630 mm 기둥으로
  놓고 팔을 검사하면 link2 후단이 **정상 자세에서도** 473 mm 겹쳐 1,175 포즈
  전부 오검출이 났다. 상완 뒷부분이 기둥 옆을 지나가는 것이 이 로봇의 정상
  형상이기 때문이다. 제대로 하려면 인접하지 않은 링크끼리 메시-메시로 봐야 한다.
- **축 2·3 연동 가동범위.** ABB 실기의 작업영역도는 축2와 축3이 독립이 아니다.
  그 값이 없으므로 여기서는 축별 독립으로 본다 — **미검증 가정이다.**
- **토크·페이로드.** 롤러가 판재를 누르는 반력이 축 토크 한계 안인지 모른다.
"""

import robot as rb


# 이 아래로 내려가면 사람이 봐야 한다는 선 (deg). 안전여유가 아니다.
WARN_LIMIT_DEG = 10.0

# 한 구간에서 이보다 크게 관절이 움직이면 자세가 튄 것으로 본다 (deg).
WARN_JUMP_DEG = 30.0

# 손목 특이점: j4·j6 축이 겹치는 곳이 j5 = 0 이다 (deg).
WARN_J5_DEG = 10.0

# 어깨 특이점: TCP 가 j1 축 위에 오는 것. 수평거리가 이보다 작으면 경고 (mm).
WARN_SHOULDER_MM = 200.0

# IRB6700-150/3.20 정격 도달 (mm). 팔 뻗음을 비율로 읽기 위한 기준.
RATED_REACH_MM = 3200.0

# j2 피벗 높이 (mm, 로봇 좌표) — 팔 뻗음을 여기서 재기 위해.
_SHOULDER_Z_MM = rb.PIVOTS_M["j2"][2] * rb.MM


def limit_margins(poses):
    """관절별 가동범위 사용량과 여유.

    돌려주는 dict: 관절 → {lo, hi, used_lo, used_hi, margin, tight_end}
    `margin` 은 양 끝 중 **가까운 쪽까지의 거리**다 (deg). 음수는 한계를 넘은 것.
    `pinned` 은 한계에 정확히 붙은 (포즈, 관절) 목록 — IK 가 잘라낸 자리다.
    """
    out = {}
    if not poses:
        return {"joints": out, "pinned": [], "worst": None, "worst_joint": None}

    for j in rb.JOINT_NAMES:
        lo, hi = rb.JOINT_LIMITS[j]
        vals = [p.get(j, 0.0) for p in poses]
        used_lo = min(vals)
        used_hi = max(vals)
        m_lo = used_lo - lo
        m_hi = hi - used_hi
        out[j] = {
            "lo": lo, "hi": hi,
            "used_lo": used_lo, "used_hi": used_hi,
            "margin": min(m_lo, m_hi),
            "tight_end": ("lo" if m_lo <= m_hi else "hi"),
        }

    # 한계에 붙은 자리 — IK 가 clamp_joint 로 잘라낸 흔적이다.
    pinned = []
    for i, p in enumerate(poses):
        for j in rb.JOINT_NAMES:
            lo, hi = rb.JOINT_LIMITS[j]
            v = p.get(j, 0.0)
            if abs(v - lo) < 1e-6 or abs(v - hi) < 1e-6:
                pinned.append((i, j))

    worst_joint = min(out, key=lambda k: out[k]["margin"])
    return {"joints": out, "pinned": pinned,
            "worst": out[worst_joint]["margin"], "worst_joint": worst_joint}


def feed_demand(poses, points=None, kinds=None, feed=50.0, joint_scale=0.25):
    """그 feed 로 성형하려면 관절이 얼마나 빨라야 하는가.

    성형 구간만 본다 — 공중 이동은 관절 속도가 지배하는 것이 정상이다.

        필요속도 = |Δθ| / (구간거리 / feed)      [deg/s]
        비율     = 필요속도 / 정격속도

    **두 기준을 따로 낸다.** 정격(100%) 초과는 **기구적으로 불가능**이고,
    오버라이드(joint_scale) 초과는 **프로그램 속도 설정 문제**다. 둘을 섞으면
    고칠 수 있는 것과 고칠 수 없는 것이 구분되지 않는다.

    `min_override` = 그 feed 를 유지하는 데 필요한 최소 오버라이드 비율.
    이 값보다 joint_scale 을 낮추면 롤러가 feed 를 못 낸다 (playback 의 시간
    모델이 조용히 느린 쪽을 택하므로 화면에서는 드러나지 않는다).
    """
    res = {"form_segs": 0, "worst_rated": 0.0, "worst_at": -1,
           "worst_joint": None, "over_rated": 0, "over_override": 0,
           "worst_override": 0.0, "min_override": 0.0,
           "feed": float(feed), "joint_scale": float(joint_scale)}
    if not poses or points is None or len(points) < 2:
        return res
    if feed <= 0.0:
        return res
    scale = float(joint_scale) if joint_scale > 0.0 else 1.0

    for i in range(len(poses) - 1):
        kind = str(kinds[i + 1]) if (kinds and i + 1 < len(kinds)) else "form"
        if kind != "form":
            continue
        if i + 1 >= len(points):
            continue
        dist = points[i].DistanceTo(points[i + 1])
        if dist <= 1e-9:
            continue
        res["form_segs"] += 1
        dt = dist / float(feed)
        bad_rated = False
        bad_ovr = False
        for j in rb.JOINT_NAMES:
            need = abs(poses[i + 1].get(j, 0.0) - poses[i].get(j, 0.0)) / dt
            r = need / rb.JOINT_MAX_SPEED[j]
            if r > res["worst_rated"]:
                res["worst_rated"] = r
                res["worst_at"] = i
                res["worst_joint"] = j
            if r > 1.0:
                bad_rated = True
            if r / scale > 1.0:
                bad_ovr = True
        if bad_rated:
            res["over_rated"] += 1
        if bad_ovr:
            res["over_override"] += 1

    res["worst_override"] = res["worst_rated"] / scale
    res["min_override"] = res["worst_rated"]
    return res


def continuity(poses, points=None):
    """구간 사이 자세 변화. 튀는 곳을 찾는다.

    `per_mm` (deg/mm) 이 핵심이다 — TCP 가 조금 움직이는데 관절이 크게 도는
    구간이 손목 뒤집힘·해 분기다. 절대 각도만 보면 공중 이동과 구분이 안 된다.
    """
    res = {"segs": 0, "worst": 0.0, "worst_at": -1, "worst_joint": None,
           "over": 0, "worst_per_mm": 0.0, "per_mm_at": -1, "top": []}
    if not poses or len(poses) < 2:
        return res

    rows = []
    for i in range(len(poses) - 1):
        d = 0.0
        who = None
        for j in rb.JOINT_NAMES:
            v = abs(poses[i + 1].get(j, 0.0) - poses[i].get(j, 0.0))
            if v > d:
                d = v
                who = j
        dist = None
        if points is not None and i + 1 < len(points):
            dist = points[i].DistanceTo(points[i + 1])
        rows.append((d, i, who, dist))
        if d > res["worst"]:
            res["worst"] = d
            res["worst_at"] = i
            res["worst_joint"] = who
        if d > WARN_JUMP_DEG:
            res["over"] += 1
        if dist is not None and dist > 1e-9:
            pm = d / dist
            if pm > res["worst_per_mm"]:
                res["worst_per_mm"] = pm
                res["per_mm_at"] = i

    res["segs"] = len(rows)
    rows.sort(key=lambda r: -r[0])
    res["top"] = rows[:5]
    return res


def singularity(poses):
    """특이점까지의 거리와 팔 뻗음.

    손목(j5=0)에서는 j4·j6 축이 겹쳐 두 축의 해가 정해지지 않고, 근처에서는
    작은 TCP 이동에 관절 속도가 폭발한다. 어깨는 TCP 가 j1 축 위에 올 때다.

    팔 뻗음은 j2 피벗에서 TCP 까지의 거리다. 정격 도달에 가까울수록 팔꿈치가
    펴져 자세 정확도와 강성이 떨어진다.
    """
    res = {"j5_min": None, "j5_at": -1, "j5_near": 0,
           "shoulder_min": None, "shoulder_at": -1, "shoulder_near": 0,
           "reach_min": None, "reach_max": None, "reach_at": -1,
           "reach_pct": None}
    if not poses:
        return res

    j5 = [abs(p.get("j5", 0.0)) for p in poses]
    res["j5_min"] = min(j5)
    res["j5_at"] = j5.index(res["j5_min"])
    res["j5_near"] = sum(1 for v in j5 if v < WARN_J5_DEG)

    r_best = None
    reach_lo = None
    reach_hi = None
    for i, p in enumerate(poses):
        tcp = rb.tcp_frame(p)
        x = tcp.M03 * rb.MM
        y = tcp.M13 * rb.MM
        z = tcp.M23 * rb.MM
        radial = (x * x + y * y) ** 0.5
        if r_best is None or radial < r_best:
            r_best = radial
            res["shoulder_at"] = i
        if radial < WARN_SHOULDER_MM:
            res["shoulder_near"] += 1
        dz = z - _SHOULDER_Z_MM
        ext = (x * x + y * y + dz * dz) ** 0.5
        if reach_lo is None or ext < reach_lo:
            reach_lo = ext
        if reach_hi is None or ext > reach_hi:
            reach_hi = ext
            res["reach_at"] = i

    res["shoulder_min"] = r_best
    res["reach_min"] = reach_lo
    res["reach_max"] = reach_hi
    res["reach_pct"] = 100.0 * reach_hi / RATED_REACH_MM
    return res


def check(poses, points=None, kinds=None, feed=50.0, joint_scale=0.25):
    """네 가지를 한 번에. `problems` 가 비어 있으면 걸린 것이 없다."""
    lim = limit_margins(poses)
    spd = feed_demand(poses, points, kinds, feed, joint_scale)
    con = continuity(poses, points)
    sng = singularity(poses)

    problems = []
    if lim["worst"] is not None and lim["worst"] < 0.0:
        problems.append("가동범위 초과 ({} {:.1f}deg)".format(
            lim["worst_joint"], lim["worst"]))
    elif lim["pinned"]:
        problems.append("관절 {}자리가 한계에 붙었다".format(len(lim["pinned"])))
    if spd["over_rated"]:
        problems.append("정격 속도 초과 {}구간".format(spd["over_rated"]))
    if con["over"]:
        problems.append("자세 튐 {}구간".format(con["over"]))
    if sng["j5_near"]:
        problems.append("손목 특이점 근처 {}포즈".format(sng["j5_near"]))
    if sng["shoulder_near"]:
        problems.append("어깨 특이점 근처 {}포즈".format(sng["shoulder_near"]))

    tight = []
    if lim["worst"] is not None and 0.0 <= lim["worst"] < WARN_LIMIT_DEG:
        tight.append("{} 여유 {:.1f}deg".format(
            lim["worst_joint"], lim["worst"]))
    if spd["over_override"]:
        tight.append("오버라이드로 feed 못 냄 {}구간".format(spd["over_override"]))

    return {"limits": lim, "speed": spd, "continuity": con,
            "singularity": sng, "problems": problems, "tight": tight,
            "poses": len(poses)}


def report(res):
    """컴포넌트 info 에 그대로 쓸 요약."""
    if not res or not res.get("poses"):
        return "기구 검토: 포즈가 없다"

    lim = res["limits"]
    spd = res["speed"]
    con = res["continuity"]
    sng = res["singularity"]
    out = ["기구 타당성 ({}포즈)".format(res["poses"])]

    out.append("  가동범위:")
    for j in rb.JOINT_NAMES:
        d = lim["joints"][j]
        flag = ""
        if d["margin"] < 0.0:
            flag = "  ** 초과"
        elif d["margin"] < WARN_LIMIT_DEG:
            flag = "  << 아슬아슬"
        out.append("    {} [{:>6.0f},{:>6.0f}]  사용 [{:>6.1f},{:>6.1f}]"
                   "  여유 {:>6.1f}{}".format(
                       j, d["lo"], d["hi"], d["used_lo"], d["used_hi"],
                       d["margin"], flag))
    if lim["pinned"]:
        out.append("    ** {}자리가 한계에 정확히 붙었다 — IK 가 잘라낸 것이다.".format(
            len(lim["pinned"])))
        out.append("       그 자세는 목표를 못 맞춘다 (reach_err 로 확인)")

    if spd["form_segs"]:
        out.append("  이송 유지 (성형 {}구간, feed {:.0f} mm/s):".format(
            spd["form_segs"], spd["feed"]))
        out.append("    필요 최대: 정격의 {:.1f}%  ({} 구간 {})".format(
            spd["worst_rated"] * 100.0, spd["worst_joint"], spd["worst_at"]))
        out.append("    최소 오버라이드 {:.1f}%  (지금 {:.0f}%)".format(
            spd["min_override"] * 100.0, spd["joint_scale"] * 100.0))
        if spd["over_rated"]:
            out.append("    ** 정격 초과 {}구간 — 그 feed 는 기구적으로 불가능하다".format(
                spd["over_rated"]))
        elif spd["over_override"]:
            out.append("    ** 오버라이드가 낮아 {}구간에서 feed 를 못 낸다.".format(
                spd["over_override"]))
            out.append("       시간 모델이 느린 쪽을 택하므로 화면에는 안 드러난다")
        else:
            out.append("    여유 있다 — feed 를 관절이 따라간다")
    else:
        out.append("  이송 유지: 타겟점이 없어 판정하지 못했다")

    out.append("  자세 연속성:")
    out.append("    최대 변화 {:.1f}deg ({} 구간 {})  {:.2f} deg/mm".format(
        con["worst"], con["worst_joint"], con["worst_at"],
        con["worst_per_mm"]))
    if con["over"]:
        out.append("    ** {}deg 초과 {}구간 — 손목이 뒤집혔거나 IK 해가 튀었다".format(
            WARN_JUMP_DEG, con["over"]))
    else:
        out.append("    튀는 구간 없음 (기준 {:.0f}deg)".format(WARN_JUMP_DEG))

    out.append("  특이점:")
    out.append("    손목 |j5| 최소 {:.1f}deg (포즈 {})  <- 0 에서 j4/j6 겹침".format(
        sng["j5_min"], sng["j5_at"]))
    out.append("    어깨 j1축 수평거리 최소 {:.0f} mm (포즈 {})".format(
        sng["shoulder_min"], sng["shoulder_at"]))
    out.append("    팔 뻗음 {:.0f} ~ {:.0f} mm  (정격 {:.0f} 의 {:.0f}%)".format(
        sng["reach_min"], sng["reach_max"], RATED_REACH_MM, sng["reach_pct"]))

    if res["problems"]:
        out.append("  ** 문제: " + " / ".join(res["problems"]))
    elif res["tight"]:
        out.append("  아슬아슬: " + " / ".join(res["tight"]))
    else:
        out.append("  기구적으로 걸리는 것 없음")
    out.append("  ** 가감속을 무시한다 — 속도 판정은 낙관적이다.")
    out.append("     자기 간섭·축2/3 연동범위·토크는 보지 않는다")
    return "\n".join(out)

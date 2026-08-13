#! python 3
# -*- coding: utf-8 -*-
"""mechanics.py 테스트 — 가동범위·이송유지·연속성·특이점.

    python adaptive_mold/tools/run_tests_via_bridge.py mechanics

**요점은 "여유가 형상을 재고 있는가"다.** 이진 판정만 맞으면 기준값을 바꿨을 때
같이 흔들려도 눈치채지 못한다. 그래서 여유가 **얼마인지**를 고정한다.
"""

import os
import sys

import Rhino.Geometry as rg

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, _SRC)

_norm = os.path.normcase(_SRC)
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb            # noqa: E402
import mechanics as mc        # noqa: E402


WHOA = mc.WARN_JUMP_DEG + 1.0     # 튐 기준을 넘는 값


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def pose(**kw):
    p = dict((j, 0.0) for j in rb.JOINT_NAMES)
    p.update(kw)
    return p


def line_points(n, step):
    """x축 위 등간격 점 n개."""
    return [rg.Point3d(i * step, 0.0, 0.0) for i in range(n)]


# ── 1. 가동범위 ─────────────────────────────────────────

def test_margin_is_distance_to_nearest_end():
    # j1 은 -170~170. 사용 [-20, 30] 이면 여유는 170-30 = 140
    res = mc.limit_margins([pose(j1=-20.0), pose(j1=30.0)])
    d = res["joints"]["j1"]
    assert close(d["used_lo"], -20.0), d
    assert close(d["used_hi"], 30.0), d
    assert close(d["margin"], 140.0), d
    assert d["tight_end"] == "hi", d


def test_margin_picks_the_tight_end():
    # j2 는 -65~85. 사용 [-60, 0] 이면 아래쪽 여유 5 가 가깝다
    res = mc.limit_margins([pose(j2=-60.0), pose(j2=0.0)])
    d = res["joints"]["j2"]
    assert close(d["margin"], 5.0), d
    assert d["tight_end"] == "lo", d


def test_worst_joint_is_reported():
    res = mc.limit_margins([pose(j2=80.0, j1=0.0)])
    assert res["worst_joint"] == "j2", res["worst_joint"]
    assert close(res["worst"], 5.0), res["worst"]


def test_over_limit_is_negative_not_clamped():
    # 한계를 넘은 포즈를 넣으면 음수로 보고해야 한다. 조용히 자르면
    # "괜찮다"로 읽힌다.
    res = mc.limit_margins([pose(j2=95.0)])
    assert res["joints"]["j2"]["margin"] < 0.0, res["joints"]["j2"]
    assert close(res["joints"]["j2"]["margin"], -10.0), res["joints"]["j2"]


def test_pinned_joints_are_found():
    res = mc.limit_margins([pose(j5=130.0), pose(j5=0.0)])
    assert (0, "j5") in res["pinned"], res["pinned"]
    assert len(res["pinned"]) == 1, res["pinned"]


def test_empty_poses_gives_no_verdict():
    res = mc.limit_margins([])
    assert res["worst"] is None, res
    assert res["joints"] == {}, res


# ── 2. 이송 유지 ────────────────────────────────────────

def test_speed_ratio_arithmetic():
    # 100 mm 를 feed 50 mm/s → 2 초. j1 이 50deg 움직이면 25 deg/s 필요.
    # j1 정격 100 deg/s → 25%.
    poses = [pose(), pose(j1=50.0)]
    pts = line_points(2, 100.0)
    res = mc.feed_demand(poses, pts, ["form", "form"], feed=50.0,
                         joint_scale=1.0)
    assert res["form_segs"] == 1, res
    assert close(res["worst_rated"], 0.25, 1e-9), res["worst_rated"]
    assert res["worst_joint"] == "j1", res
    assert res["over_rated"] == 0, res


def test_min_override_is_the_rated_ratio():
    """feed 를 유지하는 최소 오버라이드 = 정격 대비 필요 비율.

    이 값보다 낮게 돌리면 롤러가 feed 를 못 낸다.
    """
    poses = [pose(), pose(j1=50.0)]
    pts = line_points(2, 100.0)
    res = mc.feed_demand(poses, pts, None, feed=50.0, joint_scale=0.25)
    assert close(res["min_override"], 0.25, 1e-9), res["min_override"]
    # 오버라이드 25% = 필요치와 정확히 같다 → 초과 아님
    assert res["over_override"] == 0, res
    assert close(res["worst_override"], 1.0, 1e-9), res["worst_override"]


def test_override_shortfall_is_separate_from_rated():
    """오버라이드 부족과 정격 초과는 다른 문제다.

    섞으면 고칠 수 있는 것(설정)과 고칠 수 없는 것(기구)이 구분되지 않는다.
    """
    poses = [pose(), pose(j1=50.0)]
    pts = line_points(2, 100.0)
    res = mc.feed_demand(poses, pts, None, feed=50.0, joint_scale=0.1)
    assert res["over_rated"] == 0, res          # 기구적으로는 여유
    assert res["over_override"] == 1, res       # 설정으로는 못 냄


def test_rated_excess_is_flagged():
    # 10 mm 를 feed 50 → 0.2 초에 j1 50deg = 250 deg/s > 정격 100
    poses = [pose(), pose(j1=50.0)]
    pts = line_points(2, 10.0)
    res = mc.feed_demand(poses, pts, None, feed=50.0, joint_scale=1.0)
    assert res["over_rated"] == 1, res
    assert res["worst_rated"] > 1.0, res["worst_rated"]


def test_air_segments_are_excluded():
    """공중 이동은 관절 속도가 지배하는 것이 정상이다 — 세면 거짓 경보가 난다."""
    poses = [pose(), pose(j1=50.0)]
    pts = line_points(2, 10.0)
    res = mc.feed_demand(poses, pts, ["form", "air"], feed=50.0,
                         joint_scale=1.0)
    assert res["form_segs"] == 0, res
    assert res["over_rated"] == 0, res


def test_kind_index_matches_playback():
    """구간 i 의 종류는 kinds[i+1] 이다 (playback.RobotPhase._kind 와 같다).

    한 칸 어긋나면 성형/공중 판정이 통째로 밀린다.
    """
    poses = [pose(), pose(j1=50.0), pose(j1=100.0)]
    pts = line_points(3, 100.0)
    res = mc.feed_demand(poses, pts, ["air", "air", "form"], feed=50.0,
                         joint_scale=1.0)
    # 구간0 -> kinds[1]="air" 제외, 구간1 -> kinds[2]="form" 포함
    assert res["form_segs"] == 1, res
    assert res["worst_at"] == 1, res


def test_no_points_means_no_verdict():
    res = mc.feed_demand([pose(), pose(j1=10.0)], None, None)
    assert res["form_segs"] == 0, res
    assert res["min_override"] == 0.0, res


def test_zero_distance_segment_skipped():
    """제자리 구간은 나누면 0 으로 나눈다 — 건너뛴다."""
    poses = [pose(), pose(j1=5.0)]
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(0, 0, 0)]
    res = mc.feed_demand(poses, pts, None, feed=50.0)
    assert res["form_segs"] == 0, res


# ── 3. 자세 연속성 ──────────────────────────────────────

def test_worst_jump_and_joint():
    poses = [pose(), pose(j3=5.0), pose(j3=5.0, j5=40.0)]
    res = mc.continuity(poses)
    assert close(res["worst"], 40.0), res["worst"]
    assert res["worst_joint"] == "j5", res
    assert res["worst_at"] == 1, res
    assert res["segs"] == 2, res


def test_jump_threshold_counts():
    poses = [pose(), pose(j3=WHOA), pose(j3=WHOA + 5.0)]
    res = mc.continuity(poses)
    assert res["over"] == 1, res


def test_per_mm_finds_the_flip():
    """절대 각도가 아니라 deg/mm 가 뒤집힘을 잡는다.

    큰 각도가 큰 이동에서 나오면 정상이고, 작은 이동에서 나오면 튄 것이다.
    """
    poses = [pose(), pose(j4=20.0), pose(j4=40.0)]
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(101, 0, 0)]
    res = mc.continuity(poses, pts)
    assert close(res["worst"], 20.0), res["worst"]   # 두 구간 같은 각도
    assert res["per_mm_at"] == 1, res                # 이동이 작은 쪽이 튄 것
    assert close(res["worst_per_mm"], 20.0), res["worst_per_mm"]


def test_single_pose_has_no_segments():
    res = mc.continuity([pose()])
    assert res["segs"] == 0, res
    assert res["worst_at"] == -1, res


# ── 4. 특이점 ───────────────────────────────────────────

def test_wrist_singularity_distance():
    res = mc.singularity([pose(j5=40.0), pose(j5=-3.0), pose(j5=90.0)])
    assert close(res["j5_min"], 3.0), res["j5_min"]
    assert res["j5_at"] == 1, res
    assert res["j5_near"] == 1, res       # |j5| < 10 인 것 하나


def test_home_pose_is_fully_extended_forward():
    """영각 자세는 팔이 앞으로 곧게 뻗은 형상이다.

    j2 피벗에서 TCP 까지 = j5 x(1.6) - j2 x(0.32) + 툴(0.34) 를 넘어야 한다.
    구체적 값이 아니라 **부호와 크기 자리수**를 고정한다 — 매핑이 틀어지면
    여기가 먼저 깨진다.
    """
    res = mc.singularity([pose()])
    assert res["reach_max"] > 1500.0, res["reach_max"]
    assert res["reach_max"] < mc.RATED_REACH_MM, res["reach_max"]
    assert res["reach_pct"] > 40.0, res["reach_pct"]
    # 앞으로 뻗었으므로 j1 축과의 수평거리가 크다 = 어깨 특이점이 아니다
    assert res["shoulder_min"] > 1000.0, res["shoulder_min"]
    assert res["shoulder_near"] == 0, res


def test_shoulder_singularity_when_tcp_over_axis():
    """j2 를 접어 TCP 를 j1 축 위로 올리면 어깨 특이점에 가까워진다."""
    far = mc.singularity([pose()])
    folded = mc.singularity([pose(j2=-65.0, j3=70.0, j5=60.0)])
    assert folded["shoulder_min"] < far["shoulder_min"], (folded, far)


# ── 5. 통합 ─────────────────────────────────────────────

def test_check_reports_clean_path():
    poses = [pose(j2=20.0, j3=-20.0, j5=60.0),
             pose(j2=22.0, j3=-22.0, j5=60.0)]
    pts = line_points(2, 100.0)
    res = mc.check(poses, pts, ["form", "form"], feed=50.0, joint_scale=0.25)
    assert res["problems"] == [], res["problems"]
    assert res["poses"] == 2, res


def test_check_flags_over_limit():
    res = mc.check([pose(j2=95.0)], None, None)
    assert any("가동범위" in p for p in res["problems"]), res["problems"]


def test_check_separates_tight_from_problem():
    """아슬아슬(7deg 여유)은 문제가 아니다. 섞으면 실제 초과가 묻힌다.

    j5=60 을 같이 준다 — **영각 포즈는 j5=0 이라 손목 특이점이다**(이 테스트를
    처음 쓸 때 걸렸다). HOME_POSE 를 검사에 그냥 넣으면 특이점 경보가 뜬다.
    """
    res = mc.check([pose(j2=78.0, j5=60.0)], None, None)
    assert res["problems"] == [], res["problems"]
    assert any("j2" in t for t in res["tight"]), res["tight"]


def test_report_is_text_and_mentions_limits():
    poses = [pose(j2=20.0, j5=60.0), pose(j2=22.0, j5=60.0)]
    txt = mc.report(mc.check(poses, line_points(2, 100.0), None))
    assert "가동범위" in txt, txt[:200]
    assert "특이점" in txt, txt[:200]
    assert "가감속" in txt, txt[-300:]     # 한계를 반드시 같이 적는다


def test_report_survives_empty():
    txt = mc.report(mc.check([], None, None))
    assert "포즈가 없다" in txt, txt


TESTS = [
    test_margin_is_distance_to_nearest_end,
    test_margin_picks_the_tight_end,
    test_worst_joint_is_reported,
    test_over_limit_is_negative_not_clamped,
    test_pinned_joints_are_found,
    test_empty_poses_gives_no_verdict,
    test_speed_ratio_arithmetic,
    test_min_override_is_the_rated_ratio,
    test_override_shortfall_is_separate_from_rated,
    test_rated_excess_is_flagged,
    test_air_segments_are_excluded,
    test_kind_index_matches_playback,
    test_no_points_means_no_verdict,
    test_zero_distance_segment_skipped,
    test_worst_jump_and_joint,
    test_jump_threshold_counts,
    test_per_mm_finds_the_flip,
    test_single_pose_has_no_segments,
    test_wrist_singularity_distance,
    test_home_pose_is_fully_extended_forward,
    test_shoulder_singularity_when_tcp_over_axis,
    test_check_reports_clean_path,
    test_check_flags_over_limit,
    test_check_separates_tight_from_problem,
    test_report_is_text_and_mentions_limits,
    test_report_survives_empty,
]


def run_all():
    log = []
    ok = 0
    bad = 0
    for fn in TESTS:
        try:
            fn()
            log.append("PASS: " + fn.__name__)
            ok += 1
        except Exception as ex:
            log.append("FAIL: {} -> {}: {}".format(
                fn.__name__, type(ex).__name__, ex))
            bad += 1
    log.append("")
    log.append("{}개 통과 / {}개 실패".format(ok, bad))
    return ok, bad, log


if __name__ == "__main__":
    _ok, _bad, _log = run_all()
    with open(os.path.join(HERE, "_mechanics_log.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

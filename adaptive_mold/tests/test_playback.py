#! python 3
# -*- coding: utf-8 -*-
"""playback.py 테스트 — 재생 타임라인의 시간 모델.

Rhino 환경에서 실행해야 합니다 (playback → robot → Rhino.Geometry 의존).

    python adaptive_mold/tools/run_tests_via_bridge.py playback

숫자를 손으로 계산해 둔 케이스로 확인한다. "애니메이션이 그럴듯하게 움직인다"는
근거가 되지 않으므로 — 배속이 틀려도 화면은 똑같이 그럴듯하다.
"""

import os
import sys

import Rhino.Geometry as rg

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import robot as rb           # noqa: E402
import playback as pb        # noqa: E402


TOL = 1e-9


def close(a, b, tol=TOL):
    return abs(a - b) <= tol


def _pose(**kw):
    p = dict((j, 0.0) for j in rb.JOINT_NAMES)
    p.update(kw)
    return p


def _bases(n):
    return [rg.Point3d(i * 200.0, 0.0, 0.0) for i in range(n)]


# ── 핀 구간 ─────────────────────────────────────────────

def test_pin_duration_is_longest_travel():
    """구간 길이는 가장 많이 움직이는 핀이 정한다 — 합이 아니다."""
    p = pb.PinPhase(_bases(3), [0.0, 0.0, 0.0], [100.0, 50.0, 0.0], speed=50.0)
    assert close(p.duration, 2.0), p.duration
    print("PASS: test_pin_duration_is_longest_travel")


def test_pin_heights_mid_and_clamp():
    """도착한 핀은 목표에서 멈춘다. 넘어가지 않는다."""
    p = pb.PinPhase(_bases(3), [0.0, 0.0, 0.0], [100.0, 50.0, 0.0], speed=50.0)
    h = p.heights_at(1.0)
    assert close(h[0], 50.0), h
    assert close(h[1], 50.0), h        # 정확히 도착
    assert close(h[2], 0.0), h         # 행정 0
    h2 = p.heights_at(10.0)            # 구간을 한참 넘겨도
    assert close(h2[0], 100.0), h2
    assert close(h2[1], 50.0), h2
    print("PASS: test_pin_heights_mid_and_clamp")


def test_pin_descends():
    """내려가는 핀도 부호가 맞아야 한다 (home 이 목표보다 높은 경우)."""
    p = pb.PinPhase(_bases(1), [200.0], [100.0], speed=50.0)
    assert close(p.duration, 2.0), p.duration
    assert close(p.heights_at(1.0)[0], 150.0), p.heights_at(1.0)
    assert close(p.heights_at(5.0)[0], 100.0), p.heights_at(5.0)
    print("PASS: test_pin_descends")


def test_pin_arrived_count():
    p = pb.PinPhase(_bases(3), [0.0, 0.0, 0.0], [100.0, 50.0, 0.0], speed=50.0)
    assert p.arrived_at(0.0) == 1, p.arrived_at(0.0)     # 행정 0인 핀
    assert p.arrived_at(1.0) == 2, p.arrived_at(1.0)
    assert p.arrived_at(2.0) == 3, p.arrived_at(2.0)
    print("PASS: test_pin_arrived_count")


# ── 관절 시간 ───────────────────────────────────────────

def test_joint_time_is_slowest_axis():
    """가장 오래 걸리는 축이 구간 시간을 정한다."""
    a = _pose()
    b = _pose(j1=100.0, j6=190.0)
    # j1: 100 / (100*1.0) = 1.0 s,  j6: 190 / (190*1.0) = 1.0 s
    assert close(pb.joint_time(a, b, 1.0), 1.0), pb.joint_time(a, b, 1.0)
    c = _pose(j1=100.0, j6=380.0)   # j6 이 2.0 s 로 지배
    assert close(pb.joint_time(a, c, 1.0), 2.0), pb.joint_time(a, c, 1.0)
    print("PASS: test_joint_time_is_slowest_axis")


def test_joint_scale_slows_down():
    """속도 오버라이드 25% → 4배 시간."""
    a, b = _pose(), _pose(j1=100.0)
    assert close(pb.joint_time(a, b, 0.25), 4.0), pb.joint_time(a, b, 0.25)
    print("PASS: test_joint_scale_slows_down")


# ── 로봇 구간: 무엇이 시간을 지배하는가 ─────────────────

def _form_phase(dj1, dist, feed=50.0, scale=0.25, kind="form"):
    poses = [_pose(), _pose(j1=dj1)]
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(dist, 0, 0)]
    kinds = [kind, kind]
    return pb.RobotPhase(poses, kinds=kinds, points=pts,
                         feed=feed, joint_scale=scale)


def test_form_feed_dominates():
    """관절은 여유가 있고 이송이 느리면 이송이 시간을 정한다."""
    # 관절: 1 deg / (100*0.25) = 0.04 s,  이송: 100/50 = 2.0 s
    r = _form_phase(1.0, 100.0)
    assert r.dt_kind == ["feed"], r.dt_kind
    assert close(r.duration, 2.0), r.duration
    print("PASS: test_form_feed_dominates")


def test_form_joint_dominates():
    """이송이 빨라도 로봇이 못 따라가면 로봇이 시간을 정한다."""
    # 관절: 90 / (100*0.25) = 3.6 s,  이송: 100/50 = 2.0 s
    r = _form_phase(90.0, 100.0)
    assert r.dt_kind == ["joint"], r.dt_kind
    assert close(r.duration, 3.6), r.duration
    print("PASS: test_form_joint_dominates")


def test_air_ignores_feed():
    """공중 이동은 이송 속도와 무관하다 — 판재를 안 누르고 있다."""
    r = _form_phase(1.0, 100.0, kind="link")
    assert r.dt_kind == ["joint"], r.dt_kind
    assert close(r.duration, 0.04), r.duration
    print("PASS: test_air_ignores_feed")


def test_kind_of_destination_decides():
    """구간의 종류는 **도착 타겟**이 정한다.

    approach 다음이 form 이면 그 구간은 아직 공중이다 — 도착점이 form 이므로
    form 으로 센다. 경계를 어느 쪽으로 붙일지는 임의 선택이지만, 첫 접촉
    구간을 이송 속도로 다루는 편이 안전하다(빠르게 내려꽂지 않는다).
    """
    poses = [_pose(), _pose(j1=1.0), _pose(j1=2.0)]
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(200, 0, 0)]
    r = pb.RobotPhase(poses, kinds=["approach", "form", "retract"],
                      points=pts, feed=50.0, joint_scale=0.25)
    assert r.dt_kind == ["feed", "joint"], r.dt_kind
    print("PASS: test_kind_of_destination_decides")


# ── 샘플링 ──────────────────────────────────────────────

def test_robot_sample_boundaries():
    poses = [_pose(), _pose(j1=1.0), _pose(j1=2.0)]
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(200, 0, 0)]
    r = pb.RobotPhase(poses, kinds=["form", "form", "form"], points=pts,
                      feed=50.0, joint_scale=0.25)
    assert close(r.duration, 4.0), r.duration          # 2.0 + 2.0

    p, seg, f = r.sample(0.0)
    assert seg == 0 and close(f, 0.0) and close(p["j1"], 0.0), (seg, f, p["j1"])

    p, seg, f = r.sample(1.0)
    assert seg == 0 and close(f, 0.5) and close(p["j1"], 0.5), (seg, f, p["j1"])

    p, seg, f = r.sample(2.0)                          # 정확히 경계
    assert seg == 1 and close(f, 0.0) and close(p["j1"], 1.0), (seg, f, p["j1"])

    p, seg, f = r.sample(99.0)                         # 끝을 넘겨도 마지막 자세
    assert close(p["j1"], 2.0), p["j1"]
    print("PASS: test_robot_sample_boundaries")


def test_lerp_pose():
    a, b = _pose(), _pose(j1=10.0, j5=-20.0)
    m = pb.lerp_pose(a, b, 0.25)
    assert close(m["j1"], 2.5), m["j1"]
    assert close(m["j5"], -5.0), m["j5"]
    assert pb.lerp_pose(a, b, -1.0)["j1"] == 0.0
    assert pb.lerp_pose(a, b, 2.0)["j1"] == 10.0
    print("PASS: test_lerp_pose")


def test_poses_from_flat():
    """AMv1 Robot 은 6개씩 이어 붙인 평탄 목록을 낸다."""
    flat = [1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16]
    ps = pb.poses_from_flat(flat)
    assert len(ps) == 2, len(ps)
    assert close(ps[0]["j1"], 1.0) and close(ps[0]["j6"], 6.0), ps[0]
    assert close(ps[1]["j1"], 11.0) and close(ps[1]["j6"], 16.0), ps[1]
    print("PASS: test_poses_from_flat")


# ── 타임라인 전체 ───────────────────────────────────────

def _timeline():
    return pb.build(
        pin_bases=_bases(3), pin_h_start=[0.0] * 3,
        pin_h_end=[100.0, 50.0, 0.0], pin_speed=50.0,
        poses=[_pose(), _pose(j1=1.0), _pose(j1=91.0)],
        kinds=["form", "form", "form"],
        points=[rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0),
                rg.Point3d(200, 0, 0)],
        feed=50.0, joint_scale=0.25, dwell=1.0)


def test_timeline_total():
    """핀 2.0 + 정지 1.0 + 로봇 (2.0 이송 + 3.6 관절) = 8.6"""
    tl = _timeline()
    assert close(tl.t_pins, 2.0), tl.t_pins
    assert close(tl.robot.duration, 5.6), tl.robot.duration
    assert close(tl.duration, 8.6), tl.duration
    print("PASS: test_timeline_total")


def test_timeline_phases():
    tl = _timeline()
    assert tl.sample(0.0)["phase"] == "pins"
    assert tl.sample(1.9)["phase"] == "pins"
    assert tl.sample(2.0)["phase"] == "dwell"
    assert tl.sample(2.9)["phase"] == "dwell"
    assert tl.sample(3.0)["phase"] == "robot"
    assert tl.sample(8.5)["phase"] == "robot"
    assert tl.sample(8.6)["phase"] == "done"
    assert tl.sample(99.0)["phase"] == "done"
    print("PASS: test_timeline_phases")


def test_timeline_pins_stay_up_during_robot():
    """로봇이 도는 동안 핀은 목표 높이에 그대로 있어야 한다.

    heights_at(t) 에 전체 t 를 그대로 넘기면 문제없지만, 구간 시간을 잘못
    자르면 핀이 계속 올라가 버린다.
    """
    tl = _timeline()
    h = tl.sample(7.0)["heights"]
    assert close(h[0], 100.0) and close(h[1], 50.0), h
    print("PASS: test_timeline_pins_stay_up_during_robot")


def test_timeline_progress_monotonic():
    tl = _timeline()
    prev = -1.0
    t = 0.0
    while t <= tl.duration + 1.0:
        p = tl.sample(t)["progress"]
        assert p >= prev - TOL, (t, p, prev)
        assert 0.0 <= p <= 1.0, (t, p)
        prev = p
        t += 0.1
    print("PASS: test_timeline_progress_monotonic")


def test_pins_only_timeline():
    """로봇 없이 핀만 있어도 동작해야 한다 (배선 도중 상태)."""
    tl = pb.build(pin_bases=_bases(2), pin_h_start=[0.0, 0.0],
                  pin_h_end=[100.0, 0.0], pin_speed=50.0, dwell=0.0)
    assert close(tl.duration, 2.0), tl.duration
    assert tl.sample(1.0)["phase"] == "pins"
    assert tl.sample(2.0)["phase"] == "done"
    assert tl.sample(1.0)["pose"] is None
    print("PASS: test_pins_only_timeline")


TESTS = [
    test_pin_duration_is_longest_travel,
    test_pin_heights_mid_and_clamp,
    test_pin_descends,
    test_pin_arrived_count,
    test_joint_time_is_slowest_axis,
    test_joint_scale_slows_down,
    test_form_feed_dominates,
    test_form_joint_dominates,
    test_air_ignores_feed,
    test_kind_of_destination_decides,
    test_robot_sample_boundaries,
    test_lerp_pose,
    test_poses_from_flat,
    test_timeline_total,
    test_timeline_phases,
    test_timeline_pins_stay_up_during_robot,
    test_timeline_progress_monotonic,
    test_pins_only_timeline,
]


def run_all():
    """(통과, 실패, 로그) — Rhino 콘솔은 밖에서 안 보이므로 로그를 돌려준다."""
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
    _out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_playback_log.txt")
    with open(_out, "w", encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

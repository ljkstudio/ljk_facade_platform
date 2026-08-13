#! python 3
# -*- coding: utf-8 -*-
"""robot.base_plane_from / resolve_base_plane 테스트.

    python adaptive_mold/tools/run_tests_via_bridge.py robot_base

**우선순위와 투영이 요점이다.** 베이스가 조용히 다른 곳에 잡히면 로봇이
계산된 위치와 다른 곳에 그려지고, 화면은 그럴듯해서 틀린 줄 모른다.
"""

import math
import os
import sys

import Rhino.Geometry as rg

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, _SRC)

# 모듈 캐시를 비운다 (test_playback.py 의 같은 주석 참조)
_norm = os.path.normcase(_SRC)
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb   # noqa: E402


TOL = 1e-9


def close(a, b, tol=1e-7):
    return abs(a - b) <= tol


def _targets():
    """중심이 (1000, 500, 200) 인 타겟 평면 넷."""
    pts = [rg.Point3d(500, 0, 200), rg.Point3d(1500, 0, 200),
           rg.Point3d(500, 1000, 200), rg.Point3d(1500, 1000, 200)]
    return [rg.Plane(p, rg.Vector3d.ZAxis) for p in pts]


# ── 선만 ────────────────────────────────────────────────

def test_line_alone_gives_origin_and_direction():
    ln = rg.Line(rg.Point3d(-2000, 300, 0), rg.Point3d(0, 300, 0))
    pl, note = rb.base_plane_from(line=ln)
    assert pl.Origin.DistanceTo(rg.Point3d(-2000, 300, 0)) < TOL, pl.Origin
    assert close(pl.XAxis.X, 1.0) and close(pl.XAxis.Y, 0.0), pl.XAxis
    assert note == "", note
    print("PASS: test_line_alone_gives_origin_and_direction")


def test_direction_is_unitized_and_y_is_left():
    """+Y 는 +X 를 Z 기준 90도 돈 방향이어야 한다 (오른손 좌표계)."""
    ln = rg.Line(rg.Point3d(0, 0, 0), rg.Point3d(300, 300, 0))
    pl, _ = rb.base_plane_from(line=ln)
    assert close(pl.XAxis.Length, 1.0), pl.XAxis.Length
    assert close(pl.YAxis.X, -pl.XAxis.Y) and close(pl.YAxis.Y, pl.XAxis.X), (
        pl.XAxis, pl.YAxis)
    assert close(pl.ZAxis.Z, 1.0), pl.ZAxis
    print("PASS: test_direction_is_unitized_and_y_is_left")


# ── 점 + 선 ─────────────────────────────────────────────

def test_point_wins_as_origin():
    """점이 있으면 원점은 점이고, 선은 방향만 준다."""
    ln = rg.Line(rg.Point3d(-2000, 0, 0), rg.Point3d(-2000, 900, 0))
    pt = rg.Point3d(-1400, 500, 0)
    pl, _ = rb.base_plane_from(point=pt, line=ln)
    assert pl.Origin.DistanceTo(pt) < TOL, pl.Origin
    assert close(pl.XAxis.Y, 1.0), pl.XAxis      # 선은 +Y 방향
    print("PASS: test_point_wins_as_origin")


def test_point_only_faces_targets():
    """점만 주면 타겟 중심을 향한다."""
    pt = rg.Point3d(-1400, 500, 0)
    pl, note = rb.base_plane_from(point=pt, targets=_targets())
    to_center = rg.Vector3d(rg.Point3d(1000, 500, 200) - pt)
    to_center.Z = 0.0
    to_center.Unitize()
    assert close(pl.XAxis.X, to_center.X) and close(pl.XAxis.Y, to_center.Y), (
        pl.XAxis, to_center)
    assert "타겟 중심" in note, note
    print("PASS: test_point_only_faces_targets")


def test_point_only_without_targets_uses_world_x():
    pl, note = rb.base_plane_from(point=rg.Point3d(0, 0, 0))
    assert close(pl.XAxis.X, 1.0), pl.XAxis
    assert "월드 X" in note, note
    print("PASS: test_point_only_without_targets_uses_world_x")


# ── 투영 ────────────────────────────────────────────────

def test_sloped_line_is_projected_and_reported():
    """기울어진 선을 그어도 로봇은 눕지 않는다 — 그리고 말해준다.

    원격 뷰포트에서 선을 그으면 의도와 달리 기울어지기 쉽다. 그대로 받으면
    로봇이 넘어진 자세로 계산된다.
    """
    ln = rg.Line(rg.Point3d(0, 0, 0), rg.Point3d(1000, 0, 800))
    pl, note = rb.base_plane_from(line=ln)
    assert close(pl.ZAxis.Z, 1.0), pl.ZAxis
    assert close(pl.XAxis.Z, 0.0), pl.XAxis
    assert "투영" in note, note
    print("PASS: test_sloped_line_is_projected_and_reported")


def test_vertical_line_falls_back():
    """수직선은 방향을 못 준다 — 조용히 이상한 평면을 만들지 않는다."""
    ln = rg.Line(rg.Point3d(0, 0, 0), rg.Point3d(0, 0, 1000))
    pl, note = rb.base_plane_from(line=ln)
    assert pl is not None
    assert close(pl.XAxis.X, 1.0), pl.XAxis
    assert "수직" in note, note
    print("PASS: test_vertical_line_falls_back")


def test_nothing_gives_none():
    pl, note = rb.base_plane_from()
    assert pl is None, pl
    print("PASS: test_nothing_gives_none")


# ── 여러 타입 받기 ──────────────────────────────────────

def test_accepts_curve_and_vector():
    """Line 힌트를 걸어도 Curve·Vector 가 들어올 수 있다."""
    crv = rg.LineCurve(rg.Point3d(-500, 0, 0), rg.Point3d(-500, 400, 0))
    pl, _ = rb.base_plane_from(line=crv)
    assert pl.Origin.DistanceTo(rg.Point3d(-500, 0, 0)) < TOL, pl.Origin
    assert close(pl.XAxis.Y, 1.0), pl.XAxis

    pl2, _ = rb.base_plane_from(point=rg.Point3d(0, 0, 0),
                                line=rg.Vector3d(0, -1, 0))
    assert close(pl2.XAxis.Y, -1.0), pl2.XAxis
    print("PASS: test_accepts_curve_and_vector")


# ── 우선순위 ────────────────────────────────────────────

def test_priority_plane_beats_point_line():
    given = rg.Plane(rg.Point3d(7, 8, 9), rg.Vector3d.YAxis,
                     rg.Vector3d.ZAxis)
    pl, src = rb.resolve_base_plane(
        robot_base=given, base_pt=rg.Point3d(0, 0, 0),
        base_dir=rg.Line(rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0)),
        targets=_targets())
    assert pl.Origin.DistanceTo(rg.Point3d(7, 8, 9)) < TOL, pl.Origin
    assert "평면" in src, src
    print("PASS: test_priority_plane_beats_point_line")


def test_priority_point_line_beats_auto():
    pt = rg.Point3d(-1234, 5, 0)
    pl, src = rb.resolve_base_plane(base_pt=pt, targets=_targets())
    assert pl.Origin.DistanceTo(pt) < TOL, pl.Origin
    assert src.startswith("점"), src
    print("PASS: test_priority_point_line_beats_auto")


def test_priority_auto_when_nothing():
    """아무것도 없으면 자동 기본값 — 타겟 중심에서 -X 로 1900."""
    pl, src = rb.resolve_base_plane(targets=_targets())
    assert pl.Origin.DistanceTo(rg.Point3d(1000 - 1900.0, 500, 0)) < 1e-6, pl.Origin
    assert src == "자동", src
    print("PASS: test_priority_auto_when_nothing")


def test_auto_matches_default_helper():
    """resolve 가 쓰는 자동값이 default_base_plane 과 같아야 한다."""
    t = _targets()
    a, _ = rb.resolve_base_plane(targets=t)
    b = rb.default_base_plane(t)
    assert a.Origin.DistanceTo(b.Origin) < TOL, (a.Origin, b.Origin)
    print("PASS: test_auto_matches_default_helper")


TESTS = [
    test_line_alone_gives_origin_and_direction,
    test_direction_is_unitized_and_y_is_left,
    test_point_wins_as_origin,
    test_point_only_faces_targets,
    test_point_only_without_targets_uses_world_x,
    test_sloped_line_is_projected_and_reported,
    test_vertical_line_falls_back,
    test_nothing_gives_none,
    test_accepts_curve_and_vector,
    test_priority_plane_beats_point_line,
    test_priority_point_line_beats_auto,
    test_priority_auto_when_nothing,
    test_auto_matches_default_helper,
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
    with open(os.path.join(HERE, "_robot_base_log.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

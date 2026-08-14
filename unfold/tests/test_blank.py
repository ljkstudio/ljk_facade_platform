# -*- coding: utf-8 -*-
"""blank.py 테스트 — 과소재단 보증이 실제로 성립하는가.

**이 파일이 spec §3 의 유일한 주장을 지킨다.** 재단선이 평탄화 경계를 한 군데라도
침범하면 그 자리가 곧 과소재단이다.
"""

import math

import pytest

import blank as bk
import flatten as fl
import material as mt
import meshes
import topology as tp


SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
CW_SQUARE = list(reversed(SQUARE))


def poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        s += x0 * y1 - x1 * y0
    return 0.5 * s


def test_boundary_polyline_is_counterclockwise_whatever_the_input_order():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    assert poly_area(bk.boundary_polyline(uv, topo)) > 0
    mirrored = [(x, -y) for (x, y) in uv]
    assert poly_area(bk.boundary_polyline(mirrored, topo)) > 0


def test_offset_of_a_square_grows_by_exactly_the_distance():
    out = bk.offset(SQUARE, 10.0)
    assert len(out) == 4
    assert poly_area(out) == pytest.approx(120.0 * 120.0)


def test_offset_normalizes_clockwise_input():
    """방향을 안 맞추면 오프셋이 안쪽으로 간다 — 과소재단이 조용히 만들어진다."""
    assert poly_area(bk.offset(CW_SQUARE, 10.0)) == pytest.approx(120.0 * 120.0)


def test_every_source_point_ends_up_inside_with_the_promised_clearance():
    """보증 그 자체. 한 점이라도 밖에 있거나 여유가 모자라면 실패다."""
    verts, faces = meshes.sphere_cap(R=500.0, theta=0.6, nr=6, nt=20)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=80)
    allow = 15.0
    b = bk.build(res.uv, topo, allow_mm=allow, fit_tol=1.0)
    for pt in b.source:
        assert bk.point_in_polygon(pt, b.curve), "원 경계점 %r 이 재단선 밖에 있다" % (pt,)
    assert b.clearance_min >= allow - 1e-6


def test_feature_points_survive_simplification():
    """평활화가 코너를 뭉개면 재단물이 원래 패널이 아니게 된다."""
    dense = []
    for i in range(21):
        dense.append((100.0 * i / 20.0, 0.0))
    for i in range(1, 21):
        dense.append((100.0, 100.0 * i / 20.0))
    feats = bk.feature_indices(dense, feature_deg=30.0)
    simple = bk.simplify(dense, feats, tol=1.0)
    assert (100.0, 0.0) in simple, "직각 코너가 사라졌다"


def test_smooth_boundary_without_corners_still_produces_a_curve():
    """코너가 없는 원판 경계. 고정점이 하나뿐이면 구간이 자기 자신으로 닫혀
    결과가 빈 리스트가 된다 — 재단선이 조용히 사라지는 실패다."""
    circle = [(50.0 * math.cos(2 * math.pi * i / 40.0),
               50.0 * math.sin(2 * math.pi * i / 40.0)) for i in range(40)]
    feats = bk.feature_indices(circle, feature_deg=30.0)
    assert feats == [], "이 원은 코너가 없어야 검사가 성립한다"
    simple = bk.simplify(circle, feats, tol=0.5)
    assert len(simple) >= 3
    assert poly_area(simple) > 0


def test_simplify_removes_points_from_a_straight_run():
    straight = [(float(i), 0.0) for i in range(11)] + [(10.0, 5.0), (0.0, 5.0)]
    feats = bk.feature_indices(straight, feature_deg=30.0)
    simple = bk.simplify(straight, feats, tol=0.5)
    assert len(simple) < len(straight)


def test_self_intersection_is_detected_not_silently_accepted():
    """오목 모서리에서 오프셋이 겹칠 수 있다. v1 은 고치지 않고 **알린다**."""
    bowtie = [(0.0, 0.0), (100.0, 100.0), (100.0, 0.0), (0.0, 100.0)]
    assert bk.self_intersections(bowtie)
    assert bk.self_intersections(SQUARE) == []


def test_build_notes_say_what_was_done():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    b = bk.build(uv, topo, allow_mm=12.0, fit_tol=1.0)
    text = " ".join(b.notes)
    assert "12" in text and ("여유" in text or "오프셋" in text)


SPIKE = [(0.0, 0.0), (100.0, 0.0), (50.0, 400.0)]     # 꼭짓점 2 의 내각 약 14.2도


class _FakeTopo(object):
    """boundary_loops 만 있는 최소 대역품. blank 는 그것만 읽는다."""

    def __init__(self, loop):
        self.boundary_loops = [loop]


def test_a_sharp_corner_is_reported_because_the_offset_cannot_keep_its_promise():
    """마이터 제한이 걸리면 오프셋 정점의 수직거리가 dist·denom/MITER_MIN 로 줄어
    **약속한 거리보다 가까워진다.** 스파이크에서는 어떤 마이터/베벨로도 못 지킨다.

    v1 은 기하를 고치지 않고 재서 알린다. 그러니 최소한 **알아채기는** 해야 한다."""
    assert bk.sharp_corners(SPIKE) == [2]
    assert bk.sharp_corners(SQUARE) == []      # 90도는 걸리지 않는다

    dist = 10.0
    curve = bk.offset(SPIKE, dist)
    worst = min(bk.distance_to_polygon(p, curve) for p in SPIKE)
    assert worst < dist - 1e-6, \
        "제한이 걸렸는데 여유가 줄지 않았다 — 검사가 성립하지 않는다 (worst=%.4f)" % worst


def test_build_says_out_loud_when_the_clearance_falls_short():
    """보증이 깨지면 조용히 넘기지 않는다 — 이 모듈의 유일한 약속이다."""
    b = bk.build(SPIKE, _FakeTopo(list(range(len(SPIKE)))), allow_mm=10.0, fit_tol=0.0)
    text = " ".join(b.notes)
    assert "뾰족한 꼭짓점" in text
    assert "미달" in text
    assert b.clearance_min < 10.0


def test_a_blunt_shape_reports_neither_warning():
    """경고가 아무 데서나 뜨면 아무도 안 본다."""
    b = bk.build(SQUARE, _FakeTopo(list(range(len(SQUARE)))), allow_mm=10.0, fit_tol=0.0)
    text = " ".join(b.notes)
    assert "뾰족한 꼭짓점" not in text
    assert "미달" not in text
    assert b.clearance_min >= 10.0 - 1e-6


def test_clearance_is_measured_against_the_worst_point_not_the_average():
    verts, faces = meshes.plane_grid()
    topo = tp.build(len(verts), faces)
    uv = [(x, y) for (x, y, _z) in verts]
    b = bk.build(uv, topo, allow_mm=20.0, fit_tol=0.0)
    worst = min(bk.distance_to_polygon(p, b.curve) for p in b.source)
    assert b.clearance_min == pytest.approx(worst, abs=1e-9)

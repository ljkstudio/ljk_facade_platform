# -*- coding: utf-8 -*-
"""element.py 테스트 — 국소 좌표계가 길이를 보존하는가, cotangent 가 맞는가."""

import math

import element as el


def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


RIGHT = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 4.0, 0.0))   # 3-4-5 직각삼각형
EQUI = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, math.sqrt(3) / 2, 0.0))


def test_local_frame_preserves_all_three_edge_lengths():
    """이게 무너지면 '등거리'가 거짓이 되고 변형률 전체가 틀린다."""
    p = ((1.0, 2.0, 3.0), (4.0, 0.0, 5.0), (-2.0, 1.0, 7.0))
    loc = el.local_frame(*p)
    for i in range(3):
        j = (i + 1) % 3
        assert abs(dist(p[i], p[j]) - dist(loc[i], loc[j])) < 1e-9


def test_local_frame_puts_first_edge_on_x_axis():
    loc = el.local_frame(*RIGHT)
    assert loc[0] == (0.0, 0.0)
    assert abs(loc[1][0] - 3.0) < 1e-12 and abs(loc[1][1]) < 1e-12
    assert loc[2][1] > 0.0          # 세 번째 점은 항상 y > 0 (앞면 방향)


def test_area_matches_hand_computation():
    assert abs(el.area(*RIGHT) - 6.0) < 1e-12


def test_cotangent_of_equilateral_is_one_over_sqrt3():
    for c in el.cotangents(*EQUI):
        assert abs(c - 1.0 / math.sqrt(3)) < 1e-9


def test_cotangent_of_right_angle_is_zero():
    cots = el.cotangents(*RIGHT)
    assert abs(cots[0]) < 1e-12       # 정점 0 이 직각이다
    assert cots[1] > 0 and cots[2] > 0


def test_cotangent_is_invariant_under_rigid_motion():
    """좌표계를 바꿔도 각은 그대로여야 한다."""
    p = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.7, 1.3, 0.0))
    moved = tuple((x + 10.0, z - 4.0, y + 1.0) for (x, y, z) in p)   # 회전 + 평행이동
    a = el.cotangents(*p)
    b = el.cotangents(*moved)
    # 축을 바꾸면 정점 순서가 아니라 성분 대응만 바뀐다 — 집합으로 비교한다
    assert all(abs(x - y) < 1e-9 for x, y in zip(sorted(a), sorted(b)))


def test_prepare_returns_one_entry_per_face_with_usable_inverse():
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    faces = [(0, 1, 2), (0, 2, 3)]
    data = el.prepare(verts, faces)
    assert len(data) == 2
    for d in data:
        assert d.area > 0
        m00, m01, m10, m11 = d.inv
        assert abs(m00 * m11 - m01 * m10) > 0    # 특이하지 않다


def test_zero_area_triangle_raises():
    """퇴화 삼각형은 조용히 통과시키면 안 된다 — 역행렬이 폭발한다."""
    try:
        el.prepare([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)], [(0, 1, 2)])
    except el.DegenerateTriangle as ex:
        assert "0" in str(ex) or "퇴화" in str(ex)
    else:
        raise AssertionError("퇴화 삼각형이 통과했다")

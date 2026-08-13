# -*- coding: utf-8 -*-
"""topology.py 테스트 — 위상 검사가 나쁜 메쉬를 실제로 걸러내는가.

**핵심은 "통과시키지 않는 것"이다.** 나쁜 메쉬를 통과시키면 솔버가 발산하는
대신 그럴듯한 틀린 답을 낸다. 그래서 각 결함마다 걸리는지를 따로 확인한다.
"""

import topology as tp


TRI = [(0, 1, 2)]
SQUARE = [(0, 1, 2), (0, 2, 3)]
# 바깥 사각 0-3, 안쪽 사각 4-7 을 잇는 고리 (구멍 1개)
ANNULUS = [(0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
           (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
# 바깥으로 방향이 맞춰진 사면체 (닫힌 메쉬)
TETRA = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]


def joined(t):
    return " / ".join(t.problems)


def test_single_triangle_is_a_disk():
    t = tp.build(3, TRI)
    assert t.ok, joined(t)
    assert len(t.boundary_loops) == 1
    assert sorted(t.boundary_loops[0]) == [0, 1, 2]


def test_square_boundary_loop_is_four_vertices_in_order():
    t = tp.build(4, SQUARE)
    assert t.ok, joined(t)
    assert len(t.boundary_loops) == 1
    loop = t.boundary_loops[0]
    assert len(loop) == 4
    # 순환열이므로 시작점은 자유롭지만 이웃 관계는 고정이다
    ring = loop + loop
    assert any(ring[i:i + 4] == [0, 1, 2, 3] for i in range(4))


def test_index_out_of_range_is_rejected():
    t = tp.build(3, [(0, 1, 9)])
    assert not t.ok
    assert "범위 밖" in joined(t)


def test_degenerate_face_is_rejected():
    t = tp.build(3, [(0, 1, 1)])
    assert not t.ok
    assert "중복" in joined(t)


def test_non_manifold_edge_is_rejected():
    # 엣지 {0,1} 을 면 셋이 공유한다
    t = tp.build(5, [(0, 1, 2), (1, 0, 3), (0, 1, 4)])
    assert not t.ok
    assert "비다양체" in joined(t)


def test_inconsistent_orientation_is_rejected():
    # 두 면이 같은 방향으로 엣지 (0,2) 를 쓴다 → 앞뒤가 어긋났다
    t = tp.build(4, [(0, 1, 2), (0, 2, 3), (0, 2, 1)])
    assert not t.ok
    assert "방향" in joined(t) or "비다양체" in joined(t)


def test_disconnected_shells_are_rejected():
    t = tp.build(6, [(0, 1, 2), (3, 4, 5)])
    assert not t.ok
    assert "덩어리" in joined(t)


def test_closed_mesh_has_no_boundary_and_is_rejected():
    t = tp.build(4, TETRA)
    assert not t.ok
    assert "경계가 없" in joined(t)
    assert t.boundary_loops == []


def test_hole_makes_two_loops_and_is_rejected():
    t = tp.build(8, ANNULUS)
    assert len(t.boundary_loops) == 2
    assert not t.ok
    assert "구멍" in joined(t)


def test_problems_are_readable_korean_sentences():
    """진단이 사람에게 도달해야 한다 — 코드만 뱉으면 아무도 안 고친다."""
    t = tp.build(3, [(0, 1, 9)])
    assert t.problems
    for msg in t.problems:
        assert len(msg) > 8
        assert "면" in msg or "엣지" in msg or "정점" in msg

# -*- coding: utf-8 -*-
"""flatten.py 테스트 — 반복이 옳은 방향으로 가는가.

이론해 대조는 Task 9(test_theory.py) 가 맡는다. 여기서는 **반복 자체의 성질**만
본다: 전개 가능한 곡면은 오차 0 으로 가는가, 에너지가 단조 감소하는가,
같은 입력이 같은 답을 내는가.
"""

import math

import pytest

import flatten as fl
import material as mt
import meshes
import topology as tp


def prep(verts, faces):
    topo = tp.build(len(verts), faces)
    assert topo.ok, " / ".join(topo.problems)
    return topo


def signature(res):
    """회전·평행이동에 무관한 지문. 축대칭 형상은 정렬 방향이 자유롭기 때문이다."""
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    radii = sorted(round(math.hypot(p[0] - cx, p[1] - cy), 7) for p in res.uv)
    sig = sorted((round(a, 7), round(b, 7)) for a, b in res.sigmas)
    return radii, sig


def max_sigma_error(res):
    return max(max(abs(a - 1.0), abs(b - 1.0)) for a, b in res.sigmas)


def test_plane_is_flattened_without_distortion():
    verts, faces = meshes.plane_grid()
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT)
    assert max_sigma_error(res) < 1e-9
    assert res.flips == 0


def test_cylinder_is_developable_so_error_goes_to_zero():
    """전개 가능한 곡면에서 오차가 남으면 조립이나 국소 좌표계가 틀린 것이다."""
    verts, faces = meshes.cylinder_patch(nu=13, nv=7)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=60)
    assert max_sigma_error(res) < 1e-4


def test_cone_is_developable_too():
    verts, faces = meshes.cone_patch(nu=13, nv=7)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=60)
    assert max_sigma_error(res) < 1e-4


def test_energy_decreases_monotonically_at_penalty_one():
    """k=1 에서만 단조성이 증명된다(spec §6.3). 그 증명된 경로를 여기서 지킨다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=40)
    hist = res.energy_history
    assert len(hist) >= 3
    for a, b in zip(hist, hist[1:]):
        assert b <= a + 1e-12, "에너지가 늘었다: %g -> %g" % (a, b)


def test_energy_history_is_recorded_even_when_penalty_is_raised():
    """k>1 은 수렴을 증명하지 않았다 — 그래서 이력을 남겨 판단할 수 있게 한다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    props = mt.MaterialProps(wrinkle_penalty=3.0, source="테스트")
    res = fl.run(verts, faces, prep(verts, faces), props, iters=20)
    assert len(res.energy_history) >= 3
    assert all(e == e for e in res.energy_history)          # NaN 이 아니다


def test_result_is_deterministic():
    verts, faces = meshes.sphere_cap(nr=4, nt=10)
    topo = prep(verts, faces)
    a = fl.run(verts, faces, topo, mt.DEFAULT, iters=15)
    b = fl.run(verts, faces, topo, mt.DEFAULT, iters=15)
    assert signature(a) == signature(b)


def test_rigid_motion_of_the_input_does_not_change_the_result():
    """좌표계 혼동을 잡는다 — 구현 실수의 대부분이 여기 걸린다."""
    verts, faces = meshes.cylinder_patch(nu=9, nv=5)
    topo = prep(verts, faces)
    base = fl.run(verts, faces, topo, mt.DEFAULT, iters=25)

    ang = 0.7
    ca, sa = math.cos(ang), math.sin(ang)
    moved = [(ca * x - sa * y + 123.0, sa * x + ca * y - 45.0, z + 9.0)
             for (x, y, z) in verts]
    other = fl.run(moved, faces, topo, mt.DEFAULT, iters=25)

    ra, sga = signature(base)
    rb, sgb = signature(other)
    assert ra == pytest.approx(rb, abs=1e-6)
    assert [x for p in sga for x in p] == pytest.approx([x for p in sgb for x in p], abs=1e-6)


def test_scaling_the_input_scales_the_blank_but_not_the_strain():
    verts, faces = meshes.sphere_cap(R=400.0, theta=0.5, nr=4, nt=12)
    topo = prep(verts, faces)
    a = fl.run(verts, faces, topo, mt.DEFAULT, iters=25)
    big = [(x * 3.0, y * 3.0, z * 3.0) for (x, y, z) in verts]
    b = fl.run(big, faces, topo, mt.DEFAULT, iters=25)

    ra, sga = signature(a)
    rb, sgb = signature(b)
    assert [r * 3.0 for r in ra] == pytest.approx(rb, abs=1e-5)
    assert [x for p in sga for x in p] == pytest.approx([x for p in sgb for x in p], abs=1e-6)


def test_face_order_does_not_change_the_result():
    verts, faces = meshes.cylinder_patch(nu=9, nv=5)
    shuffled = list(reversed(faces))
    a = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=25)
    b = fl.run(verts, shuffled, prep(verts, shuffled), mt.DEFAULT, iters=25)
    ra, _ = signature(a)
    rb, _ = signature(b)
    assert ra == pytest.approx(rb, abs=1e-6)


def test_iteration_count_and_convergence_flag_are_reported():
    """조용히 상한에 걸리면 안 된다."""
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    res = fl.run(verts, faces, prep(verts, faces), mt.DEFAULT, iters=2, tol=1e-30)
    assert res.iterations == 2
    assert res.converged is False

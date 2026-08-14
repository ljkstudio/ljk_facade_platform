# -*- coding: utf-8 -*-
"""initial.py 테스트 — 초기 배치가 뒤집히지 않는가.

ARAP 은 초기 배치가 접혀 있으면 거기서 못 빠져나온다. 그래서 얕은 곡면은
투영으로 끝내되, 깊으면 Tutte 로 내려가 **뒤집힘 0 을 보장**한다.
"""

import math

import pytest

import initial as ini
import meshes
import topology as tp


def test_plane_projection_is_isometric_up_to_rigid_motion():
    verts, faces = meshes.plane_grid()
    uv = ini.project(verts, faces)
    for (i, j, k) in faces:
        for a, b in ((i, j), (j, k), (k, i)):
            d3 = math.dist(verts[a], verts[b])
            d2 = math.dist(uv[a], uv[b])
            assert abs(d3 - d2) < 1e-9


def test_shallow_patch_projects_without_flips():
    verts, faces = meshes.cylinder_patch(R=2000.0, beta=0.3)
    assert ini.count_flips(ini.project(verts, faces), faces) == 0


def test_deep_cap_projection_folds_over():
    """이 케이스가 존재하지 않으면 Tutte 폴백은 죽은 코드다.

    **θ 는 적도를 넘어야 한다.** 최적평면은 대칭 때문에 극축에 수직이므로 투영은
    (R·sinφ) 로 떨어지고, 이건 φ < π/2 에서 단조 증가라 접히지 않는다. 이산화까지
    감안한 실제 접힘 시작점은 nr=6 에서 **θ≈1.75** 다 [실측 2026-08-14]:
        θ=1.40 → 뒤집힘 0,  1.70 → 0,  1.75 → 32,  1.90 → 32
    그래서 1.9 를 쓴다 — 시작점에서 충분히 떨어져 있고 뒤집힌 면이 전체 176 중
    32 라 count_flips 의 '과반이면 통째로 뒤집힌 것' 분기도 건드리지 않는다.
    """
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.9)
    assert ini.count_flips(ini.project(verts, faces), faces) > 0


def test_a_globally_mirrored_layout_is_not_counted_as_folded():
    """거울상은 접힘이 아니다. 이걸 접힘으로 세면 멀쩡한 배치를 버리고 Tutte 로
    내려가는데, Tutte 는 훨씬 왜곡된 출발점이라 손해다."""
    verts, faces = meshes.plane_grid()
    uv = ini.project(verts, faces)
    mirrored = [(x, -y) for (x, y) in uv]
    assert ini.count_flips(uv, faces) == 0
    assert ini.count_flips(mirrored, faces) == 0


def test_count_flips_reports_the_minority_orientation():
    """과반이 접히면 **소수파 수**를 돌려준다 — 문서화된 한계다(docstring 참조).

    이 함수가 이끄는 판단은 0 이냐 아니냐뿐이고 0 은 모든 면이 한 방향일 때만
    나오므로, 과소보고가 결정을 바꾸지 못한다는 것을 여기서 못박는다."""
    verts, faces = meshes.sphere_cap(R=300.0, theta=3.0)
    uv = ini.project(verts, faces)
    neg = sum(1 for f in faces if ini.signed_area(uv, f) <= ini.FLIP_TOL)
    assert neg > len(faces) - neg, "이 케이스가 과반 분기를 타야 검사가 성립한다"
    got = ini.count_flips(uv, faces)
    assert got == min(neg, len(faces) - neg)
    assert got > 0          # 접혔다는 사실 자체는 놓치지 않는다


def test_tutte_has_no_flips_even_on_the_deep_cap():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.9)
    topo = tp.build(len(verts), faces)
    assert topo.ok
    assert ini.count_flips(ini.tutte(verts, topo), faces) == 0


def test_tutte_puts_the_boundary_on_a_circle():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.0)
    topo = tp.build(len(verts), faces)
    uv = ini.tutte(verts, topo)
    radii = [math.hypot(uv[v][0], uv[v][1]) for v in topo.boundary_loops[0]]
    assert max(radii) - min(radii) < 1e-6


def test_layout_uses_projection_when_it_is_clean():
    verts, faces = meshes.cylinder_patch(R=2000.0, beta=0.3)
    topo = tp.build(len(verts), faces)
    _uv, method, flips = ini.layout(verts, faces, topo)
    assert method == "projection" and flips == 0


def test_layout_falls_back_to_tutte_when_projection_folds():
    verts, faces = meshes.sphere_cap(R=300.0, theta=1.9)   # 적도를 넘어야 접힌다
    topo = tp.build(len(verts), faces)
    _uv, method, flips = ini.layout(verts, faces, topo)
    assert method == "tutte" and flips == 0


def test_all_test_meshes_are_valid_disks():
    """생성기가 틀리면 뒤의 모든 검증이 무의미해진다."""
    for name, (verts, faces) in [
            ("plane", meshes.plane_grid()),
            ("cylinder", meshes.cylinder_patch()),
            ("cone", meshes.cone_patch()),
            ("cap", meshes.sphere_cap())]:
        topo = tp.build(len(verts), faces)
        assert topo.ok, "%s: %s" % (name, " / ".join(topo.problems))
        assert len(topo.boundary_loops) == 1

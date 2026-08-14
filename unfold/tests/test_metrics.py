# -*- coding: utf-8 -*-
"""metrics.py 테스트 — 판정이 실제로 판정을 하는가.

**미판정을 통과로 치지 않는다.** elong_max 가 없으면 찢어짐은 '통과'가 아니라
'미판정'이어야 한다. 빈 경고 목록이 "검사했고 괜찮다"인지 "검사를 안 했다"인지
구별되지 않으면 이 도구는 쓸모가 없다.
"""

import pytest

import flatten as fl
import material as mt
import meshes
import metrics as mx
import topology as tp


def flat(mesh, props=None, iters=40):
    verts, faces = mesh
    topo = tp.build(len(verts), faces)
    assert topo.ok
    res = fl.run(verts, faces, topo, props or mt.DEFAULT, iters=iters)
    return res, mx.evaluate(res, props or mt.DEFAULT)


def status_of(m, name):
    for n, s, _d in m.checks:
        if n == name:
            return s
    raise AssertionError("판정 항목 %r 이 없다: %r" % (name, [c[0] for c in m.checks]))


def test_forming_strain_sign_matches_the_spec_table():
    """σ<1 은 성형에서 늘어남(양수), σ>1 은 압축(음수)."""
    assert mx.forming_strain(0.5) == pytest.approx(1.0)
    assert mx.forming_strain(1.0) == pytest.approx(0.0)
    assert mx.forming_strain(2.0) == pytest.approx(-0.5)


def test_developable_cylinder_has_no_wrinkle_and_no_tear():
    _res, m = flat(meshes.cylinder_patch(nu=13, nv=7), iters=60)
    assert m.wrinkle_faces == []
    assert status_of(m, "주름") == "통과"
    assert abs(m.sigma_max - 1.0) < 1e-3 and abs(m.sigma_min - 1.0) < 1e-3


def test_dome_must_raise_a_wrinkle_warning():
    """볼록 돔은 평탄화에서 원주방향이 반드시 늘어난다(σ>1) → 성형에서 압축.
    경고가 안 뜨면 판정 쪽이 틀린 것이다."""
    _res, m = flat(meshes.sphere_cap(R=400.0, theta=0.7, nr=6, nt=16))
    assert m.wrinkle_faces
    assert status_of(m, "주름") == "경고"
    assert m.sigma_max > 1.0


def test_tear_is_unjudged_without_an_elongation_limit():
    _res, m = flat(meshes.sphere_cap(nr=5, nt=12))
    assert status_of(m, "찢어짐") == "미판정"
    assert m.tear_faces == []


def test_tear_fires_when_the_limit_is_tight():
    props = mt.MaterialProps(elong_max=0.001, source="테스트용 극단값")
    _res, m = flat(meshes.sphere_cap(R=300.0, theta=0.9, nr=6, nt=16), props)
    assert m.tear_faces
    assert status_of(m, "찢어짐") == "경고"


def test_tear_passes_when_the_limit_is_generous():
    props = mt.MaterialProps(elong_max=0.9, source="테스트용 극단값")
    _res, m = flat(meshes.sphere_cap(R=3000.0, theta=0.2, nr=5, nt=12), props)
    assert m.tear_faces == []
    assert status_of(m, "찢어짐") == "통과"


def test_every_check_reports_even_when_it_passes():
    """통과한 것도 적는다 — 빈 목록의 뜻이 모호해지면 안 된다."""
    _res, m = flat(meshes.plane_grid())
    names = [c[0] for c in m.checks]
    for want in ("주름", "찢어짐", "뒤집힘", "수렴"):
        assert want in names
    for _n, s, d in m.checks:
        assert s in ("통과", "경고", "미판정")
        assert d, "판정에 근거가 없다"


def test_areas_are_reported_for_both_sides():
    _res, m = flat(meshes.plane_grid())
    assert m.area_3d == pytest.approx(100.0 * 80.0)
    assert m.area_2d == pytest.approx(m.area_3d, rel=1e-9)


def test_non_convergence_is_a_warning_not_silence():
    verts, faces = meshes.sphere_cap(nr=5, nt=12)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=2, tol=1e-30)
    m = mx.evaluate(res, mt.DEFAULT)
    assert status_of(m, "수렴") == "경고"

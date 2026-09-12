# -*- coding: utf-8 -*-
"""이론해 대조 — 답을 아는 곡면으로만 검사한다 (spec §10.1).

전개 결과는 그럴듯해 보이는 것과 맞는 것을 눈으로 구별할 수 없다. 그래서
닫힌 형식으로 답이 나오는 케이스에만 기댄다.

    평면        항등
    원기둥      전개 가능 → 가로 R·β, 세로 h 의 직사각형
    원뿔        전개 가능 → 바깥 호 길이 l1·β·sin α
    구면 캡     전개 불가 → 외곽 반경이 2R·sin(θ/2) 와 R·θ **사이**
"""

import math

import pytest

import flatten as fl
import material as mt
import meshes
import metrics as mx
import solver as sv
import topology as tp


def run(mesh, iters=80, props=None):
    verts, faces = mesh
    topo = tp.build(len(verts), faces)
    assert topo.ok, " / ".join(topo.problems)
    return fl.run(verts, faces, topo, props or mt.DEFAULT, iters=iters)


def bbox(uv):
    xs = [p[0] for p in uv]
    ys = [p[1] for p in uv]
    return max(xs) - min(xs), max(ys) - min(ys)


def outer_radii(res, loop):
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    return [math.hypot(res.uv[v][0] - cx, res.uv[v][1] - cy) for v in loop]


def test_cylinder_unrolls_to_a_rectangle_of_the_right_size():
    R, beta, h = 500.0, 0.8, 300.0
    res = run(meshes.cylinder_patch(R=R, beta=beta, h=h, nu=17, nv=9))
    got = sorted(bbox(res.uv))
    want = sorted([R * beta, h])
    assert got == pytest.approx(want, rel=2e-3)


def test_cone_outer_arc_length_matches_the_sector_formula():
    """원뿔 조각을 펴면 부채꼴 띠다. 바깥 호 길이 = l1 · β · sin α."""
    alpha, l0, l1, beta = 0.4, 200.0, 600.0, 0.9
    nu, nv = 17, 9
    res = run(meshes.cone_patch(alpha=alpha, l0=l0, l1=l1, beta=beta, nu=nu, nv=nv))
    outer = [(nv - 1) * nu + i for i in range(nu)]      # 마지막 행 = l1 쪽 모서리
    length = sum(math.dist(res.uv[outer[i]], res.uv[outer[i + 1]])
                 for i in range(nu - 1))
    assert length == pytest.approx(l1 * beta * math.sin(alpha), rel=3e-3)


def test_sphere_cap_lands_between_the_two_closed_form_extremes():
    """spec §10.1 의 핵심 검사.

    축대칭 전개 r(φ) 에서 ARAP 에너지의 두 항을 각각 0 으로 만드는 사상이 극단이다:
        σ_hoop = 1  →  r = R·sinφ  →  외곽 R·sinθ   (정사영)
        σ_r    = 1  →  r = R·φ     →  외곽 R·θ      (등거리)
    각 극단은 한 항만 0 이고 다른 항이 양수이므로 최소점은 그 **사이**에 있다.

    **등면적 반경 2R·sin(θ/2) 는 하한이 아니다** (spec §10.1.1). 등면적은 제3의
    사상이고 ARAP 은 등면적법이 아니다. 실제로 ARAP 은 등면적보다 조금 아래로
    떨어진다 — θ=0.6 에서 295.498 vs 295.52 [실측 2026-08-14].
    """
    R, theta = 500.0, 0.6
    verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=8, nt=24)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)

    lo = R * math.sin(theta)        # σ_hoop = 1 극단
    hi = R * theta                  # σ_r = 1 극단
    assert lo < hi                                   # 검사 자체가 성립하는지
    r_mean = sum(outer_radii(res, topo.boundary_loops[0])) / len(topo.boundary_loops[0])
    assert lo - 1e-6 <= r_mean <= hi + 1e-6, \
        "외곽 반경 %.4f 가 [%.4f, %.4f] 밖이다" % (r_mean, lo, hi)


def test_sphere_cap_result_is_axisymmetric():
    R, theta = 500.0, 0.6
    verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=8, nt=24)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)
    radii = outer_radii(res, topo.boundary_loops[0])
    spread = (max(radii) - min(radii)) / (sum(radii) / len(radii))
    assert spread < 5e-3, "축대칭이 깨졌다 — 상대 폭 %.4f" % spread


def test_the_three_closed_forms_are_ordered_as_claimed():
    """R·sinθ < 2R·sin(θ/2) < R·θ.

    등면적 반경이 두 극단 **사이**에 있다는 것 자체는 참이다 — 다만 그게
    ARAP 결과의 하한이라는 뜻은 아니다(spec §10.1.1). 순서가 깨지면 세 공식 중
    하나를 잘못 적은 것이므로 여기서 잡는다.

    등면적 공식 검산도 겸한다: 구면 캡 면적 2πR²(1−cosθ) = 원판 면적 π(2R sin(θ/2))².
    """
    R, theta = 500.0, 0.6
    lo = R * math.sin(theta)
    eq = 2.0 * R * math.sin(theta / 2.0)
    hi = R * theta
    assert lo < eq < hi

    cap = 2.0 * math.pi * R * R * (1.0 - math.cos(theta))
    disk = math.pi * eq ** 2
    assert cap == pytest.approx(disk)


def test_refining_the_mesh_makes_the_answer_converge():
    """세분화 수렴 — 이산화가 답을 좌우하면 어떤 수치도 못 믿는다."""
    R, theta = 500.0, 0.6

    def outer(nr, nt):
        verts, faces = meshes.sphere_cap(R=R, theta=theta, nr=nr, nt=nt)
        topo = tp.build(len(verts), faces)
        res = fl.run(verts, faces, topo, mt.DEFAULT, iters=120)
        rr = outer_radii(res, topo.boundary_loops[0])
        return sum(rr) / len(rr)

    a, b, c = outer(4, 12), outer(8, 24), outer(16, 48)
    assert abs(c - b) < abs(b - a)


def test_pure_and_numpy_paths_give_the_same_flattening():
    """spec §10.3 — 두 경로가 같은 답을 내야 한다.

    **좌표를 직접 비교하지 않는다.** 구면 캡은 축대칭이라 flatten.align() 의 주축이
    수치적으로 정해지지 않고(공분산이 등방이라 주축이 없다), 두 경로의 부동소수 차이가
    정렬 각도로 증폭된다. 그건 솔버가 다른 답을 냈다는 뜻이 아니다 — flatten.py 가
    스스로 문서화한 성질이다.

    그래서 회전 불변량으로 비교한다: 무게중심까지의 거리 분포와 요소별 σ.
    """
    if not sv.HAS_NUMPY:
        pytest.skip("이 환경에 numpy 가 없다")
    mesh = meshes.sphere_cap(R=400.0, theta=0.5, nr=5, nt=14)
    before = sv.FORCE_PURE
    try:
        sv.FORCE_PURE = True
        pure = run(mesh, iters=60)
        sv.FORCE_PURE = False
        fast = run(mesh, iters=60)
    finally:
        sv.FORCE_PURE = before

    def invariants(res):
        cx = sum(p[0] for p in res.uv) / len(res.uv)
        cy = sum(p[1] for p in res.uv) / len(res.uv)
        radii = sorted(math.hypot(p[0] - cx, p[1] - cy) for p in res.uv)
        sig = sorted(s for pair in res.sigmas for s in pair)
        return radii, sig

    pure_r, pure_s = invariants(pure)
    fast_r, fast_s = invariants(fast)
    assert pure_r == pytest.approx(fast_r, abs=1e-9)
    assert pure_s == pytest.approx(fast_s, abs=1e-9)


def test_dome_wrinkle_warning_is_not_a_false_positive_on_a_cylinder():
    """경고가 아무 데서나 뜨면 아무도 안 본다."""
    cyl = mx.evaluate(run(meshes.cylinder_patch(nu=13, nv=7)), mt.DEFAULT)
    dome = mx.evaluate(run(meshes.sphere_cap(R=400.0, theta=0.7, nr=6, nt=16)), mt.DEFAULT)
    assert cyl.wrinkle_faces == []
    assert dome.wrinkle_faces


def test_golden_fixture_still_matches():
    """회귀 방어 — 리팩터링이 수치를 조용히 바꾸면 여기서 걸린다."""
    import json
    import os

    path = os.path.join(os.path.dirname(__file__), "fixtures", "cap_golden.json")
    with open(path, encoding="utf-8") as f:
        want = json.load(f)

    c = want["case"]
    verts, faces = meshes.sphere_cap(R=c["R"], theta=c["theta"], nr=c["nr"], nt=c["nt"])
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=c["iters"])
    m = mx.evaluate(res, mt.DEFAULT)
    radii = outer_radii(res, topo.boundary_loops[0])

    assert sum(radii) / len(radii) == pytest.approx(want["outer_radius_mean"], rel=1e-6)
    assert m.sigma_min == pytest.approx(want["sigma_min"], rel=1e-6)
    assert m.sigma_max == pytest.approx(want["sigma_max"], rel=1e-6)
    assert m.area_2d == pytest.approx(want["area_2d"], rel=1e-6)
    assert len(m.wrinkle_faces) == want["wrinkle_face_count"]

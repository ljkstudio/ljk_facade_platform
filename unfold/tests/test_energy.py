# -*- coding: utf-8 -*-
"""energy.py 테스트 — 2×2 부호 SVD 와 최근접 회전.

**부호가 이 모듈의 전부다.** σ = (평면 길이)/(3D 길이) 이고

    σ < 1  평탄화에서 줄어듦 → 성형에서 늘어남   정상
    σ > 1  평탄화에서 늘어남 → 성형에서 압축됨   주름 위험

여기서 부호를 놓치면 벌점이 반대 방향으로 걸리고, 결과는 여전히 그럴듯해 보인다.
"""

import math

import pytest

import element as el
import energy as en


TRI3D = ((0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (1.0, 2.0, 0.0))


def one_element():
    return el.prepare(list(TRI3D), [(0, 1, 2)])[0]


def rot(ang):
    c, s = math.cos(ang), math.sin(ang)
    return (c, -s, s, c)


def apply(m, p):
    return (m[0] * p[0] + m[1] * p[1], m[2] * p[0] + m[3] * p[1])


def test_identity_mapping_has_identity_jacobian():
    ed = one_element()
    J = en.jacobian(ed, *ed.local)
    assert J == pytest.approx((1.0, 0.0, 0.0, 1.0), abs=1e-12)


def test_rigid_motion_costs_nothing():
    """강체 이동은 변형이 아니다. 여기서 0 이 안 나오면 에너지 자체가 틀린 것이다."""
    ed = one_element()
    m = rot(0.9)
    moved = [tuple(x + t for x, t in zip(apply(m, p), (17.0, -4.0))) for p in ed.local]
    J = en.jacobian(ed, *moved)
    s1, s2 = en.singular_values(J)
    assert s1 == pytest.approx(1.0, abs=1e-12)
    assert s2 == pytest.approx(1.0, abs=1e-12)
    assert en.element_energy(ed.area, s1, s2) == pytest.approx(0.0, abs=1e-20)


def test_uniform_scale_gives_the_hand_computed_energy():
    ed = one_element()
    s = 1.3
    scaled = [(p[0] * s, p[1] * s) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *scaled))
    assert s1 == pytest.approx(s) and s2 == pytest.approx(s)
    assert en.element_energy(ed.area, s1, s2) == pytest.approx(ed.area * 2.0 * (s - 1.0) ** 2)


def test_anisotropic_scale_recovers_both_singular_values():
    ed = one_element()
    stretched = [(p[0] * 2.0, p[1] * 0.5) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *stretched))
    assert sorted([s1, s2]) == pytest.approx([0.5, 2.0])


def test_singular_values_are_signed_so_a_flip_is_visible():
    """뒤집힘을 크기만 보면 놓친다 — 접힌 채로 '변형 없음'이 된다."""
    ed = one_element()
    mirrored = [(p[0], -p[1]) for p in ed.local]
    s1, s2 = en.singular_values(en.jacobian(ed, *mirrored))
    assert s1 > 0 and s2 < 0


def test_closest_rotation_of_a_rotation_is_itself():
    for ang in (0.0, 0.4, 2.0, -1.7):
        got = en.closest_rotation(rot(ang))
        assert got == pytest.approx(rot(ang), abs=1e-12)


def test_closest_rotation_of_a_pure_stretch_is_identity():
    assert en.closest_rotation((2.0, 0.0, 0.0, 0.5)) == pytest.approx((1.0, 0.0, 0.0, 1.0),
                                                                     abs=1e-12)


def test_singular_values_multiply_to_the_determinant():
    """부호 SVD 의 정의 그 자체. 틀리면 뒤집힘 판정이 무너진다."""
    for J in ((1.2, 0.3, -0.4, 0.9), (0.5, 0.0, 0.0, -2.0), (1.0, 2.0, 3.0, 4.0)):
        s1, s2 = en.singular_values(J)
        assert s1 * s2 == pytest.approx(J[0] * J[3] - J[1] * J[2])


def test_wrinkle_weight_fires_only_when_flattening_stretched():
    """σ>1 (성형에서 압축) 일 때만 벌점이 붙는다. 반대로 걸리면 주름을 키운다."""
    assert en.wrinkle_weight(1.5, 3.0) == 3.0
    assert en.wrinkle_weight(0.7, 3.0) == 1.0
    assert en.wrinkle_weight(1.0, 3.0) == 1.0        # 경계는 벌하지 않는다


def test_wrinkle_weight_of_one_is_a_no_op():
    for s in (0.3, 1.0, 2.5):
        assert en.wrinkle_weight(s, 1.0) == 1.0

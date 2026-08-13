# -*- coding: utf-8 -*-
"""material.py 테스트 — 등급이 실제로 지켜지는가.

**가짜 손잡이를 막는 것이 이 모듈의 존재 이유다.** 형상을 바꾸지 않는 값을
받아 놓고 조용히 있으면, 사용자는 조정하고 있다고 믿는데 아무 일도 안 일어난다.
그래서 describe() 가 무엇이 작동했고 무엇이 기록만인지 반드시 말하게 한다.
"""

import material as mt


def test_default_is_the_proven_path():
    """기본값은 증명된 경로여야 한다 — 단조 감소가 보장되는 k=1."""
    assert mt.DEFAULT.wrinkle_penalty == 1.0


def test_wrinkle_penalty_below_one_is_rejected():
    """1 미만이면 부호가 뒤집혀 주름을 오히려 키운다."""
    p = mt.MaterialProps(wrinkle_penalty=0.5)
    assert not p.ok
    assert any("wrinkle_penalty" in m for m in p.problems)


def test_negative_thickness_is_rejected():
    p = mt.MaterialProps(thickness=-1.0)
    assert not p.ok
    assert any("두께" in m for m in p.problems)


def test_elongation_out_of_range_is_rejected():
    for bad in (-0.1, 1.5):
        p = mt.MaterialProps(elong_max=bad)
        assert not p.ok, "elong_max=%r 가 통과했다" % bad


def test_elongation_is_a_fraction_not_a_percent():
    """0.12 는 12%다. 12 를 넣으면 1200% 라 반드시 걸려야 한다."""
    assert mt.MaterialProps(elong_max=0.12).ok
    assert not mt.MaterialProps(elong_max=12.0).ok


def test_missing_source_is_a_note_not_an_error():
    """출처가 없어도 계산은 되어야 한다. 다만 조용히 넘어가지는 않는다."""
    p = mt.MaterialProps(name="AL-5052", thickness=3.0, elong_max=0.12)
    assert p.ok
    assert any("출처" in m for m in p.notes)


def test_describe_says_which_fields_changed_the_shape():
    p = mt.MaterialProps(name="AL", thickness=3.0, elong_max=0.12,
                         wrinkle_penalty=2.0, source="사내 시험성적서 2026-03")
    text = p.describe()
    assert "wrinkle_penalty" in text and "형상" in text
    assert "두께" in text and "기록" in text


def test_describe_marks_unset_judgment_fields_as_unjudged():
    """미판정을 통과로 치지 않는다."""
    text = mt.MaterialProps().describe()
    assert "미판정" in text

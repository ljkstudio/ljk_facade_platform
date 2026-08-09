"""입력 검증 헬퍼 (Rhino/GH 비의존)."""


def validate_positive_float(value, name, default):
    # type: (object, str, float) -> float
    """양의 실수를 검증합니다."""
    if value is None:
        return default
    try:
        val = float(value)
        if val <= 0:
            return default
        return val
    except (ValueError, TypeError):
        return default


def validate_non_negative_float(value, name, default):
    # type: (object, str, float) -> float
    """0 이상 실수를 검증합니다."""
    if value is None:
        return default
    try:
        val = float(value)
        if val < 0:
            return default
        return val
    except (ValueError, TypeError):
        return default

# -*- coding: utf-8 -*-
"""ARAP 의 구성모델 — 요소 에너지와 local 단계.

**이 파일이 v2 의 교체 지점이다.** solver 와 flatten 은 "요소 하나의 에너지와
최적 목표 회전을 주면 푼다"만 알고 어떤 재료인지 모른다. 소성 모델은 여기를
갈아끼우면 된다.

부호 규약(spec §3.1) — σ = (평면 길이)/(3D 길이)

    σ < 1   평탄화에서 줄어듦 → 성형에서 늘어남 (변형률 1/σ − 1)   정상
    σ > 1   평탄화에서 늘어남 → 성형에서 압축됨                    주름 위험

특이값은 **부호를 살려서** 돌려준다. 크기만 보면 뒤집힌 요소가 '변형 없음'으로
보인다 — 접힌 채로 통과하는 가장 조용한 실패다.
"""

import math

WRINKLE_TOL = 1e-9        # σ 가 1 을 이만큼 넘어야 주름 위험으로 센다


def jacobian(ed, u0, u1, u2):
    # type: (object, tuple, tuple, tuple) -> tuple
    """국소 등거리 좌표 → 현재 평면 좌표의 야코비안. 행 우선 (a, b, c, d)."""
    d00 = u1[0] - u0[0]
    d01 = u2[0] - u0[0]
    d10 = u1[1] - u0[1]
    d11 = u2[1] - u0[1]
    i00, i01, i10, i11 = ed.inv
    return (d00 * i00 + d01 * i10, d00 * i01 + d01 * i11,
            d10 * i00 + d11 * i10, d10 * i01 + d11 * i11)


def singular_values(J):
    # type: (tuple) -> tuple
    """2×2 부호 특이값 (s1, s2). s1 ≥ |s2| 이고 s1·s2 = det(J).

    s2 < 0 이면 요소가 뒤집혔다는 뜻이다.
    """
    a, b, c, d = J
    e = (a + d) * 0.5
    f = (a - d) * 0.5
    g = (c + b) * 0.5
    h = (c - b) * 0.5
    q = math.hypot(e, h)
    r = math.hypot(f, g)
    return q + r, q - r


def closest_rotation(J):
    # type: (tuple) -> tuple
    """J 에 가장 가까운 회전행렬 (ARAP local 단계).

    2차원에서는 닫힌 형식이다 — 각도가 atan2(c−b, a+d) 로 바로 나온다.
    SVD 를 완전히 분해할 필요가 없어 라이브러리도 필요 없다.
    """
    a, b, c, d = J
    ang = math.atan2(c - b, a + d)
    cs, sn = math.cos(ang), math.sin(ang)
    return (cs, -sn, sn, cs)


def element_energy(area, s1, s2):
    # type: (float, float, float) -> float
    """면적 가중 ARAP 에너지. 회전만 하면 0 이다."""
    return area * ((s1 - 1.0) ** 2 + (s2 - 1.0) ** 2)


def wrinkle_weight(s1, penalty):
    # type: (float, float) -> float
    """σ > 1 (성형에서 압축되는 자리) 에만 벌점을 준다.

    판재는 압축을 받으면 압축되는 대신 주름진다. 그래서 그 방향을 더 강하게
    벌해 해를 '성형 시 인장만' 쪽으로 민다.
    """
    if penalty <= 1.0:
        return 1.0
    return penalty if s1 > 1.0 + WRINKLE_TOL else 1.0

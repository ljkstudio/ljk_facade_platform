# -*- coding: utf-8 -*-
"""전개 결과의 판정 — 주름·찢어짐·뒤집힘·수렴.

부호 규약(spec §3.1) — σ = (평면 길이)/(3D 길이), 성형 변형률 = 1/σ − 1

    σ < 1  → 성형에서 늘어남 (양의 변형률). 연신 한계까지 정상
    σ > 1  → 성형에서 압축됨 (음의 변형률). 주름 위험

**미판정을 통과로 치지 않는다.** elong_max 가 없으면 찢어짐 판정은 '미판정'이다.
빈 경고 목록이 "검사했고 괜찮다"인지 "검사를 안 했다"인지 구별되지 않으면
이 도구는 쓸모가 없다.
"""

WRINKLE_TOL = 1e-6        # σ 가 1 을 이만큼 넘어야 주름 위험으로 센다
MIN_SIGMA = 1e-9          # 이보다 작으면 변형률이 발산한다 — 퇴화로 본다


def forming_strain(sigma):
    # type: (float) -> float
    """성형 중 변형률. σ<1 이면 양수(인장), σ>1 이면 음수(압축)."""
    if sigma <= MIN_SIGMA:
        return float("inf")
    return 1.0 / sigma - 1.0


class Metrics(object):
    __slots__ = ("sigma_min", "sigma_max", "max_forming_strain", "wrinkle_faces",
                 "tear_faces", "flip_faces", "area_3d", "area_2d", "checks")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _tri_area_2d(uv, face):
    a, b, c = uv[face[0]], uv[face[1]], uv[face[2]]
    return abs(0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])))


def evaluate(res, props):
    # type: (object, object) -> Metrics
    """FlattenResult 를 판정으로 옮긴다."""
    wrinkle, tear, flip = [], [], []
    s_min = float("inf")
    s_max = -float("inf")
    worst_strain = -float("inf")

    for t, (s1, s2) in enumerate(res.sigmas):
        s_max = max(s_max, s1)
        s_min = min(s_min, s2)
        if s2 < 0.0:
            flip.append(t)
            continue
        if s1 > 1.0 + WRINKLE_TOL:
            wrinkle.append(t)
        strain = forming_strain(s2)          # 가장 작은 σ 가 가장 큰 인장을 낳는다
        worst_strain = max(worst_strain, strain)
        if props.elong_max is not None and strain > props.elong_max:
            tear.append(t)

    area_3d = sum(ed.area for ed in res.elements)
    area_2d = sum(_tri_area_2d(res.uv, f) for f in res.faces)

    checks = []

    if wrinkle:
        checks.append(("주름", "경고",
                       "성형 중 압축되는 요소 %d개 (전체 %d개). 최대 σ = %.4f — "
                       "판재는 압축을 받으면 주름진다"
                       % (len(wrinkle), len(res.sigmas), s_max)))
    else:
        checks.append(("주름", "통과",
                       "모든 요소가 σ ≤ 1 이다 (최대 %.4f) — 성형이 인장만으로 이루어진다"
                       % s_max))

    if props.elong_max is None:
        checks.append(("찢어짐", "미판정",
                       "elong_max 가 없다. 성형 변형률 최대 %.2f%% 를 잰 것뿐이고 "
                       "한계와 비교하지 않았다" % (worst_strain * 100.0)))
    elif tear:
        checks.append(("찢어짐", "경고",
                       "연신 한계 %.1f%% 를 넘는 요소 %d개. 최대 %.2f%%"
                       % (props.elong_max * 100.0, len(tear), worst_strain * 100.0)))
    else:
        checks.append(("찢어짐", "통과",
                       "최대 성형 변형률 %.2f%% < 한계 %.1f%%"
                       % (worst_strain * 100.0, props.elong_max * 100.0)))

    if flip:
        checks.append(("뒤집힘", "경고",
                       "뒤집힌 요소 %d개 — 이 요소의 변형률은 믿을 수 없다" % len(flip)))
    else:
        checks.append(("뒤집힘", "통과", "뒤집힌 요소 없음"))

    if res.converged:
        checks.append(("수렴", "통과",
                       "%d회에서 수렴 (에너지 %.6g)" % (res.iterations, res.energy_history[-1])))
    else:
        checks.append(("수렴", "경고",
                       "반복 상한 %d 에서 멈췄다 — 반복을 늘려야 한다" % res.iterations))

    return Metrics(sigma_min=s_min, sigma_max=s_max, max_forming_strain=worst_strain,
                   wrinkle_faces=wrinkle, tear_faces=tear, flip_faces=flip,
                   area_3d=area_3d, area_2d=area_2d, checks=checks)

# -*- coding: utf-8 -*-
"""사람이 읽는 요약. 숫자와 그 숫자의 뜻을 같이 적는다."""


def summarize(res, m, bl, props):
    # type: (object, object, object, object) -> tuple
    """(info 문자열, warn 목록) 을 만든다.

    **통과한 판정도 warn 에 넣는다.** 빈 목록이 "검사했고 괜찮다"인지
    "검사를 안 했다"인지 구별되지 않으면 판정이 쓸모가 없다.
    """
    warn = ["[%s] %s: %s" % (status, name, detail) for name, status, detail in m.checks]

    ratio = (m.area_2d / m.area_3d) if m.area_3d else float("nan")
    # metrics 는 잰 요소가 하나도 없으면 None 을 준다(전부 뒤집힌 경우).
    # 그때 숫자를 지어내지 않는다 — 못 쟀다고 말한다.
    strain = ("측정 불가 — 뒤집힌 요소뿐이다" if m.max_forming_strain is None
              else "%.2f%%" % (m.max_forming_strain * 100.0))
    lines = [
        "반복 %d회, %s (에너지 %.6g)"
        % (res.iterations, "수렴" if res.converged else "**미수렴**",
           res.energy_history[-1]),
        "초기 배치: %s" % res.method,
        # **자릿수를 줄이지 말 것.** %.4f 로는 σ=1.000012(잔차)와 σ=1.00004 가
        # 똑같이 "1.0000" 으로 보인다 — 무시해도 되는 값과 아닌 값이 한 문장이 된다.
        "σ 범위 %.6f ~ %.6f   (σ>1 은 성형에서 압축 = 주름 위험)"
        % (m.sigma_min, m.sigma_max),
        "최대 성형 변형률 %s" % strain,
        "면적 3D %.1f mm² → 평면 %.1f mm² (비 %.4f)" % (m.area_3d, m.area_2d, ratio),
    ]
    if bl is not None:
        lines.append("재단선 %d점, 최소 여유 %.3f mm" % (len(bl.curve), bl.clearance_min))
        lines.extend("  " + n for n in bl.notes)
    lines.extend("  " + n for n in res.notes)
    lines.append(props.describe())
    return "\n".join(lines), warn

# -*- coding: utf-8 -*-
"""재료 물성 — 그리고 무엇이 실제로 작동하는지에 대한 정직한 표시.

**ARAP 에너지에는 탄성계수도 푸아송비도 들어가지 않는다.** E 를 곱해도 최소점이
그대로라 형상이 안 바뀐다. 그런 값을 받아 두면 돌려도 아무 일이 안 일어나는
가짜 손잡이가 된다 — 사용자는 조정하고 있다고 믿는데 실제로는 아무것도 안 한다.

그래서 v1 은 필드를 셋으로 나누고 describe() 가 그걸 말한다.

  형상을 바꿈 : wrinkle_penalty
  판정만      : elong_max
  기록만      : thickness, name, source

E·ν·항복곡선·FLD·r 값은 **필드조차 만들지 않는다.** v2 소성 모델과 함께 온다.
"""

MIN_PENALTY = 1.0        # 1 미만이면 부호가 뒤집힌다
MAX_ELONG = 1.0          # 100% 를 넘는 균일연신률은 입력 실수(퍼센트를 그대로 넣음)


class MaterialProps(object):
    """판재 물성. 값이 없으면 그 항목은 '미판정'이지 '통과'가 아니다."""

    def __init__(self, name="", thickness=None, elong_max=None,
                 wrinkle_penalty=1.0, source=""):
        # type: (str, float, float, float, str) -> None
        self.name = name or ""
        self.thickness = thickness
        self.elong_max = elong_max
        self.wrinkle_penalty = wrinkle_penalty
        self.source = source or ""
        self.problems = []
        self.notes = []
        self._validate()

    def _validate(self):
        if self.wrinkle_penalty is None or self.wrinkle_penalty < MIN_PENALTY:
            self.problems.append(
                "wrinkle_penalty 는 %g 이상이어야 한다 (받은 값 %r). "
                "1 미만이면 벌점의 부호가 뒤집혀 주름을 오히려 키운다"
                % (MIN_PENALTY, self.wrinkle_penalty))
        if self.thickness is not None and self.thickness <= 0.0:
            self.problems.append("두께는 0 보다 커야 한다 (받은 값 %r mm)" % (self.thickness,))
        if self.elong_max is not None:
            if self.elong_max <= 0.0 or self.elong_max > MAX_ELONG:
                self.problems.append(
                    "elong_max 는 0 초과 %g 이하의 **비율**이다 (받은 값 %r). "
                    "12%%는 12 가 아니라 0.12 다" % (MAX_ELONG, self.elong_max))
        if not self.source:
            self.notes.append(
                "출처 미기재 — 숫자가 어디서 왔는지 적어야 나중에 검증할 수 있다")
        if self.elong_max is None:
            self.notes.append("elong_max 없음 — 찢어짐 판정은 미판정으로 남는다")

    @property
    def ok(self):
        # type: () -> bool
        return not self.problems

    def describe(self):
        # type: () -> str
        """무엇이 형상을 바꿨고 무엇이 기록일 뿐인지 말한다."""
        lines = ["재료: %s" % (self.name or "(이름 없음)")]
        if self.wrinkle_penalty is None:
            # _validate 가 None 을 예상 입력으로 다루므로 여기서도 다뤄야 한다.
            # 물성이 잘못됐을수록 describe() 는 **더** 말을 해야 한다 — 여기서
            # 죽으면 진단이 통째로 사라지고 사용자는 예외만 본다.
            lines.append("  [형상] wrinkle_penalty 없음 — 잘못된 물성이다 (problems 참조)")
        else:
            lines.append("  [형상] wrinkle_penalty = %g%s"
                         % (self.wrinkle_penalty,
                            "" if self.wrinkle_penalty > 1.0 else "  (1.0 — 순수 ARAP, 벌점 없음)"))
        if self.elong_max is None:
            lines.append("  [판정] elong_max 없음 — 찢어짐 **미판정**")
        else:
            lines.append("  [판정] elong_max = %.1f%%" % (self.elong_max * 100.0))
        if self.thickness is None:
            lines.append("  [기록] 두께 없음")
        else:
            lines.append("  [기록] 두께 %g mm — 막 모델이라 **형상에는 영향 없음**"
                         % self.thickness)
        lines.append("  [기록] 출처: %s" % (self.source or "미기재"))
        return "\n".join(lines)


DEFAULT = MaterialProps()

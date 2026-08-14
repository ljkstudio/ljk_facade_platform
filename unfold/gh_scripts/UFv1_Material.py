# -*- coding: utf-8 -*-
# UFv1 Material — 물성을 한 덩어리로 묶어 내보낸다
#
# Flatten 의 입력을 물성 수만큼 늘리는 대신 객체 하나를 물린다.
# AMv1 을 Base/Check/Play 로 쪼갠 것과 같은 이유다.
#
# **프리셋은 없다.** 알루미늄 균일연신률을 출처와 함께 댈 수 없기 때문이다.
# 근거 없는 기본값을 넣으면 아무도 안 고치고 그대로 쓴다.
#
# ── 입력 (Rhino 8 스크립트 에디터에서 이 순서대로 만든다) ──────────────
#   platform_path    str    repo root (필수)
#   name             str    재료 이름
#   thickness        float  두께 mm — **형상에는 영향 없음** (막 모델)
#   elong_max        float  균일연신률 **비율**. 12% 는 0.12
#   wrinkle_penalty  float  σ>1 쪽 벌점. 1.0 이 순수 ARAP(증명된 경로)
#   source           str    이 숫자들이 어디서 왔는가
#
# ── 출력 ────────────────────────────────────────────────────────────
#   props   object  UFv1 Flatten 에 물린다
#   info    str     무엇이 형상을 바꿨고 무엇이 기록인지

import os
import sys

props = None
info = ""

root = str(platform_path or "").strip().strip('"').strip("'")
if not root or not os.path.isdir(root):
    info = "platform_path 가 필요하다 (repo root 폴더)"
else:
    src = os.path.join(root, "unfold", "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    # Rhino 는 프로세스가 사는 동안 모듈을 캐시한다. 저장소 코드를 고친 뒤
    # 다시 계산해도 옛 모듈이 그대로 돌아 **고친 적 없는 결과**가 나온다.
    _norm = os.path.normcase(os.path.normpath(src))
    for _n in [n for n in list(sys.modules)
               if getattr(sys.modules.get(n), "__file__", None)
               and os.path.normcase(
                   os.path.normpath(sys.modules[n].__file__)).startswith(_norm)]:
        del sys.modules[_n]

    import material as mt

    props = mt.MaterialProps(
        name=str(name or ""),
        thickness=float(thickness) if thickness is not None else None,
        elong_max=float(elong_max) if elong_max is not None else None,
        wrinkle_penalty=float(wrinkle_penalty) if wrinkle_penalty is not None else 1.0,
        source=str(source or ""))

    parts = [props.describe()]
    for p in props.problems:
        parts.append("[경고] " + p)
    for n in props.notes:
        parts.append("[참고] " + n)
    info = "\n".join(parts)

    if not props.ok:
        # 잘못된 물성을 하류로 흘려보내지 않는다. Flatten 이 props 없음으로
        # 보고 기본 물성으로 도는 편이, 틀린 값으로 도는 것보다 낫다.
        props = None

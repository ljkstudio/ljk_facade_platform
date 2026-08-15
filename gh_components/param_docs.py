# -*- coding: utf-8 -*-
"""GH 컴포넌트 파라미터 설명(툴팁) — **정본은 `docs/params.ko.json` 이다.**

이 모듈은 그 JSON 을 읽어 옛 이름(`PARAM_DOCS`)으로 노출하는 얇은 껍데기다.
정본을 내린 이유는 하나뿐이다 — **C# 이 파이썬 모듈을 못 읽는다.**
`.gha` 는 같은 JSON 을 EmbeddedResource 로 읽고, 매뉴얼 표도 거기서 생성된다.

**설명을 고칠 때는 JSON 을 고친다.** 여기에 데이터를 되돌려 놓으면 정본이
둘이 되고, 두 컴포넌트가 캔버스에 공존하므로 사용자 눈에 나란히 어긋난다.

**형식 주의:** Grasshopper 툴팁은 평문이다. 마크다운(**굵게** 등)은 기호가
그대로 보이므로 쓰지 않는다. 줄바꿈(\\n)은 그대로 반영된다.
"""

import io
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
PARAM_DOCS_JSON = os.path.normpath(os.path.join(_HERE, "..", "docs", "params.ko.json"))

with io.open(PARAM_DOCS_JSON, encoding="utf-8") as _f:
    PARAM_DOCS = json.load(_f)

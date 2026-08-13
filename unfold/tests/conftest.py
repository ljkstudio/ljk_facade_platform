# -*- coding: utf-8 -*-
"""unfold/src 를 import 경로에 넣는다.

`unfold` 를 설치 가능한 패키지로 만들지 않는 이유: `adaptive_mold/src` 와 같은
방식(평평한 모듈)을 쓰면 Rhino 안에서도 sys.path 하나만 추가하면 되기 때문이다.
"""

import os
import sys

_SRC = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

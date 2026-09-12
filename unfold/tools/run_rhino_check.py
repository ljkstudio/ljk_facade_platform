#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""unfold 의 Rhino 검사 스크립트를 밖에서 돌린다.

`adaptive_mold/tools/run_tests_via_bridge.py` 와 같은 경로다:
    이 스크립트(CPython 3, 밖) → 브리지 1999(IronPython 2.7, Rhino 안)
      → _-RunPythonScript → shebang 대로 CPython 3 로 실행 → 로그 파일

선결 조건: Rhino 8 + 명령창에 `mcpstart`.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))

from rhino_cli import Rhino  # noqa: E402

SCRIPT = os.path.normpath(os.path.join(HERE, "..", "tests", "rhino", "check_rhino_io.py"))
LOG = os.path.join(os.path.dirname(SCRIPT), "_rhino_io_log.txt")

# 브리지는 IronPython 2.7 이다. 여기서 도는 것은 이 조각뿐이고, 실제 검사는
# shebang(`#! python 3`) 대로 CPython 3 에서 돈다.
# `run_tests_via_bridge.py` 의 BRIDGE_CODE 와 같은 방식이다.
BRIDGE_CODE = r'''
import Rhino, io, traceback
lines = []
try:
    ok = Rhino.RhinoApp.RunScript('_-RunPythonScript "{script}"', True)
    lines.append("RunScript=%s" % ok)
except Exception:
    lines.append(traceback.format_exc())
f = io.open(r"{out}", "w", encoding="utf-8")
try:
    f.write(u"\n".join([unicode(x) for x in lines]))
finally:
    f.close()
'''


def main():
    out_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "uf_check_result.txt")
    for p in (LOG, out_path):
        if os.path.exists(p):
            os.remove(p)        # 먼저 지운다 — 없으면 "실행되지 않았다"로 읽는다

    code = BRIDGE_CODE.format(script=SCRIPT.replace("\\", "\\\\"), out=out_path)
    r = Rhino()
    try:
        r.py(code)
    finally:
        r.close()

    if not os.path.exists(LOG):
        print("로그가 없다 — 스크립트가 실행되지 않았다. "
              "Rhino 가 떠 있고 mcpstart 를 했는가?")
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8") as f:
                print(f.read())
        return 1
    with open(LOG, encoding="utf-8") as f:
        text = f.read()
    print(text)
    return 0 if "실패 0건" in text else 1


if __name__ == "__main__":
    sys.exit(main())

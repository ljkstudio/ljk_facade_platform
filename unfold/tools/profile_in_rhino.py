#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""전개 파이프라인의 단계별 소요 시간을 Rhino 안에서 잰다.

    python unfold/tools/profile_in_rhino.py [panel_dome] [edge_mm] [iters]

`run_rhino_check.py` 와 같은 경로다 — 브리지(IronPython 2.7)를 거쳐
`_-RunPythonScript` 로 CPython 3 에서 실행한다. **GH 컴포넌트가 도는 것과 같은
엔진**이라야 "Rhino 가 얼어붙는다"의 원인을 같은 자리에서 잴 수 있다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))

from rhino_cli import Rhino  # noqa: E402

SCRIPT = os.path.normpath(os.path.join(HERE, "..", "tests", "rhino", "profile_pipeline.py"))
LOG = os.path.join(os.path.dirname(SCRIPT), "_profile_log.txt")
CFG = os.path.join(os.path.dirname(SCRIPT), "_profile_cfg.txt")

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
    target = sys.argv[1] if len(sys.argv) > 1 else "panel_dome"
    edge = sys.argv[2] if len(sys.argv) > 2 else "60"
    iters = sys.argv[3] if len(sys.argv) > 3 else "30"
    with open(CFG, "w", encoding="utf-8") as f:
        f.write("%s %s %s" % (target, edge, iters))

    out_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "uf_profile_result.txt")
    for p in (LOG, out_path):
        if os.path.exists(p):
            os.remove(p)        # 먼저 지운다 — 없으면 "빨랐다"가 아니라 "안 돌았다"

    code = BRIDGE_CODE.format(script=SCRIPT.replace("\\", "\\\\"),
                              out=out_path)
    r = Rhino(timeout=1800)     # 얼어붙는 것을 재는 도구다. 넉넉히 기다린다
    try:
        r.py(code)
    finally:
        r.close()

    if not os.path.exists(LOG):
        print("로그가 없다 — 실행되지 않았다. Rhino 가 떠 있고 mcpstart 를 했는가?")
        return 1
    with open(LOG, encoding="utf-8") as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())

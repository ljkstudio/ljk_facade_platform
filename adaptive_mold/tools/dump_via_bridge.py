#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""픽스처 재생성을 밖에서 한 방에 돌린다 — GUI 조작 없이.

J-002 PROCEDURE-01은 "2번(ScriptEditor에서 Run)이 GUI 조작이라 남는다"였다.
이 스크립트가 그 단계를 없앤다.

경로:
    이 스크립트(CPython 3, 밖)
      → rhinomcp 브리지 1999 (IronPython 2.7, Rhino 안)
        → Rhino.RhinoApp.RunScript('_-RunPythonScript "<path>"')
          → dump_fixtures.py가 shebang(`#! python 3`)대로 **CPython 3**로 실행

**왜 브리지에서 exec하지 않는가:** 브리지는 IronPython 2.7이다. 거기서 직접
`exec`하면 픽스처가 2.7로 뽑히는데, dict에 순서가 없어 JSON 키 순서가 매번
달라지고 후행 공백이 붙는다(J-005 FACT-02). 정답지 파일은 diff가 읽혀야 한다.
그래서 명령을 한 번 더 태워 CPython 3로 넘긴다.

**선결 조건:** Rhino 8이 떠 있고 명령창에 `mcpstart`를 입력해 포트 1999가
열려 있어야 한다. 브리지는 동시 클라이언트 1개만 받는다.

사용:
    python adaptive_mold/tools/dump_via_bridge.py
    git diff plugin/fixtures/        # 값이 왜 바뀌었는지 설명 가능한지 확인
"""

import io
import json
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, ".."))
DUMP_SCRIPT = os.path.join(HERE, "dump_fixtures.py")
LOG_PATH = os.path.join(os.path.normpath(os.path.join(REPO_ROOT, "..")),
                        "plugin", "fixtures", "_dump_log.txt")

sys.path.insert(0, HERE)
from rhino_cli import Rhino  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# 브리지 안에서 돌 IronPython 2.7 코드.
# 비ASCII를 넣지 않는다 — IronPython의 json 인코더가 죽는다.
# 파일은 **반드시 close**한다. .NET GC라 참조가 끊겨도 flush 시점이 보장되지 않아
# close 없이 write하면 빈 파일이 남는다 (J-005 TRAP-02).
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
                            "am_runscript_result.txt")
    if os.path.exists(out_path):
        os.remove(out_path)
    if os.path.exists(LOG_PATH):
        os.remove(LOG_PATH)   # 새 실행이 실제로 돌았는지 구별하기 위해

    code = BRIDGE_CODE.format(script=DUMP_SCRIPT.replace("\\", "\\\\"),
                              out=out_path)

    try:
        r = Rhino()
    except socket.error as exc:
        print("브리지에 연결할 수 없다: {}".format(exc))
        print("Rhino 8을 띄우고 명령창에 mcpstart 를 입력할 것 (포트 1999).")
        return 2

    try:
        ver = r.py("import Rhino\nprint(Rhino.RhinoApp.Version)")
        print("Rhino:", json.dumps(ver, ensure_ascii=False)[:200])
        resp = r.py(code)
        ok = resp.get("result", {}).get("success")
        print("디스패치:", "성공" if ok else json.dumps(resp, ensure_ascii=False)[:400])
    finally:
        r.close()

    if os.path.exists(out_path):
        print("브리지 결과:", io.open(out_path, encoding="utf-8").read().strip())

    if not os.path.exists(LOG_PATH):
        print("덤프 로그가 생기지 않았다 — dump_fixtures.py가 실행되지 않았다.")
        return 1

    print("--- {} ---".format(os.path.basename(LOG_PATH)))
    print(io.open(LOG_PATH, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    sys.exit(main())

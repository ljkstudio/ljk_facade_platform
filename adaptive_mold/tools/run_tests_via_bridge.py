#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""adaptive_mold/tests 의 테스트를 밖에서 돌린다 — GUI 조작 없이.

`adaptive_mold/tests/*.py` 는 Rhino.Geometry 에 의존하므로 밖에서는 못 돈다.
그렇다고 ScriptEditor 를 열어 Run 을 누르면 자동화가 끊긴다.

경로 (dump_via_bridge.py 와 같다):
    이 스크립트(CPython 3, 밖)
      → 브리지 1999 (IronPython 2.7, Rhino 안)
        → RunScript('_-RunPythonScript "<test>"')
          → shebang(`#! python 3`) 대로 **CPython 3** 로 실행
            → tests/_<이름>_log.txt 에 결과를 쓴다

**브리지에서 바로 exec 하지 않는 이유:** 브리지는 IronPython 2.7 이다. 테스트를
2.7 로만 돌리면 CPython 3 에서 깨지는 것을 놓친다(반대도 마찬가지). 정본 엔진을
CPython 3 로 정한 J-005 DECISION-01 을 따른다.

**Rhino 콘솔 출력은 밖에서 보이지 않는다.** 그래서 테스트 파일이 로그를 직접
쓰고 이 스크립트가 그것을 읽는다. 로그를 **먼저 지우므로** 파일이 없으면
"통과"가 아니라 "실행되지 않았다"로 판정된다.

선결 조건: Rhino 8 + 명령창에 `mcpstart` (포트 1999).

사용:
    python adaptive_mold/tools/run_tests_via_bridge.py playback
    python adaptive_mold/tools/run_tests_via_bridge.py            # 목록 보기
"""

import io
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.normpath(os.path.join(HERE, "..", "tests"))

sys.path.insert(0, HERE)
from rhino_cli import Rhino  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


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


def available():
    if not os.path.isdir(TESTS_DIR):
        return []
    return sorted(n[5:-3] for n in os.listdir(TESTS_DIR)
                  if n.startswith("test_") and n.endswith(".py"))


def main(argv):
    if not argv:
        print("테스트 모듈을 지정하세요. 있는 것:")
        for n in available():
            print("  " + n)
        return 2

    name = argv[0]
    script = os.path.join(TESTS_DIR, "test_{}.py".format(name))
    if not os.path.isfile(script):
        print("없다: {}".format(script))
        return 2

    log_path = os.path.join(TESTS_DIR, "_{}_log.txt".format(name))
    out_path = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                            "am_test_result.txt")
    for p in (log_path, out_path):
        if os.path.exists(p):
            os.remove(p)

    code = BRIDGE_CODE.format(script=script.replace("\\", "\\\\"),
                              out=out_path)

    try:
        r = Rhino()
    except socket.error as exc:
        print("브리지에 연결할 수 없다: {}".format(exc))
        print("Rhino 8을 띄우고 명령창에 mcpstart 를 입력할 것 (포트 1999).")
        return 2
    try:
        resp = r.py(code)
        ok = resp.get("result", {}).get("success")
        if not ok:
            print("디스패치 실패:", str(resp)[:400])
    finally:
        r.close()

    if os.path.exists(out_path):
        print("브리지:", io.open(out_path, encoding="utf-8").read().strip())

    if not os.path.exists(log_path):
        print("로그가 생기지 않았다 — 테스트가 실행되지 않았다.")
        print("ScriptEditor 가 열려 있으면 RunScript 가 막힐 수 있다.")
        return 1

    text = io.open(log_path, encoding="utf-8").read()
    print("--- test_{}.py ---".format(name))
    print(text)
    return 1 if "FAIL" in text else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

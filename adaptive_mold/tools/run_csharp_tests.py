#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""C# 테스트를 **Rhino 안에서** 태우고 결과를 밖으로 가져온다.

왜 Rhino 안인가
---------------
역산 알고리즘은 전부 네이티브 openNURBS 호출(`RayShoot`·`ClosestPoint`·
`Surface.Extend`·`FitPlaneToPoints`)이다. Rhino 밖에서 `dotnet test` 를 돌리면
`RhinoCommon.dll` 을 못 찾아 죽는다(실측: FileNotFoundException).

`Rhino.Testing` 은 기각했다 — J-015 DECISION-01 참조. 요약하면 NUnit 3.14 에
묶여 있는데 그것을 맞춰도 `[RhinoTestFixture]` 가 **discovery 에서 조용히
사라진다.** 테스트가 없어지는데 러너는 "통과"라고 보고한다.

대신 NUnitLite 의 `AutoRun(assembly).Execute(args)` 를 Rhino 안에서 부른다.
같은 AppDomain 에서 돌므로 테스트 탐색기의 자식 AppDomain 문제가 없고,
RhinoCommon 은 이미 로드돼 있다.

전제
----
Rhino 8 이 떠 있고 명령창에서 `mcpstart` 를 한 상태(포트 1999).
**포트가 열린 것만으로는 부족하다** — 플러그인이 로드되면 mcpstart 없이도
열린다. 이 스크립트는 실제 왕복으로 확인한다.

사용법
------
    python adaptive_mold/tools/run_csharp_tests.py
    python adaptive_mold/tools/run_csharp_tests.py --config Release
"""

import argparse
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rhino_cli import Rhino  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_PROJ = os.path.join(REPO, "plugin", "AdaptiveMold.Tests")


def _posix(p):
    """윈도우에서도 파이썬은 슬래시 경로를 정상으로 받는다.

    백슬래시를 쓰면 브리지로 보내는 코드 문자열에서 이스케이프가 깨진다
    (J-013 TRAP-02). 경로에 백슬래시를 쓸 이유가 없다.
    """
    return p.replace("\\", "/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="Debug", choices=["Debug", "Release"])
    ap.add_argument("--tfm", default="net7.0-windows")
    args = ap.parse_args()

    bin_dir = os.path.join(TEST_PROJ, "bin", args.config, args.tfm)
    dll = os.path.join(bin_dir, "AdaptiveMold.Tests.dll")
    if not os.path.isfile(dll):
        print("[실패] 테스트 어셈블리가 없다: {}".format(dll))
        print("       먼저 dotnet build 를 돌릴 것.")
        return 2

    # Rhino 가 어셈블리를 LoadFrom 하면 파일을 잡고 놓지 않는다. 원본을 잡히면
    # 다음 빌드가 막히므로 **복사본을 태운다**. Rhino 를 껐다 켜지 않고
    # 고쳐-빌드-재실행을 반복할 수 있는 유일한 방법이다.
    stage = tempfile.mkdtemp(prefix="amv1_tests_")
    shutil.copytree(bin_dir, stage, dirs_exist_ok=True)

    result_xml = os.path.join(stage, "nunit-result.xml")

    code = """
import System, io, os
NL = os.linesep
testasm = System.Reflection.Assembly.LoadFrom(r"{dll}")
litasm  = System.Reflection.Assembly.LoadFrom(r"{lite}")
t = litasm.GetType("NUnitLite.AutoRun")
runner = System.Activator.CreateInstance(t, System.Array[System.Object]([testasm]))
# Execute(String[]) 오버로드만 쓴다. 3인자 오버로드는 ExtendedTextWriter 를
# 요구하는데 IronPython 에서 만들기 번거롭고, 결과는 XML 로 받으면 된다.
args = System.Array[System.String]([u"--result={res}"])
rc = runner.Execute(args)
f = io.open(r"{rcfile}", "w", encoding="utf-8")
try:
    f.write(unicode(rc) + NL)
finally:
    f.close()
print("rc=" + str(rc))
""".format(
        dll=_posix(os.path.join(stage, "AdaptiveMold.Tests.dll")),
        lite=_posix(os.path.join(stage, "nunitlite.dll")),
        res=_posix(result_xml),
        rcfile=_posix(os.path.join(stage, "rc.txt")),
    )

    try:
        rhino = Rhino(timeout=300)
    except Exception as e:
        print("[실패] 브리지에 붙지 못했다: {}".format(e))
        print("       Rhino 8 을 띄우고 명령창에 mcpstart 를 칠 것.")
        return 2

    out = rhino.py(code)
    ok = out.get("status") == "success" and out.get("result", {}).get("success")
    if not ok:
        print("[실패] Rhino 안에서 실행이 깨졌다:")
        print(out)
        return 2

    if not os.path.isfile(result_xml):
        print("[실패] 결과 XML 이 없다. 테스트가 하나도 발견되지 않았을 수 있다.")
        return 2

    root = ET.parse(result_xml).getroot()
    total = int(root.get("total") or 0)
    passed = int(root.get("passed") or 0)
    failed = int(root.get("failed") or 0)
    skipped = int(root.get("skipped") or 0)

    for tc in root.iter("test-case"):
        if tc.get("result") != "Passed":
            print("  [{}] {}".format(tc.get("result"), tc.get("fullname")))
            msg = tc.find(".//message")
            if msg is not None and msg.text:
                for line in msg.text.strip().splitlines()[:6]:
                    print("        " + line)

    print("total={} passed={} failed={} skipped={}".format(total, passed, failed, skipped))
    print("결과 XML: {}".format(result_xml))

    # **0개인데 초록**이 가장 위험한 실패 모드다. 실증 사례가 있다
    # (Rhino 미설치 CI 에서 21개가 discovery 에서 사라졌는데 로그는 Passed 21).
    if total == 0:
        print("[실패] 발견된 테스트가 0개다. 초록으로 보이는 것을 믿지 말 것.")
        return 2

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

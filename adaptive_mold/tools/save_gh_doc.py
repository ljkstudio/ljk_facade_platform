#! python 3
# -*- coding: utf-8 -*-
"""열려 있는 GH 문서를 원래 경로에 저장하고, **다시 읽어서 검증한다.**

**Rhino 안에서 CPython 3 로 실행해야 한다.** 밖에서 부를 때는
`rhino_bridge.py run-file` 로 태운다.

    python ~/.claude/skills/rhino-bridge/scripts/rhino_bridge.py run-file \\
        adaptive_mold/tools/save_gh_doc.py

**브리지에서 직접 부르지 말 것 (실측 2026-08-13).** `GH_DocumentIO` 의
`SaveQuiet`/`Open` 을 브리지(IronPython)에서 호출하면 **파일 작업은 되는데
브리지 응답이 돌아오지 않는다** — 결과 파일이 생기지 않아 실패처럼 보이지만
디스크는 이미 바뀌어 있다. 가장 위험한 실패 방식이다(성공을 실패로 오인해
같은 작업을 반복하게 된다). 원인 미확정.

**크기로 판정하지 않는다.** 저장 후 파일을 별도 문서로 다시 열어 객체 수와
컴포넌트별 코드 길이·파라미터 수를 센다. 크기는 압축 때문에 컴포넌트가 늘어도
줄어들 수 있다 — 실측으로 45,730 → 39,381 로 줄면서 컴포넌트는 하나 늘었다.

로그: adaptive_mold/grasshopper/_save_log.txt
"""

import os

import Grasshopper as ghk


HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.normpath(os.path.join(HERE, "..", "grasshopper"))
LOG = os.path.join(GH_DIR, "_save_log.txt")

_lines = []


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def verify(path):
    """저장된 파일을 별도 문서로 열어 내용물을 센다."""
    io = ghk.Kernel.GH_DocumentIO()
    if not io.Open(path):
        log("  검증 실패 — 파일을 열 수 없다")
        return False
    doc = io.Document
    if doc is None:
        log("  검증 실패 — 문서가 비었다")
        return False

    log("  다시 읽음: 객체 {}개".format(doc.ObjectCount))
    n_script = 0
    for o in doc.Objects:
        code = getattr(o, "Code", None)
        if not code:
            continue
        n_script += 1
        log("    {:<18} code {:>6}자  입력 {:>2} / 출력 {:>2}".format(
            o.NickName, len(code),
            o.Params.Input.Count, o.Params.Output.Count))
    log("  스크립트 컴포넌트 {}개".format(n_script))
    return doc.ObjectCount > 0


def main():
    docs = [d for d in ghk.Instances.DocumentServer]
    if not docs:
        log("열린 GH 문서가 없다")
        return

    for d in docs:
        path = d.FilePath
        log("문서 {} — 객체 {}개, 미저장 {}".format(
            d.DisplayName, d.ObjectCount, d.IsModified))
        if not path:
            log("  파일 경로가 없다 — 건너뜀 (한 번은 손으로 저장해야 한다)")
            continue

        before = os.path.getsize(path) if os.path.exists(path) else 0
        ok = ghk.Kernel.GH_DocumentIO(d).SaveQuiet(path)
        after = os.path.getsize(path) if os.path.exists(path) else 0
        log("  SaveQuiet={}  {} -> {} bytes  미저장 {}".format(
            ok, before, after, d.IsModified))
        log("  {}".format(path))
        if ok:
            verify(path)


try:
    main()
finally:
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))

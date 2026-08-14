#! python 3
# -*- coding: utf-8 -*-
"""`unfold/grasshopper/UFv1.gh` 를 열거나 저장하고, **다시 읽어서 검증한다.**

**Rhino 안에서 CPython 3 로 실행해야 한다.** 밖에서는 `run-file` 로 태운다:

    python ~/.claude/skills/rhino-bridge/scripts/rhino_bridge.py run-file \\
        unfold/tools/save_uf_document.py

UFv1 문서가 열려 있지 않으면 **연다.** 열려 있으면 그 자리에 저장한다.
그래서 이 도구 하나로 "열어 놓기 → 배선 고치기 → 저장" 흐름이 돈다.

**브리지에서 직접 부르지 말 것** — `GH_DocumentIO` 의 `SaveQuiet`/`Open` 은
브리지(IronPython)에서 부르면 파일은 바뀌는데 응답이 안 돌아온다(실측).

**크기로 판정하지 않는다.** 저장 후 별도 문서로 다시 열어 객체 수·연결 수·
컴포넌트 코드 길이·파라미터 수를 센다.

로그: unfold/grasshopper/_save_log.txt
"""

import os

import System
import Grasshopper as ghk

HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.normpath(os.path.join(HERE, "..", "grasshopper"))
TARGET = os.path.join(GH_DIR, "UFv1.gh")
LOG = os.path.join(GH_DIR, "_save_log.txt")

COMPS = ("UFv1 Material", "UFv1 Flatten")

_lines = []


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def count_wires(doc):
    n = 0
    for o in doc.Objects:
        params = getattr(o, "Params", None)
        if params is None:
            continue
        for p in params.Input:
            n += p.SourceCount
    return n


def open_on_canvas(path):
    """파일을 GH 편집기에서 연다 — 사용자가 여는 것과 같은 경로.

    **`AddDocument(doc, True)` 로 쓰지 말 것 (실측).** 두 번째 인자는 "활성화"가
    아니라 **out 파라미터**다:

        AddDocument(GH_Document document)
        AddDocument(GH_Document document, Boolean& success)
        AddDocument(String filepath, Boolean makeActive)

    `True` 를 넘기면 `(String, Boolean)` 쪽으로 잡혀 "GH_Document 를 String 으로
    못 바꾼다"는 TypeError 가 난다. 브리지(IronPython)에서는 넘어가던 호출이
    CPython 3 에서 죽는 이유가 이것이다.
    """
    ed = ghk.Instances.DocumentEditor
    if ed is not None:
        try:
            ed.ScriptAccess_OpenDocument(path)
            log("  ScriptAccess_OpenDocument 로 열었다")
            return True
        except Exception as ex:
            log("  ScriptAccess_OpenDocument 실패 ({})".format(type(ex).__name__))

    io = ghk.Kernel.GH_DocumentIO()
    if not io.Open(path):
        log("  GH_DocumentIO.Open 실패")
        return False
    try:
        ghk.Instances.DocumentServer.AddDocument(io.Document)   # 인자 하나
        log("  AddDocument(doc) 로 등록했다")
        return True
    except Exception as ex:
        log("  AddDocument(doc) 실패 ({})".format(type(ex).__name__))
        return False


def verify(path):
    io = ghk.Kernel.GH_DocumentIO()
    if not io.Open(path):
        log("  검증 실패 — 파일을 열 수 없다")
        return False
    doc = io.Document
    if doc is None:
        log("  검증 실패 — 문서가 비었다")
        return False

    log("  다시 읽음: 객체 {}개, 연결 {}개".format(doc.ObjectCount, count_wires(doc)))
    n_desc = 0
    for o in doc.Objects:
        if o.NickName not in COMPS:
            continue
        code = None
        try:
            _got, code = o.TryGetSource()
        except Exception:
            code = getattr(o, "Code", None)
        log("    {:<14} code {}자  입력 {} / 출력 {}".format(
            o.NickName, len(code) if code else "?",
            o.Params.Input.Count, o.Params.Output.Count))
        log("      {}".format(" ".join(
            "%s<-%d" % (p.NickName, p.SourceCount) for p in o.Params.Input)))
        for p in list(o.Params.Input) + list(o.Params.Output):
            if p.Description and p.Description != p.NickName:
                n_desc += 1
    log("  파일이 들고 있는 파라미터 설명 {}개".format(n_desc))
    return doc.ObjectCount > 0


def main():
    doc = None
    for d in [x for x in ghk.Instances.DocumentServer]:
        if any(o.NickName in COMPS for o in d.Objects):
            doc = d
    if doc is None:
        if not os.path.exists(TARGET):
            log("UFv1 문서가 열려 있지도, 파일이 있지도 않다: {}".format(TARGET))
            return
        log("열려 있지 않다 — 연다: {}".format(TARGET))
        open_on_canvas(TARGET)
        opened = None
        for d in [x for x in ghk.Instances.DocumentServer]:
            if any(o.NickName in COMPS for o in d.Objects):
                opened = d
        if opened is None:
            log("  열렸는지 확인 실패 — DocumentServer 에 안 보인다")
        else:
            log("  확인: {} 객체 {}개, 연결 {}개".format(
                opened.DisplayName, opened.ObjectCount, count_wires(opened)))
        return

    log("문서 {} — 객체 {}개, 연결 {}개, 미저장 {}".format(
        doc.DisplayName, doc.ObjectCount, count_wires(doc), doc.IsModified))
    ok = ghk.Kernel.GH_DocumentIO(doc).SaveQuiet(TARGET)
    size = os.path.getsize(TARGET) if os.path.exists(TARGET) else 0
    log("SaveQuiet={}  {} bytes".format(ok, size))
    log(TARGET)
    if ok:
        verify(TARGET)


try:
    main()
finally:
    if not os.path.isdir(GH_DIR):
        os.makedirs(GH_DIR)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))

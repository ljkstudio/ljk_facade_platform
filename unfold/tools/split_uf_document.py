#! python 3
# -*- coding: utf-8 -*-
"""UFv1 컴포넌트와 시험 하네스를 별도 `.gh` 문서로 떼어내 저장한다.

**Rhino 안에서 CPython 3 로 실행해야 한다.** 밖에서는 `run-file` 로 태운다:

    python ~/.claude/skills/rhino-bridge/scripts/rhino_bridge.py run-file \\
        unfold/tools/split_uf_document.py

**브리지에서 직접 부르지 말 것** (실측, J-002~J-005): `GH_DocumentIO` 의
`SaveQuiet`/`Open` 을 브리지(IronPython)에서 호출하면 **파일 작업은 되는데 응답이
돌아오지 않는다.** 결과 파일이 안 생겨 실패처럼 보이는데 디스크는 이미 바뀌어
있다 — 성공을 실패로 오인해 같은 작업을 반복하게 되는 실패 방식이다.

**어떻게 떼어내는가 — 저장 → 다시 열기 → 나머지 삭제.**

    ① 원본 문서를 **임시 경로**에 통째로 저장한다 (사용자 파일은 안 건드린다)
    ② 그 파일을 새 문서로 연다 — 배선까지 그대로인 완전한 복제본이다
    ③ 복제본에서 UF 덩어리가 **아닌** 것을 지운다
    ④ UFv1.gh 로 저장하고, 다시 열어 객체·배선·코드 길이를 센다
    ⑤ 그때까지 다 맞으면 원본에서 덩어리를 지운다

**기각한 대안 — 복사/붙여넣기** (`GH_ClipboardType`). 선택 범위의 배선을
유지하도록 만들어진 경로라 첫 후보였는데, 실측에서 `Copy=True` 인데
`Paste=False`, 객체 0개였다(Local·문서를 서버에 등록하기 전). 캔버스에 붙지 않은
문서로는 붙여넣기가 안 되는 것으로 보인다 — 원인 미확정.

**기각한 대안 — 객체를 옮기기** (`RemoveObject` 후 `AddObject`). `RemoveObject` 는
문서를 일관되게 유지하려고 그 객체의 연결을 끊는다. 저장은 성공하고 컴포넌트도
다 있는데 **선만 없는** 파일이 될 수 있다.

**떼어내기 전에 덩어리가 자립하는지 검사한다.** 바깥에서 들어오는 선이나
바깥으로 나가는 선이 하나라도 있으면 **아무것도 하지 않고 멈춘다.** 배선을
조용히 끊는 것보다 안 하는 것이 낫다.

로그: unfold/grasshopper/_split_log.txt
"""

import os
import tempfile

import Grasshopper as ghk

HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.normpath(os.path.join(HERE, "..", "grasshopper"))
TARGET = os.path.join(GH_DIR, "UFv1.gh")
LOG = os.path.join(GH_DIR, "_split_log.txt")

COMPS = ("UFv1 Material", "UFv1 Flatten")
PREFIX = "uf_"                      # 시험 하네스 위젯

_lines = []


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def in_cluster(obj):
    return obj.NickName in COMPS or obj.NickName.startswith(PREFIX)


def sources_of(obj):
    """이 객체의 입력이 물고 있는 소스 객체들."""
    out = []
    params = getattr(obj, "Params", None)
    if params is not None:
        for p in params.Input:
            for s in p.Sources:
                out.append(s)
    else:
        for s in getattr(obj, "Sources", []):
            out.append(s)
    return out


def owner_of(param, doc):
    """파라미터가 속한 문서 객체. 컴포넌트의 입출력이면 그 컴포넌트다."""
    att = getattr(param, "Attributes", None)
    if att is not None and att.GetTopLevel is not None:
        return att.GetTopLevel.DocObject
    return param


def check_self_contained(doc, cluster):
    """덩어리 안팎으로 넘나드는 선이 있는지 센다."""
    ids = set(str(o.InstanceGuid) for o in cluster)
    crossing = []

    for o in cluster:                      # 바깥에서 들어오는 선
        for s in sources_of(o):
            top = owner_of(s, doc)
            if str(top.InstanceGuid) not in ids:
                crossing.append("들어옴: %s <- %s" % (o.NickName, top.NickName))

    for o in doc.Objects:                  # 바깥으로 나가는 선
        if str(o.InstanceGuid) in ids:
            continue
        for s in sources_of(o):
            top = owner_of(s, doc)
            if str(top.InstanceGuid) in ids:
                crossing.append("나감: %s -> %s" % (top.NickName, o.NickName))
    return crossing


def count_wires(doc, only=None):
    """연결 수 — 배선이 살아남았는지 판정하는 유일한 근거다.

    `only` 를 주면 그 닉네임 집합에 속한 객체의 입력만 센다.
    """
    n = 0
    for o in doc.Objects:
        if only is not None and o.NickName not in only:
            continue
        params = getattr(o, "Params", None)
        if params is None:
            continue
        for p in params.Input:
            n += p.SourceCount
    return n


def verify(path, want_objects, want_wires):
    """저장된 파일을 **별도 문서로 다시 열어** 내용물을 센다.

    크기나 IsModified 로 판정하지 않는다 — 컴포넌트가 늘어도 파일이 줄어든다.
    """
    io = ghk.Kernel.GH_DocumentIO()
    if not io.Open(path):
        log("  검증 실패 — 파일을 열 수 없다")
        return False
    doc = io.Document
    if doc is None:
        log("  검증 실패 — 문서가 비었다")
        return False

    wires = count_wires(doc)
    log("  다시 읽음: 객체 {}개 (기대 {}), 연결 {}개 (기대 {})".format(
        doc.ObjectCount, want_objects, wires, want_wires))

    n_desc = 0
    for o in doc.Objects:
        if o.NickName not in COMPS:
            continue
        code = None
        try:
            _got, code = o.TryGetSource()
        except Exception:
            code = getattr(o, "Code", None)
        srcs = " ".join("%s<-%d" % (p.NickName, p.SourceCount)
                        for p in o.Params.Input)
        log("    {:<14} {:<18} code {}자".format(
            o.NickName, o.GetType().Name, len(code) if code else "?"))
        log("      입력 {} / 출력 {}".format(
            o.Params.Input.Count, o.Params.Output.Count))
        log("      {}".format(srcs))
        for p in list(o.Params.Input) + list(o.Params.Output):
            if p.Description and p.Description != p.NickName:
                n_desc += 1

    # **실측 2026-08-14: 새 Script 컴포넌트의 설명은 파일에 남았다** (23/23).
    # AMv1(구형 GhPython)에서 관찰된 소실(125개 중 120개)은 **Rhino 재시작 후**의
    # 것이고, 같은 세션 안의 저장→재열기에서는 살아남는다. 재시작까지 살아남는지는
    # 새 컴포넌트에서 아직 미검증이다 — 그래서 apply 도구는 그대로 둔다.
    log("  파일이 들고 있는 파라미터 설명 {}개".format(n_desc))
    return doc.ObjectCount == want_objects and wires == want_wires


def main():
    src = None
    cluster = []
    for d in [x for x in ghk.Instances.DocumentServer]:
        found = [o for o in d.Objects if in_cluster(o)]
        if found:
            src = d
            cluster = found
    if src is None:
        log("UFv1 컴포넌트가 열린 문서에 없다")
        return

    log("원본 문서 {} — 객체 {}개".format(src.DisplayName, src.ObjectCount))
    log("떼어낼 것 {}개:".format(len(cluster)))
    for o in sorted(cluster, key=lambda x: x.NickName):
        log("  {:<14} {}".format(o.NickName, o.GetType().Name))

    crossing = check_self_contained(src, cluster)
    if crossing:
        log("")
        log("중단 — 덩어리 밖으로 넘나드는 선이 {}개다. 떼어내면 끊긴다:".format(
            len(crossing)))
        for c in crossing:
            log("  " + c)
        return

    names = set(o.NickName for o in cluster)
    want_wires = count_wires(src, only=names)
    log("덩어리 안쪽 연결 {}개 (원본 문서 전체 {}개)".format(
        want_wires, count_wires(src)))

    # ── ① 원본을 임시 경로에 통째로 저장 ─────────────────────────
    tmp = os.path.join(tempfile.gettempdir(), "uf_split_tmp.gh")
    if not ghk.Kernel.GH_DocumentIO(src).SaveQuiet(tmp):
        log("중단 — 임시 저장이 되지 않았다. 원본은 건드리지 않았다")
        return
    log("임시 복제본 {} bytes".format(os.path.getsize(tmp)))

    # ── ② 복제본을 새 문서로 연다 ────────────────────────────────
    io = ghk.Kernel.GH_DocumentIO()
    if not io.Open(tmp):
        log("중단 — 임시 복제본을 열 수 없다")
        return
    nd = io.Document

    # ── ③ 덩어리가 아닌 것을 지운다 ──────────────────────────────
    drop = [o for o in nd.Objects if not in_cluster(o)]
    nd.RemoveObjects(drop, False)
    new_wires = count_wires(nd)
    log("복제본에서 {}개 삭제 → 객체 {}개, 연결 {}개".format(
        len(drop), nd.ObjectCount, new_wires))

    if nd.ObjectCount != len(cluster) or new_wires != want_wires:
        log("중단 — 개수나 배선이 안 맞는다 (기대 객체 {} 연결 {}). "
            "원본은 건드리지 않았다".format(len(cluster), want_wires))
        return

    # ── ④ 저장하고 다시 읽어 검증 ────────────────────────────────
    if not os.path.isdir(GH_DIR):
        os.makedirs(GH_DIR)
    ok = ghk.Kernel.GH_DocumentIO(nd).SaveQuiet(TARGET)
    size = os.path.getsize(TARGET) if os.path.exists(TARGET) else 0
    log("SaveQuiet={}  {} bytes".format(ok, size))
    log(TARGET)
    if not ok or not verify(TARGET, len(cluster), want_wires):
        log("중단 — 저장/검증이 통과하지 못했다. 원본은 건드리지 않았다")
        return

    # ── ⑤ 여기까지 다 맞았을 때만 원본에서 지운다 ────────────────
    src.RemoveObjects(cluster, False)
    src.NewSolution(False)
    log("원본에서 제거 → 남은 객체 {}개".format(src.ObjectCount))

    # 새 문서를 캔버스에 띄운다. CPython 3 에서는 오버로드가
    # AddDocument(string, bool) 로 잡히므로 명시해야 한다 (실측).
    try:
        add = ghk.Instances.DocumentServer.AddDocument.Overloads[
            ghk.Kernel.GH_Document, bool]
        add(nd, True)
        log("새 문서를 캔버스에 띄웠다")
    except Exception as ex:
        log("캔버스에 띄우지 못했다 ({}) — 파일은 저장돼 있으니 열면 된다".format(
            type(ex).__name__))

    try:
        os.remove(tmp)
    except Exception:
        pass

    log("")
    log("원본 {} 은 저장하지 않았다 — 디스크의 .gh 는 그대로다".format(src.DisplayName))


try:
    main()
finally:
    if not os.path.isdir(GH_DIR):
        os.makedirs(GH_DIR)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(_lines))

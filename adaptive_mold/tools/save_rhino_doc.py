#! python 3
# -*- coding: utf-8 -*-
"""열려 있는 Rhino 문서를 원래 경로에 저장하고 **다시 읽어서 검증한다.**

**Rhino 안에서 CPython 3 로 실행한다.**

    python ~/.claude/skills/rhino-bridge/scripts/rhino_bridge.py run-file \\
        adaptive_mold/tools/save_rhino_doc.py

**`RhinoDoc.SaveAs` 는 예외 없이 False 를 돌려준다**(실측, rhino-bridge 스킬 §6).
그래서 `WriteFile(path, FileWriteOptions())` 를 쓰고 **반환값을 확인**한다.

**크기로 판정하지 않는다.** 저장 뒤 파일을 `File3dm.Read` 로 열어 객체 수와
이름을 세어 본다 — 도구가 만든 객체가 실제로 파일에 들어갔는지가 요점이다.

로그: adaptive_mold/grasshopper/_rhino_save_log.txt
"""

import os

import Rhino


HERE = os.path.dirname(os.path.abspath(__file__))
GH_DIR = os.path.normpath(os.path.join(HERE, "..", "grasshopper"))
LOG = os.path.join(GH_DIR, "_rhino_save_log.txt")

_lines = []


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    path = doc.Path
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    n_before = len([o for o in doc.Objects.GetObjectList(st)])
    log("문서 {} — 객체 {}개, 미저장 {}".format(doc.Name, n_before, doc.Modified))
    if not path:
        log("파일 경로가 없다 — 한 번은 손으로 저장해야 한다")
        return

    # **렌더 메시를 털고 저장한다.** 기본값으로 저장하면 파일이 크게 부푼다
    # (실측: 106,468 -> 672,707 bytes, 6.3배). 저장소에 들어가는 파일이므로
    # diff 와 클론 비용에 그대로 얹힌다. 형상 자체는 다시 열 때 Rhino 가
    # 메시를 만들므로 잃는 것이 없다.
    #
    # 렌더 메시는 객체에 캐시되므로 옵션과 별개로 털어 준다.
    Rhino.RhinoApp.RunScript("_-ClearAllMeshes", False)

    # **속성 이름을 틀리면 예외 없이 조용히 무시된다** (실측). `SaveRenderMeshes`
    # 라는 이름으로 몇 번 설정하고 "옵션을 껐다"고 믿었는데, 실제 이름은
    # `IncludeRenderMeshes` 였고 파일은 계속 컸다. 그래서 **넣고 다시 읽어 확인**한다.
    opt = Rhino.FileIO.FileWriteOptions()
    for name, value in (("IncludeRenderMeshes", False),
                        ("IncludePreviewImage", False),
                        ("IncludeBitmapTable", False),
                        ("IncludeHistory", False)):
        try:
            setattr(opt, name, value)
        except Exception as ex:
            log("  옵션 {} 설정 실패: {}".format(name, ex))
            continue
        got = getattr(opt, name, "없음")
        if got != value:
            log("  옵션 {} 반영 안 됨 (읽으니 {}) — 이름이 틀렸을 수 있다".format(
                name, got))

    size0 = os.path.getsize(path) if os.path.exists(path) else 0
    ok = doc.WriteFile(path, opt)
    size1 = os.path.getsize(path) if os.path.exists(path) else 0
    log("WriteFile={}  {} -> {} bytes  미저장 {}".format(
        ok, size0, size1, doc.Modified))
    log(path)
    if not ok:
        return

    f = Rhino.FileIO.File3dm.Read(path)
    if f is None:
        log("  검증 실패 — 파일을 읽을 수 없다")
        return
    objs = [o for o in f.Objects]
    log("  다시 읽음: 객체 {}개".format(len(objs)))
    named = {}
    for o in objs:
        nm = o.Attributes.Name or "(무명)"
        named[nm] = named.get(nm, 0) + 1
    for nm in sorted(named):
        log("    {:<18} {}개  ".format(nm, named[nm]))


try:
    main()
finally:
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(_lines))

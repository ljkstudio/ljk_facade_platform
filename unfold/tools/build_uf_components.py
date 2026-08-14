#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""UFv1 컴포넌트 둘을 캔버스에 맞춘다 — 코드 push + 입출력 파라미터 생성.

    C:\\Python313\\python.exe unfold/tools/build_uf_components.py

선결 조건: Rhino 8 이 떠 있고 Grasshopper 가 열려 있고, 캔버스에 NickName 이
정확히 `UFv1 Material` / `UFv1 Flatten` 인 **Python 3 스크립트 컴포넌트**가 있을 것.
이름이 한 글자만 달라도 "못 찾음"이 된다.

멱등하다. 기존 입출력을 지우고 다시 만든다(표준출력 `out` 은 남긴다).

──────────────────────────────────────────────────────────────────────
왜 adaptive_mold/tools/build_gh_components.py 를 못 쓰는가
──────────────────────────────────────────────────────────────────────
그쪽은 구형 `ZuiPythonComponent` + `GH_*Hint` 를 전제한다. Rhino 8 의 새
스크립트 컴포넌트는 `RhinoCodePluginGH.Components.Python3Component` 이고
파라미터가 `ScriptVariableParam`, 힌트가 `ScriptVariableTypeHintSet` 이라
API 가 통째로 다르다.

구형으로 바꾸는 것은 길이 아니다 — IronPython 2.7 이라 numpy 를 못 쓰고
`unfold/src` 가 전제한 Python 3.9 문법이 깨진다.

──────────────────────────────────────────────────────────────────────
실측으로 알아낸 함정 셋 (2026-08-14). 순서를 지켜야 한다
──────────────────────────────────────────────────────────────────────
1. **코드는 `comp.SetSource(text)` 로 넣는다.** `TryGetSource()` 는 튜플을
   돌려주므로 되읽을 때 문자열 항목을 골라야 한다.

2. **힌트는 파라미터를 컴포넌트에 등록한 *뒤에* 건다.** 등록 전에는 파라미터가
   언어를 몰라 파이썬 전용 힌트(`float`, `object`)가 목록에 아예 없고
   `string` 도 `AnyStringConverter` 로 나온다.

3. **`TypeHints.Select()` 는 값의 .NET 타입을 받는다** (`typeof(Brep)` 식).
   힌트 객체를 주면 "expected Type", 변환기의 타입을 주면 "No hints found for
   given type" 이 난다. 둘 다 겪었다.

`props` 에 `object`(PythonDynamicConverter)를 쓰는 이유: "No Type Hint" 는
GH_Goo 래퍼를 넘겨서 파이썬 객체가 그대로 건너가지 않는다.
"""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
SCRIPTS = os.path.join(REPO, "unfold", "gh_scripts")
sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))

from rhino_cli import Rhino  # noqa: E402

LOG = os.path.join(os.environ.get("TEMP", HERE), "uf_build.txt")

BRIDGE = r'''
import io, traceback
import clr
import System
import Rhino
import Grasshopper as ghk

lines = []

# 힌트 이름 -> 값의 .NET 타입. Select 가 이걸 받는다 (함정 3).
CLR_TYPE = {
    "string": clr.GetClrType(System.String),
    "float": clr.GetClrType(System.Double),
    "int": clr.GetClrType(System.Int32),
    "bool": clr.GetClrType(System.Boolean),
    "object": clr.GetClrType(System.Object),
    "Brep": clr.GetClrType(Rhino.Geometry.Brep),
}

SPECS = [
    ("UFv1 Material", MATPATH,
     [("platform_path", "string"), ("name", "string"), ("thickness", "float"),
      ("elong_max", "float"), ("wrinkle_penalty", "float"), ("source", "string")],
     ["props", "info"]),
    ("UFv1 Flatten", FLATPATH,
     [("platform_path", "string"), ("srf", "Brep"), ("props", "object"),
      ("edge_mm", "float"), ("allow_mm", "float"), ("iters", "int"),
      ("max_verts", "int"), ("run", "bool")],
     ["flat", "blank", "strain", "warn", "info"]),
]

KEEP_OUT = ("out",)          # 표준출력(print 캡처)은 지우지 않는다


def set_hint(p, name):
    t = CLR_TYPE.get(name)
    if t is None:
        return "'%s' 에 대응하는 .NET 타입을 모른다" % name
    try:
        p.TypeHints.Select(t)
        return "hint=%s" % name
    except Exception:
        return "hint 실패: %s" % traceback.format_exc().splitlines()[-1]


def make_param(proto_type, nick):
    p = System.Activator.CreateInstance(proto_type)
    p.Name = nick
    p.NickName = nick            # NickName 을 주면 VariableName 이 따라온다
    p.Description = nick
    p.Access = ghk.Kernel.GH_ParamAccess.item
    return p


def build(nick, path, ins, outs):
    doc = ghk.Instances.ActiveCanvas.Document
    comp = None
    for o in doc.Objects:
        if o.NickName == nick:
            comp = o
            break
    if comp is None:
        lines.append("%s : NOT FOUND — 캔버스에 그 이름의 컴포넌트가 없다" % nick)
        return

    lines.append("=== %s" % nick)

    f = io.open(path, "r", encoding="utf-8")
    try:
        text = f.read()
    finally:
        f.close()
    comp.SetSource(text)
    lines.append("  코드 %d자 push" % len(text))

    proto_in = comp.Params.Input[0].GetType()
    proto_out = None
    for p in comp.Params.Output:
        if p.NickName not in KEEP_OUT:
            proto_out = p.GetType()
            break
    if proto_out is None:
        proto_out = proto_in

    for p in list(comp.Params.Input):
        comp.Params.UnregisterInputParameter(p)
    for p in list(comp.Params.Output):
        if p.NickName not in KEEP_OUT:
            comp.Params.UnregisterOutputParameter(p)

    for nickname, hint in ins:
        p = make_param(proto_in, nickname)
        comp.Params.RegisterInputParam(p)     # 등록이 먼저다 (함정 2)
        lines.append("  in  %-16s %s" % (nickname, set_hint(p, hint)))

    for nickname in outs:
        comp.Params.RegisterOutputParam(make_param(proto_out, nickname))
        lines.append("  out %s" % nickname)

    comp.Params.OnParametersChanged()
    try:
        comp.VariableParameterMaintenance()
    except Exception:
        pass
    comp.ExpireSolution(True)

    lines.append("  최종 in : %s" % ", ".join([p.NickName for p in comp.Params.Input]))
    lines.append("  최종 out: %s" % ", ".join([p.NickName for p in comp.Params.Output]))


try:
    for spec in SPECS:
        build(*spec)
except Exception:
    lines.append(traceback.format_exc())

f = io.open(LOGPATH, "w", encoding="utf-8")
try:
    f.write(u"\n".join([unicode(x) for x in lines]))
finally:
    f.close()
'''


def main():
    code = (BRIDGE
            .replace("MATPATH", repr(os.path.join(SCRIPTS, "UFv1_Material.py")))
            .replace("FLATPATH", repr(os.path.join(SCRIPTS, "UFv1_Flatten.py")))
            .replace("LOGPATH", repr(LOG)))
    if os.path.exists(LOG):
        os.remove(LOG)          # 먼저 지운다 — 없으면 "실행되지 않았다"로 읽는다
    r = Rhino(timeout=120)
    try:
        r.py(code)
    finally:
        r.close()
    if not os.path.exists(LOG):
        print("로그가 없다 — 실행되지 않았다. Rhino 가 떠 있고 mcpstart 를 했는가?")
        return 1
    text = io.open(LOG, encoding="utf-8").read()
    print(text)
    return 1 if ("NOT FOUND" in text or "실패" in text) else 0


if __name__ == "__main__":
    sys.exit(main())

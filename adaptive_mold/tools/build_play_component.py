#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""AMv1 Play 컴포넌트를 살아 있는 캔버스에 만들고 형제 컴포넌트에 배선한다.

**멱등하다.** 다시 돌려도 안전하다 — 파라미터 순서가 정의와 다르면 전부 다시
만들지만, 그 전에 **연결을 닉네임으로 기억해 두고 복원한다.** 이게 없으면
파라미터를 하나 추가할 때마다 배선을 손으로 다시 해야 한다.

**코드는 저장소 파일에서 읽는다.** 브리지 JSON 에 한글을 태우지 않기 위해
경로만 넘기고 Rhino 쪽에서 `io.open(encoding="utf-8")` 로 읽는다
(rhino-bridge 스킬 규칙 4).

선결 조건: Rhino 8 + `mcpstart`, 그리고 캔버스에 AMv1 Inspect / RollerPath /
Robot 이 있어야 한다 — 파라미터 타입 힌트의 원형과 배선 상대를 거기서 얻는다.

사용:
    python adaptive_mold/tools/build_play_component.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
CODE_PATH = os.path.join(REPO_ROOT, "gh_components", "gh_scripts", "AMv1_Play.py")

sys.path.insert(0, HERE)
from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# (닉네임, 힌트, list접근?, 위젯)
#   위젯: None | ("slider", lo, hi, val, digits) | ("toggle", val) | ("path",)
INPUTS = [
    ("platform_path", "GH_StringHint_CS",  False, ("path",)),
    ("pin_tops",      "GH_Point3dHint",    True,  None),
    ("base_plane",    "GH_PlaneHint",      False, None),
    ("pin_home",      "GH_DoubleHint_CS",  False, ("slider", 0, 400, 0, 0)),
    ("pin_speed",     "GH_DoubleHint_CS",  False, ("slider", 5, 300, 50, 0)),
    ("poses",         "GH_DoubleHint_CS",  True,  None),
    ("targets",       "GH_PlaneHint",      True,  None),
    ("move_kind",     "GH_StringHint_CS",  True,  None),
    ("robot_base",    "GH_PlaneHint",      False, None),
    ("feed",          "GH_DoubleHint_CS",  False, ("slider", 5, 300, 50, 0)),
    ("joint_scale",   "GH_DoubleHint_CS",  False, ("slider", 0.05, 1.0, 0.25, 2)),
    ("dwell",         "GH_DoubleHint_CS",  False, ("slider", 0, 10, 1, 1)),
    ("t",             "GH_DoubleHint_CS",  False, ("slider", 0, 600, 0, 1)),
    ("play",          "GH_BooleanHint_CS", False, ("toggle", False)),
    ("loop",          "GH_BooleanHint_CS", False, ("toggle", False)),
    ("time_scale",    "GH_DoubleHint_CS",  False, ("slider", 0.1, 20, 1, 1)),
    ("fps",           "GH_IntegerHint_CS", False, ("slider", 5, 60, 25, 0)),
    ("roller_d",      "GH_DoubleHint_CS",  False, ("slider", 20, 200, 60, 0)),
    ("show_path",     "GH_BooleanHint_CS", False, ("toggle", True)),
    ("solo",          "GH_BooleanHint_CS", False, ("toggle", True)),
]

OUTPUTS = ["pins", "deck", "links", "tcp", "roller", "duration", "info"]

# (내 입력, 상대 컴포넌트, 상대 출력)
WIRING = [
    ("pin_tops",   "AMv1 Inspect",    "pin_tops"),
    ("poses",      "AMv1 Robot",      "poses"),
    ("targets",    "AMv1 RollerPath", "targets"),
    ("move_kind",  "AMv1 RollerPath", "move_kind"),
]

# 형제의 같은 입력에 붙어 있는 소스를 그대로 공유한다 (슬라이더 재사용)
SHARE = [
    ("platform_path", "AMv1 Inspect", "platform_path"),
    ("base_plane",    "AMv1 Inspect", "base_plane"),
    ("robot_base",    "AMv1 Robot",   "robot_base"),
    ("roller_d",      "AMv1 RollerPath", "roller_d"),
]


BRIDGE_CODE = u'''
import io
import System
import System.Drawing as sd
import Grasshopper as ghk
import Grasshopper.Kernel as gk
import Grasshopper.Kernel.Special as ghs

NICK = "AMv1 Play"
INPUTS = {inputs}
OUTPUTS = {outputs}
WIRING = {wiring}
SHARE = {share}
CODE_PATH = r"{code}"


def find(nick):
    for _d in [d for d in ghk.Instances.DocumentServer]:
        for _o in _d.Objects:
            if _o.NickName == nick:
                return _d, _o
    return None, None


doc, insp = find("AMv1 Inspect")
if insp is None:
    lines.append("AMv1 Inspect not on canvas -- cannot clone param types")
else:
    _, comp = find(NICK)
    if comp is None:
        _, anchor = find("AMv1 Robot")
        if anchor is None:
            anchor = insp
        comp = System.Activator.CreateInstance(insp.GetType())
        comp.CreateAttributes()
        comp.Attributes.Pivot = sd.PointF(
            anchor.Attributes.Pivot.X, anchor.Attributes.Pivot.Y + 520.0)
        comp.NickName = NICK
        comp.Name = NICK
        doc.AddObject(comp, False)
        lines.append("created")
    else:
        lines.append("exists")

    # ---- code from repo (source of truth) ----
    f = io.open(CODE_PATH, "r", encoding="utf-8")
    try:
        code = f.read()
    finally:
        f.close()
    comp.Code = code
    lines.append("code %d chars" % len(code))

    # ---- params ----
    want = [a for a, b, c, d in INPUTS]
    have = [p.NickName for p in comp.Params.Input]

    if have != want:
        # remember wiring by nickname, then rebuild in order
        kept = {{}}
        for p in comp.Params.Input:
            if p.SourceCount:
                kept[p.NickName] = [s for s in p.Sources]
        lines.append("rebuild inputs (had %d, remembered %d wires)" % (
            len(have), len(kept)))

        while comp.Params.Input.Count > 0:
            comp.Params.UnregisterInputParameter(comp.Params.Input[0])

        proto = insp.Params.Input[0]
        for nick, hint, is_list, widget in INPUTS:
            p = System.Activator.CreateInstance(proto.GetType())
            p.Name = nick
            p.NickName = nick
            p.Description = nick
            p.Optional = True
            p.Access = (gk.GH_ParamAccess.list if is_list
                        else gk.GH_ParamAccess.item)
            try:
                p.TypeHint = getattr(gk.Parameters.Hints, hint)()
            except Exception as ex:
                lines.append("  hint FAIL %s %s: %s" % (nick, hint, ex))
            comp.Params.RegisterInputParam(p)
            for s in kept.get(nick, []):
                p.AddSource(s)
    else:
        lines.append("inputs already match (%d)" % len(have))

    # GhPython 의 "out" 은 콘솔 출력용 특수 파라미터다 -- 지우지 않고 앞에 둔다
    existing_out = [p for p in comp.Params.Output]
    have_out = [p.NickName for p in existing_out if p.NickName != "out"]

    def recipients(p):
        try:
            return [r for r in p.Recipients]
        except Exception:
            return []

    if have_out != OUTPUTS:
        kept_o = {{}}
        for p in existing_out:
            rec = recipients(p)
            if rec:
                kept_o[p.NickName] = rec
        for p in existing_out:
            if p.NickName != "out":
                comp.Params.UnregisterOutputParameter(p)
        proto_o = None
        for p in insp.Params.Output:
            if p.NickName != "out":
                proto_o = p
                break
        if proto_o is None:
            proto_o = insp.Params.Output[0]
        for nick in OUTPUTS:
            p = System.Activator.CreateInstance(proto_o.GetType())
            p.Name = nick
            p.NickName = nick
            p.Description = nick
            comp.Params.RegisterOutputParam(p)
            for r in kept_o.get(nick, []):
                r.AddSource(p)
        lines.append("rebuild outputs (%d, kept %d wires)" % (
            len(OUTPUTS), len(kept_o)))
    else:
        lines.append("outputs already match (%d)" % len(have_out))

    comp.Params.OnParametersChanged()

    def in_p(owner, nick):
        for p in owner.Params.Input:
            if p.NickName == nick:
                return p
        return None

    def out_p(owner, nick):
        for p in owner.Params.Output:
            if p.NickName == nick:
                return p
        return None

    # ---- wire to siblings ----
    wired = []
    for my, other_nick, their in WIRING:
        p = in_p(comp, my)
        _, other = find(other_nick)
        if p is None or other is None or p.SourceCount:
            continue
        q = out_p(other, their)
        if q is not None:
            p.AddSource(q)
            wired.append("%s<-%s.%s" % (my, other_nick, their))

    # ---- share sibling input sources ----
    for my, other_nick, their in SHARE:
        p = in_p(comp, my)
        _, other = find(other_nick)
        if p is None or other is None or p.SourceCount:
            continue
        q = in_p(other, their)
        if q is None or q.SourceCount == 0:
            continue
        for s in q.Sources:
            p.AddSource(s)
        wired.append("%s<-shared %s" % (my, other_nick))

    # ---- widgets for still-unwired inputs ----
    px = comp.Attributes.Pivot.X
    py = comp.Attributes.Pivot.Y
    row = 0
    made = []
    for nick, hint, is_list, widget in INPUTS:
        p = in_p(comp, nick)
        if p is None or p.SourceCount or widget is None:
            continue
        y = py - 60.0 + row * 26.0
        if widget[0] == "slider":
            lo, hi, val, digits = widget[1], widget[2], widget[3], widget[4]
            w = ghs.GH_NumberSlider()
            w.CreateAttributes()
            w.Slider.DecimalPlaces = int(digits)
            w.Slider.Minimum = System.Decimal(float(lo))
            w.Slider.Maximum = System.Decimal(float(hi))
            try:
                w.SetSliderValue(System.Decimal(float(val)))
            except Exception:
                w.Slider.Value = System.Decimal(float(val))
            w.NickName = nick
            w.Attributes.Pivot = sd.PointF(px - 320.0, y)
            doc.AddObject(w, False)
            p.AddSource(w)
            made.append(nick)
            row += 1
        elif widget[0] == "toggle":
            w = ghs.GH_BooleanToggle()
            w.CreateAttributes()
            w.Value = bool(widget[1])
            w.NickName = nick
            w.Attributes.Pivot = sd.PointF(px - 320.0, y)
            doc.AddObject(w, False)
            p.AddSource(w)
            made.append(nick)
            row += 1
        elif widget[0] == "path":
            w = ghs.GH_Panel()
            w.CreateAttributes()
            w.UserText = r"{repo}"
            w.NickName = nick
            w.Attributes.Pivot = sd.PointF(px - 560.0, y)
            doc.AddObject(w, False)
            p.AddSource(w)
            made.append(nick)
            row += 1

    lines.append("wired: %s" % (", ".join(wired) if wired else "none"))
    lines.append("widgets: %s" % (", ".join(made) if made else "none"))

    unwired = [p.NickName for p in comp.Params.Input if p.SourceCount == 0]
    lines.append("still unwired: %s" % (", ".join(unwired) if unwired else "none"))

    comp.ExpireSolution(True)
    doc.NewSolution(False)

    lines.append("inputs %d / outputs %d" % (
        comp.Params.Input.Count, comp.Params.Output.Count))
    for lvl in (gk.GH_RuntimeMessageLevel.Error,
                gk.GH_RuntimeMessageLevel.Warning,
                gk.GH_RuntimeMessageLevel.Remark):
        for m in comp.RuntimeMessages(lvl):
            lines.append("%s: %s" % (str(lvl), m))
'''


def main():
    if not os.path.isfile(CODE_PATH):
        print("코드 원본이 없다: {}".format(CODE_PATH))
        return 2

    code = BRIDGE_CODE.format(
        inputs=repr(INPUTS), outputs=repr(OUTPUTS),
        wiring=repr(WIRING), share=repr(SHARE),
        code=CODE_PATH.replace("\\", "\\\\"),
        repo=REPO_ROOT.replace("\\", "\\\\"))

    with Bridge() as b:
        print(remote(b, code))
    return 0


if __name__ == "__main__":
    sys.exit(main())

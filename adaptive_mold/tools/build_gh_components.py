#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""AMv1 컴포넌트의 파라미터·배선·코드를 살아 있는 캔버스에 맞춘다.

`build_play_component.py` 를 일반화한 것이다 — 손댈 컴포넌트가 둘이 되었고,
파라미터를 추가할 때마다 임시 스크립트를 쓰는 것을 그만두려 만들었다.

**멱등하다.** 다시 돌려도 안전하다.

**두 가지 모드 — 남의 것은 건드리지 않는다.**

    reorder=True   정의 순서와 다르면 입력을 전부 다시 만든다. 그 전에
                   연결을 닉네임으로 기억해 복원한다. 순서가 깔끔해지지만
                   힌트 이름을 하나라도 틀리면 잘 돌던 컴포넌트가 깨진다.
    reorder=False  **추가·삭제만 한다. 기존 파라미터는 손대지 않는다.**
                   새 것은 뒤에 붙는다. 이미 잘 도는 컴포넌트에 입력 하나를
                   더할 때 쓴다 — 예: AMv1 Robot 의 targets 는 힌트가 없는
                   상태(System.Object)로 잘 돌고 있어 다시 만들 이유가 없다.

**코드는 저장소 파일에서 읽는다.** 브리지 JSON 에 한글을 태우지 않기 위해
경로만 넘기고 Rhino 쪽에서 `io.open(encoding="utf-8")` 로 읽는다
(rhino-bridge 스킬 규칙 4).

**코드를 넣으면 그 컴포넌트의 툴팁이 지워진다**(J-006 TRAP-04). 그래서 이 도구는
끝에 `apply_param_docs.py` 를 돌리라고 일러준다.

선결 조건: Rhino 8 + `mcpstart`, 캔버스에 AMv1 Inspect 가 있어야 한다
(파라미터 클래스의 원형을 거기서 얻는다).

사용:
    python adaptive_mold/tools/build_gh_components.py            # 전부
    python adaptive_mold/tools/build_gh_components.py Play       # 하나만
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SCRIPTS = os.path.join(REPO_ROOT, "gh_components", "gh_scripts")

sys.path.insert(0, HERE)
from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# 입력: (닉네임, 힌트, list접근?, 위젯)
#   힌트 None = 지정하지 않는다 (기존 것을 그대로 둔다)
#   위젯: None | ("slider", lo, hi, val, digits) | ("toggle", val) | ("path",)
PLAY_INPUTS = [
    ("platform_path", "GH_StringHint_CS",  False, ("path",)),
    ("pin_tops",      "GH_Point3dHint",    True,  None),
    ("base_plane",    "GH_PlaneHint",      False, None),
    ("pin_home",      "GH_DoubleHint_CS",  False, ("slider", 0, 400, 0, 0)),
    ("pin_speed",     "GH_DoubleHint_CS",  False, ("slider", 5, 300, 50, 0)),
    ("poses",         "GH_DoubleHint_CS",  True,  None),
    ("reach_err",     "GH_DoubleHint_CS",  True,  None),
    ("targets",       "GH_PlaneHint",      True,  None),
    ("move_kind",     "GH_StringHint_CS",  True,  None),
    ("robot_base",    "GH_PlaneHint",      False, None),
    ("base_pt",       "GH_Point3dHint",    False, None),
    # **Curve 로 받는다.** Rhino 에서 선은 LineCurve 객체이고, GH_Line 은 Rhino
    # 객체를 참조할 수 없다(실측). Line 힌트를 걸면 참조가 끊겨 선을 돌려도
    # 방향이 안 바뀐다. robot._direction_of 가 Curve·Line·Vector 를 다 받는다.
    ("base_dir",      "GH_CurveHint",      False, None),
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
    ("show_body",     "GH_BooleanHint_CS", False, ("toggle", True)),
    ("parts_file",    "GH_StringHint_CS",  False, None),
    ("mold_srf",      "GH_BrepHint",       False, None),
    ("stack",         "GH_DoubleHint_CS",  False, ("slider", 0, 100, 28, 0)),
    ("check_hit",     "GH_BooleanHint_CS", False, ("toggle", False)),
    ("hit_margin",    "GH_DoubleHint_CS",  False, ("slider", 0, 200, 30, 0)),
    ("hit_step",      "GH_IntegerHint_CS", False, ("slider", 1, 50, 1, 0)),
]

# AMv1 Robot — 이미 돌고 있으므로 **추가만** 한다 (reorder=False).
# 기존 것은 정의만 적어 두고 힌트를 None 으로 둬 손대지 않게 한다.
ROBOT_INPUTS = [
    ("platform_path", None, False, None),
    ("targets",       None, True,  None),
    ("move_kind",     None, True,  None),
    ("robot_base",    None, False, None),
    ("frame",         None, False, None),
    ("step",          None, False, None),
    ("iterations",    None, False, None),
    ("rot_weight",    None, False, None),
    ("compute",       None, False, None),
    ("base_pt",       "GH_Point3dHint", False, None),
    ("base_dir",      "GH_CurveHint",   False, None),   # Line 이 아니다 — 위 주석 참조
]

SPECS = {
    "Play": {
        "nick": "AMv1 Play",
        "code": os.path.join(SCRIPTS, "AMv1_Play.py"),
        "inputs": PLAY_INPUTS,
        "outputs": ["pins", "deck", "links", "body", "tcp", "roller",
                    "duration", "info"],
        "reorder": True,
        "anchor": "AMv1 Robot",
        "wiring": [
            ("pin_tops",  "AMv1 Inspect",    "pin_tops"),
            ("poses",     "AMv1 Robot",      "poses"),
            ("reach_err", "AMv1 Robot",      "reach_err"),
            ("targets",   "AMv1 RollerPath", "targets"),
            ("move_kind", "AMv1 RollerPath", "move_kind"),
        ],
        "share": [
            ("platform_path", "AMv1 Inspect",    "platform_path"),
            ("base_plane",    "AMv1 Inspect",    "base_plane"),
            ("robot_base",    "AMv1 Robot",      "robot_base"),
            ("base_pt",       "AMv1 Robot",      "base_pt"),
            ("base_dir",      "AMv1 Robot",      "base_dir"),
            ("roller_d",      "AMv1 RollerPath", "roller_d"),
            ("mold_srf",      "AMv1 RollerPath", "mold_srf"),
        ],
    },
    "Robot": {
        "nick": "AMv1 Robot",
        "code": os.path.join(SCRIPTS, "AMv1_Robot.py"),
        "inputs": ROBOT_INPUTS,
        "outputs": None,          # 건드리지 않는다
        "reorder": False,
        "anchor": None,
        "wiring": [],
        "share": [],
    },
}


BRIDGE_CODE = u'''
import io
import System
import System.Drawing as sd
import Grasshopper as ghk
import Grasshopper.Kernel as gk
import Grasshopper.Kernel.Special as ghs

NICK = "{nick}"
INPUTS = {inputs}
OUTPUTS = {outputs}
REORDER = {reorder}
ANCHOR = {anchor}
WIRING = {wiring}
SHARE = {share}
CODE_PATH = r"{code}"
REPO = r"{repo}"


def find(nick):
    for _d in [d for d in ghk.Instances.DocumentServer]:
        for _o in _d.Objects:
            if _o.NickName == nick:
                return _d, _o
    return None, None


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


def make_param(proto, nick, hint, is_list):
    p = System.Activator.CreateInstance(proto.GetType())
    p.Name = nick
    p.NickName = nick
    p.Description = nick
    p.Optional = True
    p.Access = (gk.GH_ParamAccess.list if is_list else gk.GH_ParamAccess.item)
    if hint:
        try:
            p.TypeHint = getattr(gk.Parameters.Hints, hint)()
        except Exception as ex:
            lines.append("  hint FAIL %s %s: %s" % (nick, hint, ex))
    return p


doc, insp = find("AMv1 Inspect")
if insp is None:
    lines.append("AMv1 Inspect not on canvas -- cannot clone param types")
else:
    _, comp = find(NICK)
    if comp is None:
        anchor = None
        if ANCHOR:
            _, anchor = find(ANCHOR)
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

    f = io.open(CODE_PATH, "r", encoding="utf-8")
    try:
        code = f.read()
    finally:
        f.close()
    if comp.Code != code:
        comp.Code = code
        lines.append("code %d chars (updated)" % len(code))
    else:
        lines.append("code %d chars (unchanged)" % len(code))

    proto = insp.Params.Input[0]
    want = [a for a, b, c, d in INPUTS]
    have = [p.NickName for p in comp.Params.Input]

    if REORDER and have != want:
        kept = {{}}
        for p in comp.Params.Input:
            if p.SourceCount:
                kept[p.NickName] = [s for s in p.Sources]
        lines.append("rebuild inputs (had %d, remembered %d wires)" % (
            len(have), len(kept)))
        while comp.Params.Input.Count > 0:
            comp.Params.UnregisterInputParameter(comp.Params.Input[0])
        for nick, hint, is_list, widget in INPUTS:
            p = make_param(proto, nick, hint, is_list)
            comp.Params.RegisterInputParam(p)
            for s in kept.get(nick, []):
                p.AddSource(s)
    else:
        # 추가·삭제만. **기존 파라미터는 손대지 않는다.**
        removed = []
        for p in list(comp.Params.Input):
            if p.NickName not in want:
                comp.Params.UnregisterInputParameter(p)
                removed.append(p.NickName)
        added = []
        for nick, hint, is_list, widget in INPUTS:
            if in_p(comp, nick) is not None:
                continue
            comp.Params.RegisterInputParam(
                make_param(proto, nick, hint, is_list))
            added.append(nick)
        lines.append("inputs: 추가 %s / 제거 %s" % (
            ", ".join(added) if added else "없음",
            ", ".join(removed) if removed else "없음"))

    # 힌트·접근방식 동기화. **추가/제거만으로는 못 잡는다** — 이름이 그대로면
    # 재구성이 일어나지 않으므로, 힌트를 고쳐도 캔버스에는 옛 힌트가 남는다
    # (실측: base_dir 을 Line -> Curve 로 바꿨는데 반영되지 않았다).
    fixed = []
    for nick, hint, is_list, widget in INPUTS:
        p = in_p(comp, nick)
        if p is None:
            continue
        if hint:
            cur = p.TypeHint.GetType().Name if p.TypeHint is not None else "None"
            if cur != hint:
                try:
                    p.TypeHint = getattr(gk.Parameters.Hints, hint)()
                    fixed.append("%s %s->%s" % (nick, cur, hint))
                except Exception as ex:
                    lines.append("  hint FAIL %s %s: %s" % (nick, hint, ex))
        want_access = (gk.GH_ParamAccess.list if is_list
                       else gk.GH_ParamAccess.item)
        if p.Access != want_access:
            p.Access = want_access
            fixed.append("%s access" % nick)
    if fixed:
        lines.append("고침: %s" % ", ".join(fixed))

    if OUTPUTS is not None:
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
            w.UserText = REPO
            w.NickName = nick
            w.Attributes.Pivot = sd.PointF(px - 560.0, y)
            doc.AddObject(w, False)
            p.AddSource(w)
            made.append(nick)
            row += 1

    lines.append("wired: %s" % (", ".join(wired) if wired else "none"))
    lines.append("widgets: %s" % (", ".join(made) if made else "none"))
    unwired = [p.NickName for p in comp.Params.Input if p.SourceCount == 0]
    lines.append("unwired: %s" % (", ".join(unwired) if unwired else "none"))

    comp.ExpireSolution(True)
    doc.NewSolution(False)

    lines.append("inputs %d / outputs %d" % (
        comp.Params.Input.Count, comp.Params.Output.Count))
    for lvl in (gk.GH_RuntimeMessageLevel.Error,
                gk.GH_RuntimeMessageLevel.Warning):
        for m in comp.RuntimeMessages(lvl):
            lines.append("%s: %s" % (str(lvl), m))
'''


def main(argv):
    names = argv if argv else list(SPECS.keys())
    bad = [n for n in names if n not in SPECS]
    if bad:
        print("모르는 이름: {}  (있는 것: {})".format(
            ", ".join(bad), ", ".join(sorted(SPECS))))
        return 2

    with Bridge() as b:
        for name in names:
            s = SPECS[name]
            if not os.path.isfile(s["code"]):
                print("코드 원본이 없다: {}".format(s["code"]))
                return 2
            code = BRIDGE_CODE.format(
                nick=s["nick"], inputs=repr(s["inputs"]),
                outputs=repr(s["outputs"]), reorder=repr(bool(s["reorder"])),
                anchor=repr(s["anchor"]), wiring=repr(s["wiring"]),
                share=repr(s["share"]),
                code=s["code"].replace("\\", "\\\\"),
                repo=REPO_ROOT.replace("\\", "\\\\"))
            print("=== {} ===".format(s["nick"]))
            print(remote(b, code))
            print("")

    print("코드를 넣으면 툴팁이 지워진다 — 이어서 돌릴 것:")
    print("  python adaptive_mold/tools/apply_param_docs.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

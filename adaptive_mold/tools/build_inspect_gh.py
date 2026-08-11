#! python 3
# -*- coding: utf-8 -*-
"""AMv1_Inspect 정의 파일(.gh)을 만들어내는 스크립트.

입력 11개를 손으로 만드는 대신 Grasshopper API에게 시킨다.
GhPython 컴포넌트 + 슬라이더/토글/패널을 배치하고 배선까지 한 뒤 저장한다.

**Rhino 안에서 실행** (ScriptEditor → 열기 → Run).
Grasshopper가 한 번은 로드돼 있어야 한다 — 먼저 `Grasshopper` 명령으로
캔버스를 띄운 뒤 이 스크립트를 돌릴 것.

출력: adaptive_mold/grasshopper/AMv1_Inspect.gh
"""

import os
import sys

import Rhino
import Grasshopper as gh
import Grasshopper.Kernel as ghk
import Grasshopper.Kernel.Special as ghs

import System
import System.Drawing


def _pt(x, y):
    """GH 캔버스 좌표. Attributes.Pivot은 Rhino의 Point2d가 아니라
    System.Drawing.PointF를 받는다."""
    return System.Drawing.PointF(float(x), float(y))


def _dec(v):
    return System.Decimal(float(v))

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = r"C:\Users\leeja\Documents\dev\26_AdaptiveMold_development\adaptive_mold\tools"

REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
SCRIPT_SRC = os.path.join(REPO_ROOT, "gh_components", "gh_scripts", "AMv1_Inspect.py")
OUT_DIR = os.path.join(REPO_ROOT, "adaptive_mold", "grasshopper")
OUT_GH = os.path.join(OUT_DIR, "AMv1_Inspect.gh")

_LOG = []


def log(m=""):
    print(m)
    _LOG.append(str(m))


# ── 입력 정의 ────────────────────────────────────────────
# (이름, 종류, 기본값/범위, 설명)
#   str    → GH_Panel 에 문자열
#   num    → GH_NumberSlider (min, max, value, 소수자리)
#   bool   → GH_BooleanToggle
#   geo    → 배선 없음. 사용자가 직접 곡면을 연결
#   plane  → 배선 없음 (비우면 WorldXY)

# 타입 힌트가 없으면 GhPython은 Rhino 문서 객체를 Guid로 넘긴다.
# 그러면 target_srf가 지오메트리가 아니라 Guid가 되어 "invalid"가 되고,
# base_plane은 "expected Plane, got Guid"로 터진다. 반드시 걸어야 한다.
HINTS = {
    "str":   "GH_StringHint_CS",
    "num":   "GH_DoubleHint_CS",
    "bool":  "GH_BooleanHint_CS",
    "geo":   "GH_BrepHint",
    "plane": "GH_PlaneHint",
}


def make_hint(kind):
    """Grasshopper.Kernel.Parameters.Hints 에서 힌트 인스턴스를 만든다."""
    name = HINTS.get(kind)
    if not name:
        return None
    try:
        cls = getattr(ghk.Parameters.Hints, name)
        return cls()
    except Exception as e:
        log("  [힌트 실패] {} -> {}".format(name, e))
        return None


INPUTS = [
    ("platform_path", "str",   REPO_ROOT,                 "repo root"),
    ("target_srf",    "geo",   None,                      "목표 곡면 — 직접 연결"),
    ("base_plane",    "plane", None,                      "비우면 WorldXY"),
    ("width",         "num",   (100.0, 4000.0, 1000.0, 0), "몰드 가로 mm"),
    ("length",        "num",   (100.0, 4000.0, 1000.0, 0), "몰드 세로 mm"),
    ("spacing",       "num",   (50.0, 500.0, 200.0, 0),    "핀 간격 mm"),
    ("max_height",    "num",   (50.0, 1000.0, 400.0, 0),   "최대 stroke mm"),
    ("min_height",    "num",   (0.0, 500.0, 0.0, 0),       "최소 stroke mm"),
    ("pin_radius",    "num",   (0.0, 100.0, 0.0, 1),       "0이면 자동"),
    ("normalized",    "bool",  False,                      "★ Phase B 회전 방식 전환"),
    ("compute",       "bool",  False,                      "계산 실행"),
]

OUTPUTS = [
    "pins_ok", "pins_clamped", "pins_ext", "pin_tops", "deck",
    "positioned", "extended", "envelope", "deviation", "info",
]


def make_python_component(code):
    """GhPython 컴포넌트를 만든다. Rhino 8에는 스크립트 컴포넌트가 여럿이라
    쓸 수 있는 것을 찾아 쓴다."""
    try:
        import GhPython
        comp = GhPython.Component.ZuiPythonComponent()
        comp.Code = code
        return comp, "GhPython.ZuiPythonComponent"
    except Exception as e:
        raise RuntimeError(
            "GhPython 컴포넌트를 만들 수 없습니다: {}\n"
            "Grasshopper를 한 번 띄운 뒤(명령: Grasshopper) 다시 실행하세요.".format(e))


def configure_params(comp):
    """입력/출력 파라미터를 정의대로 맞춘다."""
    # 기존 입력 전부 제거
    while comp.Params.Input.Count > 0:
        comp.Params.UnregisterInputParameter(comp.Params.Input[0])
    while comp.Params.Output.Count > 0:
        comp.Params.UnregisterOutputParameter(comp.Params.Output[0])

    for name, kind, _default, desc in INPUTS:
        p = ghk.Parameters.Param_ScriptVariable()
        p.Name = name
        p.NickName = name
        p.Description = desc
        p.Access = ghk.GH_ParamAccess.item
        p.Optional = True

        hint = make_hint(kind)
        if hint is not None:
            p.TypeHint = hint
            log("  힌트 {:<14} <- {}".format(name, HINTS[kind]))
        else:
            log("  힌트 {:<14} <- 없음(원시 Guid로 넘어올 수 있음)".format(name))

        comp.Params.RegisterInputParam(p)

    for name in OUTPUTS:
        p = ghk.Parameters.Param_GenericObject()
        p.Name = name
        p.NickName = name
        comp.Params.RegisterOutputParam(p)

    comp.Params.OnParametersChanged()
    try:
        comp.VariableParameterMaintenance()
    except Exception:
        pass


def add_slider(doc, x, y, lo, hi, val, digits, nick):
    s = ghs.GH_NumberSlider()
    s.CreateAttributes()
    s.Slider.DecimalPlaces = int(digits)
    s.Slider.Minimum = _dec(lo)
    s.Slider.Maximum = _dec(hi)
    try:
        s.SetSliderValue(_dec(val))
    except Exception:
        s.Slider.Value = _dec(val)
    s.NickName = nick
    s.Attributes.Pivot = _pt(x, y)
    doc.AddObject(s, False)
    return s


def add_toggle(doc, x, y, value, nick):
    t = ghs.GH_BooleanToggle()
    t.CreateAttributes()
    t.Value = bool(value)
    t.NickName = nick
    t.Attributes.Pivot = _pt(x, y)
    doc.AddObject(t, False)
    return t


def add_panel(doc, x, y, text, nick):
    p = ghs.GH_Panel()
    p.CreateAttributes()
    p.UserText = str(text)
    p.NickName = nick
    p.Attributes.Pivot = _pt(x, y)
    doc.AddObject(p, False)
    return p


def main():
    if not os.path.isfile(SCRIPT_SRC):
        raise RuntimeError("스크립트 원본이 없습니다: {}".format(SCRIPT_SRC))

    with open(SCRIPT_SRC, "r", encoding="utf-8") as f:
        code = f.read()

    log("원본 코드: {} ({} 자)".format(SCRIPT_SRC, len(code)))

    # GH_Document.DisplayName은 읽기 전용 — 파일명에서 파생된다.
    doc = ghk.GH_Document()

    comp, kind = make_python_component(code)
    log("컴포넌트: {}".format(kind))

    comp.CreateAttributes()
    comp.NickName = "AMv1 Inspect"
    comp.Attributes.Pivot = _pt(520, 240)
    configure_params(comp)
    doc.AddObject(comp, False)

    # 입력 위젯 배치 + 배선
    y = 60
    for idx, (name, kind_, default, desc) in enumerate(INPUTS):
        param = comp.Params.Input[idx]
        if kind_ == "num":
            lo, hi, val, digits = default
            w = add_slider(doc, 200, y, lo, hi, val, digits, name)
            param.AddSource(w)
        elif kind_ == "bool":
            w = add_toggle(doc, 240, y, default, name)
            param.AddSource(w)
        elif kind_ == "str":
            w = add_panel(doc, 60, y, default, name)
            param.AddSource(w)
        else:
            w = None  # geo / plane 은 사용자가 직접 연결
        y += 44

    # info 출력용 패널
    info_panel = add_panel(doc, 800, 240, "", "info")
    for i, oname in enumerate(OUTPUTS):
        if oname == "info":
            info_panel.AddSource(comp.Params.Output[i])
            break

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    io = ghk.GH_DocumentIO(doc)
    ok = io.SaveQuiet(OUT_GH)
    log("저장 {}: {}".format("성공" if ok else "실패", OUT_GH))
    log("")
    log("입력 {}개 / 출력 {}개".format(len(INPUTS), len(OUTPUTS)))
    log("target_srf 와 base_plane 만 직접 연결하시면 됩니다.")

    with open(os.path.join(OUT_DIR, "_build_log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))


try:
    main()
except Exception:
    import traceback
    tb = traceback.format_exc()
    print(tb)
    try:
        if not os.path.isdir(OUT_DIR):
            os.makedirs(OUT_DIR)
        with open(os.path.join(OUT_DIR, "_build_log.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(_LOG) + "\n\n[예외]\n" + tb)
    except Exception:
        pass
    raise

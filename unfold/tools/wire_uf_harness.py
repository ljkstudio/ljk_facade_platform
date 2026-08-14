#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""UFv1 컴포넌트에 시험용 입력을 물린다 — 경로 패널 · 곡면 참조 · run 토글.

    python unfold/tools/wire_uf_harness.py [panel_dome] [edge=60] [iters=80]

이름 인자는 Rhino 문서의 **객체 이름**이다 (`panel_flat` / `panel_tilt10` /
`panel_cylinder` / `panel_dome` / `panel_saddle`). 기본은 `panel_flat` —
σ=1 이 나와야 하는 가장 강한 정상성 검사다.

`edge=` `allow=` `iters=` `maxverts=` 는 슬라이더 값이다. 주지 않으면 컴포넌트
기본값과 같은 값(40 / 15 / 30 / 5000)으로 맞춘다 — **매번 명시적으로 맞춘다.**
남아 있던 값으로 돌면 어제의 슬라이더가 오늘의 결과를 설명하게 된다.

멱등하다. 이미 물려 있으면 참조 대상만 바꾼다.

**참조는 걸었다고 믿지 않는다** (rhino-bridge T-03): `SetPersistentData` 뒤에
`PersistentData` 를 다시 읽어 `ReferenceID` 를 대조하고, 안 맞으면 FAIL 로 찍는다.
예외가 없는 것이 근거가 아니다 — 잘못된 타입에 참조를 걸면 조용히 버려진다.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.expanduser(r"~\.claude\skills\rhino-bridge\scripts"))

from rhino_bridge import Bridge, remote  # noqa: E402

BODY = u'''
import System.Drawing as sd

REPO = REPOPATH
TARGET = TARGETNAME

doc = None
comps = {}
for d in [x for x in gh.Instances.DocumentServer]:
    for o in d.Objects:
        if o.NickName in ("UFv1 Material", "UFv1 Flatten"):
            doc = d
            comps[o.NickName] = o
if doc is None:
    lines.append("FAIL: UFv1 컴포넌트가 캔버스에 없다")
else:
    have = {}
    for o in doc.Objects:
        have[o.NickName] = o

    def put(obj, nick, x, y):
        obj.CreateAttributes()
        obj.Attributes.Pivot = sd.PointF(x, y)
        obj.NickName = nick
        doc.AddObject(obj, False)
        return obj

    def wire(comp, in_nick, src):
        for p in comp.Params.Input:
            if p.NickName == in_nick:
                for s in [q for q in p.Sources]:
                    p.RemoveSource(s)
                p.AddSource(src)
                return "wired %s.%s" % (comp.NickName, in_nick)
        return "FAIL: %s 에 입력 %s 가 없다" % (comp.NickName, in_nick)

    # ── 경로 패널
    pan = have.get("uf_path")
    if pan is None:
        pan = put(gh.Kernel.Special.GH_Panel(), "uf_path", -260.0, 980.0)
        lines.append("added uf_path")
    pan.UserText = REPO
    pan.ExpireSolution(True)

    # ── 곡면 참조 (Brep — Rhino 에 객체로 존재하는 타입이라 참조가 걸린다)
    srf = have.get("uf_srf")
    if srf is None:
        srf = put(gh.Kernel.Parameters.Param_Brep(), "uf_srf", -260.0, 1080.0)
        lines.append("added uf_srf")

    rdoc = Rhino.RhinoDoc.ActiveDoc
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True          # 시험 패널은 전부 숨겨져 있다
    st.NormalObjects = True
    st.LockedObjects = True
    found = None
    for o in rdoc.Objects.GetObjectList(st):
        if o.Attributes.Name == TARGET:
            found = o
    if found is None:
        lines.append("FAIL: Rhino 에 '%s' 라는 객체가 없다" % TARGET)
    else:
        gb = gh.Kernel.Types.GH_Brep(found.Geometry)
        gb.ReferenceID = found.Id
        srf.PersistentData.Clear()
        srf.PersistentData.Append(gb)
        srf.ExpireSolution(True)
        # 걸렸다고 믿지 않는다 — 되읽어 대조한다
        got = None
        for item in srf.PersistentData.AllData(True):
            got = item
        if got is None:
            lines.append("FAIL: PersistentData 가 비었다")
        elif str(got.ReferenceID) != str(found.Id):
            lines.append("FAIL: 참조가 조용히 버려졌다 refid=%s" % got.ReferenceID)
        else:
            lines.append("srf ref OK  %s  refid=%s  isref=%s"
                         % (TARGET, got.ReferenceID, got.IsReferencedGeometry))

    # ── 수치 슬라이더 (없으면 만들고, 값은 항상 인자대로 맞춘다)
    SLIDERS = [
        ("uf_edge",      "edge_mm",   "10<EDGE<200",     1, -260.0, 1280.0),
        ("uf_allow",     "allow_mm",  "0<ALLOW<100",     1, -260.0, 1340.0),
        ("uf_iters",     "iters",     "5<ITERS<300",     0, -260.0, 1400.0),
        ("uf_maxverts",  "max_verts", "500<MAXV<40000",  0, -260.0, 1460.0),
    ]
    made = {}
    for nick, target_in, init, digits, x, y in SLIDERS:
        sl = have.get(nick)
        if sl is None:
            sl = put(gh.Kernel.Special.GH_NumberSlider(), nick, x, y)
            lines.append("added %s" % nick)
        sl.SetInitCode(init)
        sl.Slider.DecimalPlaces = digits
        sl.ExpireSolution(True)
        made[target_in] = sl

    # ── 물성 (Material 쪽). 텍스트는 패널, 수치는 슬라이더
    #
    # **인자를 준 때만 물린다.** 슬라이더는 "값 없음"을 표현하지 못한다 —
    # elong_max 를 0 으로 물리면 MaterialProps 가 "0 초과여야 한다"로 거부하고
    # props 가 통째로 None 이 되어, 미판정(값 없음)과 입력 오류가 뒤섞인다.
    MAT_TEXT = [] if not MATFLAG else [("uf_matname", "name", MATNAME, 200.0, 980.0),
                ("uf_source", "source", MATSOURCE, 200.0, 1060.0)]
    mat_in = {}
    for nick, target_in, text, x, y in MAT_TEXT:
        pn = have.get(nick)
        if pn is None:
            pn = put(gh.Kernel.Special.GH_Panel(), nick, x, y)
            lines.append("added %s" % nick)
        pn.UserText = text
        pn.ExpireSolution(True)
        mat_in[target_in] = pn

    MAT_NUM = [] if not MATFLAG else [
               ("uf_thick", "thickness", "0.5<THICK<10", 1, 200.0, 1140.0),
               ("uf_elong", "elong_max", "0<ELONG<0.5", 3, 200.0, 1200.0),
               ("uf_penalty", "wrinkle_penalty", "1<PENALTY<10", 1, 200.0, 1260.0)]
    for nick, target_in, init, digits, x, y in MAT_NUM:
        sl = have.get(nick)
        if sl is None:
            sl = put(gh.Kernel.Special.GH_NumberSlider(), nick, x, y)
            lines.append("added %s" % nick)
        sl.SetInitCode(init)
        sl.Slider.DecimalPlaces = digits
        sl.ExpireSolution(True)
        mat_in[target_in] = sl

    # ── run 토글
    tog = have.get("uf_run")
    if tog is None:
        tog = put(gh.Kernel.Special.GH_BooleanToggle(), "uf_run", -260.0, 1180.0)
        tog.Value = False
        lines.append("added uf_run (False)")
    lines.append("uf_run = %s" % tog.Value)

    fl = comps.get("UFv1 Flatten")
    mt = comps.get("UFv1 Material")
    if fl is not None:
        lines.append(wire(fl, "platform_path", pan))
        lines.append(wire(fl, "srf", srf))
        lines.append(wire(fl, "run", tog))
        for target_in, sl in made.items():
            lines.append(wire(fl, target_in, sl))
    if mt is not None:
        lines.append(wire(mt, "platform_path", pan))
        for target_in, src in mat_in.items():
            lines.append(wire(mt, target_in, src))
        if fl is not None:
            for p in mt.Params.Output:
                if p.NickName == "props":
                    lines.append(wire(fl, "props", p))

    doc.NewSolution(False)
    for nick in ("UFv1 Material", "UFv1 Flatten"):
        c = comps.get(nick)
        if c is None:
            continue
        srcs = []
        for p in c.Params.Input:
            srcs.append("%s<-%d" % (p.NickName, p.SourceCount))
        lines.append("%-14s %s" % (nick, " ".join(srcs)))
'''


DEFAULTS = {"EDGE": "40", "ALLOW": "15", "ITERS": "30", "MAXV": "5000",
            "THICK": "3", "ELONG": "0.12", "PENALTY": "1",
            "MATNAME": "''", "MATSOURCE": "''", "MATFLAG": "False"}
KEYS = {"edge": "EDGE", "allow": "ALLOW", "iters": "ITERS", "maxverts": "MAXV",
        "thick": "THICK", "elong": "ELONG", "penalty": "PENALTY",
        "name": "MATNAME", "source": "MATSOURCE"}
QUOTED = ("MATNAME", "MATSOURCE")      # 파이썬 문자열로 들어가야 한다


def main():
    args = [a for a in sys.argv[1:]]
    target = "panel_flat"
    vals = dict(DEFAULTS)
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            key = KEYS.get(k.lstrip("-"))
            if key is None:
                print("모르는 인자: %s (%s)" % (a, " ".join(sorted(KEYS))))
                return 2
            vals[key] = repr(v) if key in QUOTED else v
            if key in ("THICK", "ELONG", "PENALTY", "MATNAME", "MATSOURCE"):
                vals["MATFLAG"] = "True"
        else:
            target = a
    # 본문 안에 %s 서식이 많아 % 치환은 못 쓴다 — 빌더와 같은 방식으로 바꾼다
    body = BODY.replace("REPOPATH", repr(REPO)).replace("TARGETNAME", repr(target))
    for k, v in vals.items():
        body = body.replace(k, v)
    with Bridge(timeout=180) as b:
        text = remote(b, body)
    print(text)
    return 1 if "FAIL" in text else 0


if __name__ == "__main__":
    sys.exit(main())

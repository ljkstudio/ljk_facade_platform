#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""UFv1 Flatten 을 한 번 돌리고 **출력값과 런타임 메시지로** 판정한다.

    python unfold/tools/run_uf_test.py

캔버스 모양은 근거가 아니다 (gh-component-dev §5). 여기서 읽는 것:

  · 두 컴포넌트의 RuntimeMessages (Error/Warning/Remark)
  · Flatten 의 info · warn 전문
  · flat 메쉬의 정점·면 수, blank 곡선의 길이·닫힘 여부
  · flat 의 바운딩박스가 blank 안에 들어가는가 (재단선이 평탄화 경계를 침범하지 않는다)

**끝나면 run 토글을 원래대로 끈다.** 켜 둔 채로 두면 캔버스를 만질 때마다
UI 스레드에서 다시 돈다.
"""

import os
import sys

sys.path.insert(0, os.path.expanduser(r"~\.claude\skills\rhino-bridge\scripts"))

from rhino_bridge import Bridge, remote  # noqa: E402

BODY = u'''
import time

doc = None
comps = {}
tog = None
srf = None
for d in [x for x in gh.Instances.DocumentServer]:
    for o in d.Objects:
        if o.NickName in ("UFv1 Material", "UFv1 Flatten"):
            doc = d
            comps[o.NickName] = o
        if o.NickName == "uf_run":
            tog = o
        if o.NickName == "uf_srf":
            srf = o

if doc is None or "UFv1 Flatten" not in comps:
    lines.append("FAIL: UFv1 Flatten 이 캔버스에 없다")
elif tog is None:
    lines.append("FAIL: uf_run 토글이 없다 — wire_uf_harness.py 를 먼저 돌린다")
else:
    ref = "?"
    if srf is not None:
        for item in srf.PersistentData.AllData(True):
            ref = str(item.ReferenceID)
    rdoc = Rhino.RhinoDoc.ActiveDoc
    name = "?"
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    st.NormalObjects = True
    st.LockedObjects = True
    for o in rdoc.Objects.GetObjectList(st):
        if str(o.Id) == ref:
            name = o.Attributes.Name
    lines.append("target = %s (%s)" % (name, ref))

    tog.Value = True
    tog.ExpireSolution(True)
    comps["UFv1 Flatten"].ExpireSolution(True)
    t0 = time.time()
    doc.NewSolution(False)
    dt = time.time() - t0
    lines.append("solution %.2f s" % dt)

    LEVELS = [("Error", gh.Kernel.GH_RuntimeMessageLevel.Error),
              ("Warning", gh.Kernel.GH_RuntimeMessageLevel.Warning),
              ("Remark", gh.Kernel.GH_RuntimeMessageLevel.Remark)]
    for nick in ("UFv1 Material", "UFv1 Flatten"):
        c = comps.get(nick)
        if c is None:
            continue
        for label, lv in LEVELS:
            for m in c.RuntimeMessages(lv):
                lines.append("[%s] %s: %s" % (nick, label, m))

    def out_items(comp, nick):
        for p in comp.Params.Output:
            if p.NickName == nick:
                return [x for x in p.VolatileData.AllData(True)]
        return []

    fl = comps["UFv1 Flatten"]

    lines.append("")
    lines.append("── info ──")
    for it in out_items(fl, "info"):
        lines.append(str(it.Value))
    lines.append("")
    lines.append("── warn ──")
    ws = out_items(fl, "warn")
    if not ws:
        lines.append("(비어 있다 — 통과 항목도 안 적혔다면 그것 자체가 문제다)")
    for it in ws:
        lines.append("  * " + str(it.Value))

    lines.append("")
    lines.append("── geometry ──")
    fm = out_items(fl, "flat")
    if not fm:
        lines.append("flat  : 없음")
    else:
        m = fm[0].Value
        bb = m.GetBoundingBox(True)
        lines.append("flat  : verts=%d faces=%d bbox=%.1f x %.1f x %.1f"
                     % (m.Vertices.Count, m.Faces.Count,
                        bb.Max.X - bb.Min.X, bb.Max.Y - bb.Min.Y, bb.Max.Z - bb.Min.Z))
    sm = out_items(fl, "strain")
    lines.append("strain: %s" % ("있음" if sm else "없음"))
    bl = out_items(fl, "blank")
    if not bl:
        lines.append("blank : 없음")
    else:
        crv = bl[0].Value
        lines.append("blank : 길이 %.1f mm  닫힘=%s  점=%s"
                     % (crv.GetLength(), crv.IsClosed,
                        crv.PointCount if hasattr(crv, "PointCount") else "?"))
        if fm:
            # 재단선이 평탄화 경계를 침범하지 않는가 — 안쪽 판정을 좌표로 한다
            m = fm[0].Value
            inside = 0
            outside = 0
            for v in m.Vertices:
                p = rg.Point3d(v.X, v.Y, 0.0)
                rel = crv.Contains(p, rg.Plane.WorldXY, 0.01)
                if str(rel) == "Inside":
                    inside += 1
                else:
                    outside += 1
            lines.append("flat 정점 %d개 중 blank 안쪽 %d / 바깥 %d" % (inside + outside, inside, outside))

    tog.Value = False
    tog.ExpireSolution(True)
    doc.NewSolution(False)
    lines.append("")
    lines.append("run 토글을 다시 껐다")
'''


def main():
    with Bridge(timeout=600) as b:
        text = remote(b, BODY)
    print(text)
    return 1 if "FAIL" in text else 0


if __name__ == "__main__":
    sys.exit(main())

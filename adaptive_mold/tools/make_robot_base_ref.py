#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""로봇 베이스를 정할 점·선을 Rhino 에 만들고 GH 파라미터로 참조해 물린다.

목적은 **Rhino 에서 점을 끌면 로봇이 따라오게** 하는 것이다. Plane 을 GH 에서
조립하는 것보다 점을 찍고 선을 긋는 편이 훨씬 빠르다.

만드는 것:
    Rhino 레이어 `robot_base` 에
      점  `robot_base_pt`   — 베이스 원점
      선  `robot_base_dir`  — 로봇이 바라보는 방향
    GH 캔버스에
      Point 파라미터 / Line 파라미터 (위 객체를 **참조**한다)
      → AMv1 Robot 과 AMv1 Play 의 base_pt / base_dir 에 배선

**처음 위치는 지금 쓰이는 자동값과 같게 잡는다** — 타겟 바운딩박스 중심에서
-X 로 1900 mm, 방향은 중심을 향한다. 그래서 물리는 순간 로봇이 튀지 않는다.
튀면 무엇이 바뀐 것인지 알 수 없게 된다.

**이름으로 찾아 재사용한다.** 다시 돌려도 객체가 늘지 않고, 이미 옮겨 둔 위치를
덮어쓰지 않는다.

선결 조건: Rhino 8 + `mcpstart`, 캔버스에 AMv1 RollerPath(타겟)·Robot·Play.

사용:
    python adaptive_mold/tools/make_robot_base_ref.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# 비ASCII 를 넣지 않는다 — 응답 JSON 인코더가 죽는다
BRIDGE_CODE = u'''
import System
import System.Drawing as sd
import Rhino.Geometry as rgg
import Grasshopper as ghk
import Grasshopper.Kernel as gk

LAYER = "robot_base"
PT_NAME = "robot_base_pt"
LN_NAME = "robot_base_dir"
DIR_LEN = 900.0
OFFSET = 1900.0        # robot.DEFAULT_BASE_OFFSET_MM

doc = Rhino.RhinoDoc.ActiveDoc


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


ghdoc, rp = find("AMv1 RollerPath")
_, robot = find("AMv1 Robot")
_, play = find("AMv1 Play")

if rp is None or robot is None:
    lines.append("AMv1 RollerPath / Robot not on canvas")
else:
    # ---- 타겟 중심 (자동 기본값과 같은 자리에 두기 위해) ----
    pts = []
    q = None
    for p in rp.Params.Output:
        if p.NickName == "targets":
            q = p
    if q is not None:
        for it in q.VolatileData.AllData(True):
            try:
                pl = it.Value
                pts.append(rgg.Point3d(pl.Origin))
            except Exception:
                pass
    if pts:
        c = rgg.BoundingBox(pts).Center
    else:
        c = rgg.Point3d(500.0, 500.0, 0.0)
        lines.append("targets empty -- fallback center used")
    origin = rgg.Point3d(c.X - OFFSET, c.Y, 0.0)
    lines.append("target center (%.0f, %.0f, %.0f) -> base (%.0f, %.0f, %.0f)" % (
        c.X, c.Y, c.Z, origin.X, origin.Y, origin.Z))

    # ---- 레이어 ----
    li = -1
    for i in range(doc.Layers.Count):
        L = doc.Layers[i]
        if (not L.IsDeleted) and L.Name == LAYER:
            li = i
    if li < 0:
        L = Rhino.DocObjects.Layer()
        L.Name = LAYER
        L.Color = sd.Color.FromArgb(255, 40, 120, 200)
        li = doc.Layers.Add(L)
        lines.append("layer created idx=%d" % li)
    else:
        lines.append("layer exists idx=%d" % li)

    # ---- 이름으로 기존 객체 찾기 ----
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    existing = {}
    for o in doc.Objects.GetObjectList(st):
        nm = o.Attributes.Name
        if nm in (PT_NAME, LN_NAME):
            existing[nm] = o

    att = Rhino.DocObjects.ObjectAttributes()
    att.LayerIndex = li

    pt_id = None
    if PT_NAME in existing:
        pt_id = existing[PT_NAME].Id
        lines.append("point reused (not moved)")
    else:
        a = att.Duplicate()
        a.Name = PT_NAME
        pt_id = doc.Objects.AddPoint(origin, a)
        lines.append("point created")

    ln_id = None
    if LN_NAME in existing:
        ln_id = existing[LN_NAME].Id
        lines.append("line reused (not moved)")
    else:
        v = rgg.Vector3d(c - origin)
        v.Z = 0.0
        v.Unitize()
        a = att.Duplicate()
        a.Name = LN_NAME
        ln_id = doc.Objects.AddLine(origin, origin + v * DIR_LEN, a)
        lines.append("line created")

    doc.Views.Redraw()

    # ---- GH 파라미터 (Rhino 객체를 참조) ----
    def ensure_ref(kind, nick, guid, x, y):
        """Param_Point / Param_Curve 를 만들어 Rhino 객체를 **참조**하게 한다.

        **Param_Line 을 쓰면 안 된다 (실측).** Rhino 에서 선은 LineCurve 객체이고
        GH_Line 은 참조 가능한 타입이 아니다 — ReferenceID 를 넣어도 예외 없이
        조용히 버려져 `refid=00000000-...` 가 되고, 값이 박힌 채로 남는다.
        그러면 Rhino 에서 선을 돌려도 로봇 방향이 안 바뀐다.
        Curve 로 받으면 참조가 살아 있고, robot._direction_of 가 Curve 를 받는다.

        **예외가 없는 것을 근거로 삼지 않는다.** 넣은 뒤 다시 읽어 참조가 실제로
        걸렸는지 확인해 돌려준다.
        """
        want_type = ("Param_Point" if kind == "pt" else "Param_Curve")
        _, ex = find(nick)
        if ex is not None:
            if ex.GetType().Name == want_type:
                return ex, "exists"
            # 타입이 다르면 버리고 다시 만든다 (Param_Line -> Param_Curve 교체)
            for comp in (robot, play):
                if comp is None:
                    continue
                for p in comp.Params.Input:
                    if ex in [s for s in p.Sources]:
                        p.RemoveSource(ex)
            ghdoc.RemoveObject(ex, False)
            lines.append("  replaced %s (%s -> %s)" % (
                nick, ex.GetType().Name, want_type))

        p = (gk.Parameters.Param_Point() if kind == "pt"
             else gk.Parameters.Param_Curve())
        p.CreateAttributes()
        p.NickName = nick
        p.Attributes.Pivot = sd.PointF(x, y)
        ghdoc.AddObject(p, False)

        obj = doc.Objects.FindId(guid)
        if kind == "pt":
            goo = ghk.Kernel.Types.GH_Point(obj.Geometry.Location)
        else:
            goo = ghk.Kernel.Types.GH_Curve(obj.Geometry.DuplicateCurve())
        try:
            goo.ReferenceID = guid
            goo.LoadGeometry(doc)
        except Exception as ex2:
            lines.append("  reference set FAIL %s: %s" % (nick, ex2))
        p.SetPersistentData(goo)
        p.ExpireSolution(False)

        # 확인 — 넣은 것과 들어간 것이 같은지
        ok = False
        for it in p.PersistentData.AllData(True):
            if str(it.ReferenceID) == str(guid):
                ok = True
        return p, "created/" + ("referenced" if ok else "VALUE ONLY (참조 실패)")

    base_x = robot.Attributes.Pivot.X - 700.0
    base_y = robot.Attributes.Pivot.Y - 40.0
    p_pt, s1 = ensure_ref("pt", "robot_base_pt", pt_id, base_x, base_y)
    p_ln, s2 = ensure_ref("ln", "robot_base_dir", ln_id, base_x, base_y + 30.0)
    lines.append("param point: %s" % s1)
    lines.append("param line:  %s" % s2)

    # ---- 배선 ----
    wired = []
    for comp in (robot, play):
        if comp is None:
            continue
        for nick, src in (("base_pt", p_pt), ("base_dir", p_ln)):
            tgt = in_p(comp, nick)
            if tgt is None:
                lines.append("  %s has no %s" % (comp.NickName, nick))
                continue
            if tgt.SourceCount:
                continue
            tgt.AddSource(src)
            wired.append("%s.%s" % (comp.NickName, nick))
    lines.append("wired: %s" % (", ".join(wired) if wired else "none"))

    for comp in (robot, play):
        if comp is not None:
            comp.ExpireSolution(True)
    ghdoc.NewSolution(False)

    # ---- 실제로 들어갔는지 ----
    for comp in (robot, play):
        if comp is None:
            continue
        got = []
        for nick in ("base_pt", "base_dir"):
            p = in_p(comp, nick)
            n = 0
            if p is not None:
                try:
                    n = len([x for x in p.VolatileData.AllData(True)])
                except Exception:
                    pass
            got.append("%s=%d" % (nick, n))
        lines.append("%s: %s" % (comp.NickName, " ".join(got)))
'''


def main():
    with Bridge() as b:
        print(remote(b, BRIDGE_CODE))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#! python 3
# -*- coding: utf-8 -*-
"""IRB6700 GLB 파트 9개를 읽어 `irb6700_parts.3dm` 으로 만든다.

**Rhino 안에서 CPython 3 로 실행한다.**

    python ~/.claude/skills/rhino-bridge/scripts/rhino_bridge.py run-file \\
        adaptive_mold/tools/import_robot_glb.py

원본: ljks_website_v2/irb6700-robot-demo/model/source-parts/*.glb
      (BASE, LINK01~06, CYLINDER, ROD — 9개)

**압축된 통합본(irb6700.glb)을 쓰지 않는 이유:** Draco 압축본이라 Rhino 임포터의
지원 여부가 불확실하고, 노드 이름을 파싱해야 한다. 소스 파트는 비압축이고
**파일명이 곧 링크 이름**이라 매핑에 해석이 필요 없다.

**파트는 이미 공통 좌표계(Z-up, meter)에 제자리로 놓여 있다**(원본 merge_glb.py).
그래서 임포트한 그대로가 **영각(零角) 자세**이고, 관절 j 의 파트에
`joint_frames(pose)[j] * Translation(-pivot_j)` 를 걸면 그 자세가 된다.

──────────────────────────────────────────────────────────
실측 함정 둘 (2026-08-13)
──────────────────────────────────────────────────────────

**1. glTF 는 Y-up 이라 Z 축이 -Y 로 들어온다.**
Rhino 임포터가 Y-up→Z-up 변환을 거는데, 원본이 이미 Z-up 이라 **한 번 더 돈다.**
X 는 맞고(link6 x=1875.8 ≈ 1.876 m) Z 만 -Y 로 간다 (base z[-360,360],
link5 z[-92,91] — 실제로는 y 성분이다).
그래서 **X 축 -90° 회전으로 되돌린다.** 다만 하드코딩하지 않는다 —
`robot.py` 의 J6 피벗이 link6 바운딩박스 안에 들어가는 후보를 골라 쓴다.
이 방식이면 원본이 다시 내보내지면서 규약이 바뀌어도 도구가 알아서 맞춘다.

**2. 임포트와 정리 사이에서 예외가 나면 문서가 오염된다.**
처음 판에서 저장 직전에 터져 **메시 4,592개가 test_panels.3dm 에 남았다.**
그래서 정리를 `finally` 로 옮겼다. 열려 있는 문서를 건드리는 도구는 예외
경로에서도 원복되어야 한다.

**단위 판정에 Z 를 쓰지 않는다** — 함정 1 때문에 Z 는 믿을 수 없다. 전 파트의
최대 절대좌표로 판정한다(로봇은 약 1.9 m = 1900 mm 를 차지한다).

로그: adaptive_mold/grasshopper/_robot_import_log.txt
"""

import math
import os
import sys

import Rhino
import Rhino.Geometry as rg


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
GH_DIR = os.path.normpath(os.path.join(HERE, "..", "grasshopper"))
SRC_DIR = os.path.join(REPO_ROOT, "adaptive_mold", "src")
LOG = os.path.join(GH_DIR, "_robot_import_log.txt")
OUT_3DM = os.path.join(GH_DIR, "irb6700_parts.3dm")

SRC = os.path.normpath(os.path.join(
    REPO_ROOT, "..", "ljks_website_v2", "irb6700-robot-demo",
    "model", "source-parts"))

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
import robot as rb   # noqa: E402  피벗의 정본

PARTS = [
    ("BASE.glb",     "base"),
    ("LINK01.glb",   "link1"),
    ("LINK02.glb",   "link2"),
    ("LINK03.glb",   "link3"),
    ("LINK04.glb",   "link4"),
    ("LINK05.glb",   "link5"),
    ("LINK06.glb",   "link6"),
    ("CYLINDER.glb", "cylinder"),
    ("ROD.glb",      "rod"),
]

# KINEMATICS.md 의 world z 범위 (m → mm). 최종 대조용.
EXPECT_Z_MM = {
    "base":  (0, 370),
    "link1": (220, 1020),
    "link2": (590, 2060),
    "link3": (1730, 2280),
    "link4": (1970, 2240),
    "link5": (2000, 2190),
    "link6": (2010, 2200),
}

# 표시용 메시 목표 면수. 재생이 21 fps 로 돌아야 하므로 원본 밀도를 쓰지 않는다.
TARGET_FACES_TOTAL = 120000

_lines = []
_touched = []      # 문서에 생긴 객체 — finally 에서 반드시 지운다


def log(msg=""):
    print(msg)
    _lines.append(str(msg))


def all_ids(doc):
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    st.DeletedObjects = False
    return set(o.Id for o in doc.Objects.GetObjectList(st))


def import_file(doc, path):
    """파일을 임포트하고 **새로 생긴 객체만** 돌려준다.

    이름·레이어로 고르면 사용자 객체를 지울 위험이 있다. id 차집합이 안전하다.
    """
    before = all_ids(doc)
    ok = Rhino.RhinoApp.RunScript('_-Import "{}" _Enter'.format(path), False)
    after = all_ids(doc)
    new = [doc.Objects.FindId(i) for i in (after - before)]
    return ok, [o for o in new if o is not None]


def as_mesh(objs):
    """문서 객체 목록을 하나의 메시로."""
    meshes = []
    for o in objs:
        g = o.Geometry
        if isinstance(g, rg.Mesh):
            meshes.append(g.DuplicateMesh())
        elif isinstance(g, rg.Brep):
            for m in rg.Mesh.CreateFromBrep(
                    g, rg.MeshingParameters.Default) or []:
                meshes.append(m)
    if not meshes:
        return None
    merged = rg.Mesh()
    for m in meshes:
        merged.Append(m)
    merged.Faces.ConvertQuadsToTriangles()
    merged.Normals.ComputeNormals()
    merged.Compact()
    return merged


def bbox_distance(bb, pt):
    """점에서 바운딩박스까지 거리 (안이면 0)."""
    dx = max(bb.Min.X - pt.X, 0.0, pt.X - bb.Max.X)
    dy = max(bb.Min.Y - pt.Y, 0.0, pt.Y - bb.Max.Y)
    dz = max(bb.Min.Z - pt.Z, 0.0, pt.Z - bb.Max.Z)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def pick_axis_fix(parts):
    """축 보정 후보를 J6 피벗으로 채점해 고른다.

    근거: link6 은 툴 플랜지이므로 J6 회전 피벗이 그 안에 있어야 한다.
    이것이 성립하지 않는 좌표계는 틀린 것이다.
    """
    j6 = rb.PIVOTS_M["j6"]
    target = rg.Point3d(j6[0] * rb.MM, j6[1] * rb.MM, j6[2] * rb.MM)
    link6 = dict(parts).get("link6")

    cands = [
        ("그대로", rg.Transform.Identity),
        ("X -90", rg.Transform.Rotation(-math.pi / 2.0, rg.Vector3d.XAxis,
                                        rg.Point3d.Origin)),
        ("X +90", rg.Transform.Rotation(math.pi / 2.0, rg.Vector3d.XAxis,
                                        rg.Point3d.Origin)),
    ]

    log("축 보정 채점 — J6 피벗 ({:.0f}, {:.0f}, {:.0f}) 이 link6 안에 있어야 한다".format(
        target.X, target.Y, target.Z))

    best = None
    for name, xf in cands:
        if link6 is None:
            break
        m = link6.DuplicateMesh()
        m.Transform(xf)
        bb = m.GetBoundingBox(True)
        d = bbox_distance(bb, target)

        # 로봇은 바닥에 선다 — 어떤 파트도 z 가 음수로 크게 내려가면 안 된다
        zmin = min(_transformed_bbox(p, xf).Min.Z for _, p in parts)
        log("  {:<7} J6 거리 {:>8.1f} mm   전 파트 최소 z {:>8.1f}".format(
            name, d, zmin))
        score = d + (0.0 if zmin > -1.0 else 1e6)
        if best is None or score < best[0]:
            best = (score, name, xf)

    if best is None:
        return "없음", rg.Transform.Identity
    log("  -> {} 채택".format(best[1]))
    return best[1], best[2]


def _transformed_bbox(mesh, xf):
    m = mesh.DuplicateMesh()
    m.Transform(xf)
    return m.GetBoundingBox(True)


def main():
    doc = Rhino.RhinoDoc.ActiveDoc
    log("문서 {} 단위={}".format(doc.Name, doc.ModelUnitSystem))
    log("원본 {}".format(SRC))
    if not os.path.isdir(SRC):
        log("원본 폴더가 없다 — 웹 저장소 경로를 확인할 것")
        return
    log("")

    parts = []
    for fname, part in PARTS:
        path = os.path.join(SRC, fname)
        if not os.path.isfile(path):
            log("{:<10} 파일 없음".format(part))
            continue
        ok, objs = import_file(doc, path)
        _touched.extend(objs)
        m = as_mesh(objs)
        if m is None:
            log("{:<10} RunScript={} 객체 {}개 — 메시가 없다".format(
                part, ok, len(objs)))
            continue
        log("{:<10} 객체 {:>4}개  면 {:>7}".format(part, len(objs), m.Faces.Count))
        parts.append((part, m))

    if not parts:
        log("")
        log("아무것도 못 읽었다 — Rhino 가 glTF 를 임포트하지 못했다")
        return

    # ── 단위 ─────────────────────────────────────────────
    # Z 는 축 함정 때문에 못 믿는다. 최대 절대좌표로 본다.
    span = 0.0
    for _, m in parts:
        bb = m.GetBoundingBox(True)
        for p in (bb.Min, bb.Max):
            span = max(span, abs(p.X), abs(p.Y), abs(p.Z))
    log("")
    log("최대 절대좌표 = {:.3f}".format(span))
    if span < 10.0:
        log("  -> meter 로 들어왔다. x1000")
        xf = rg.Transform.Scale(rg.Point3d.Origin, 1000.0)
        for _, m in parts:
            m.Transform(xf)
    else:
        log("  -> 이미 mm (임포터가 x1000 을 걸었다)")

    # ── 축 보정 ──────────────────────────────────────────
    log("")
    name, xf = pick_axis_fix(parts)
    if name != "그대로":
        for _, m in parts:
            m.Transform(xf)

    # ── 대조 ─────────────────────────────────────────────
    log("")
    log("KINEMATICS.md 의 world z 범위와 대조 (mm)")
    worst = 0.0
    for part, m in parts:
        bb = m.GetBoundingBox(True)
        exp = EXPECT_Z_MM.get(part)
        if exp is None:
            log("  {:<10} z[{:>7.1f},{:>7.1f}]   (기대값 없음)".format(
                part, bb.Min.Z, bb.Max.Z))
            continue
        d0 = abs(bb.Min.Z - exp[0])
        d1 = abs(bb.Max.Z - exp[1])
        worst = max(worst, d0, d1)
        log("  {:<10} z[{:>7.1f},{:>7.1f}]   기대 [{:>5},{:>5}]   차이 {:>5.0f} / {:>5.0f}".format(
            part, bb.Min.Z, bb.Max.Z, exp[0], exp[1], d0, d1))
    log("  최대 차이 {:.0f} mm — 원본 문서가 '근사'라고 적어 둔 범위".format(worst))

    # ── 표시용으로 면수 줄이기 ───────────────────────────
    total = sum(m.Faces.Count for _, m in parts)
    log("")
    log("전체 면 {}개".format(total))
    if TARGET_FACES_TOTAL and total > TARGET_FACES_TOTAL:
        ratio = float(TARGET_FACES_TOTAL) / total
        log("  목표 {} -> 파트별 {:.1%}".format(TARGET_FACES_TOTAL, ratio))
        for part, m in parts:
            n0 = m.Faces.Count
            try:
                m.Reduce(max(200, int(n0 * ratio)), True, 10, False)
            except Exception as ex:
                log("  {:<10} Reduce 실패: {}".format(part, ex))
                continue
            log("  {:<10} {:>7} -> {:>6}".format(part, n0, m.Faces.Count))

    # ── 저장 ─────────────────────────────────────────────
    f = Rhino.FileIO.File3dm()
    f.Settings.ModelUnitSystem = Rhino.UnitSystem.Millimeters
    for part, m in parts:
        # File3dmLayerTable 은 IList 라 Add() 가 인덱스를 돌려주지 않는다(void).
        # 넣기 전 Count 가 그 레이어의 인덱스다.
        idx = f.AllLayers.Count
        layer = Rhino.DocObjects.Layer()
        layer.Name = part
        layer.Index = idx
        f.AllLayers.Add(layer)
        att = Rhino.DocObjects.ObjectAttributes()
        att.Name = part
        att.LayerIndex = idx
        f.Objects.AddMesh(m, att)

    ok = f.Write(OUT_3DM, 7)
    size = os.path.getsize(OUT_3DM) if os.path.exists(OUT_3DM) else 0
    log("")
    log("저장 {}: {} bytes, 파트 {}개".format(
        "성공" if ok else "실패", size, len(parts)))
    log(OUT_3DM)


try:
    main()
except Exception:
    import traceback
    log("")
    log(traceback.format_exc())
finally:
    # **예외가 나도 문서는 원복한다.** 처음 판에서 이 정리가 try 안에 있어
    # 메시 4,592개가 문서에 남았다.
    doc = Rhino.RhinoDoc.ActiveDoc
    n = 0
    for o in _touched:
        try:
            if doc.Objects.Delete(o, True):
                n += 1
        except Exception:
            pass
    log("문서 정리: 임포트 객체 {}/{}개 삭제".format(n, len(_touched)))
    try:
        doc.Views.Redraw()
    except Exception:
        pass
    with open(LOG, "w", encoding="utf-8") as fh:
        fh.write("\n".join(_lines))

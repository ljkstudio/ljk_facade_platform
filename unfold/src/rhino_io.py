# -*- coding: utf-8 -*-
"""Rhino 경계면 — **이 파일만 Rhino 를 import 한다.**

코어가 Rhino 를 모르게 유지하는 대가로, Rhino 쪽 함정은 전부 여기 모인다.

  · Mesh.CreateFromBrep 은 None 이나 빈 배열을 돌려줄 수 있다 → 반드시 검사
  · 트림된 Brep 은 조각으로 나오므로 Append 로 합치고 CombineIdentical 로 꿰맨다
  · 사각형 면이 섞여 나오므로 ConvertQuadsToTriangles 를 반드시 부른다
    (코어는 삼각형만 받는다)
"""

import math

import Rhino.Geometry as rg
import System.Drawing as sd

MIN_EDGE_RATIO = 0.25         # 최소 변 길이 = edge_mm × 이것
WELD_DEG = 180.0               # 정점 병합 각도
MESH_DENSITY = 0.0             # MeshingParameters 밀도 — 변 길이로만 제어한다
FULL_COLOR_STRAIN = 0.20       # σ 가 1 에서 이만큼 벗어나면 색이 만색이 된다
COLOR_MAX = 255                # 채널 최대
COLOR_SWING = 200              # 만색에서 다른 두 채널이 내려가는 폭


def mesh_from_brep(brep, edge_mm):
    # type: (object, float) -> tuple
    """Brep 을 삼각망으로. (verts, faces, notes) 를 돌려준다."""
    notes = []
    if brep is None:
        return [], [], ["Brep 이 None 이다"]

    mp = rg.MeshingParameters(MESH_DENSITY)
    mp.MaximumEdgeLength = float(edge_mm)
    mp.MinimumEdgeLength = float(edge_mm) * MIN_EDGE_RATIO
    mp.SimplePlanes = False
    mp.JaggedSeams = False

    pieces = rg.Mesh.CreateFromBrep(brep, mp)
    if pieces is None or len(pieces) == 0:
        return [], [], ["Mesh.CreateFromBrep 이 아무것도 못 만들었다 — "
                        "곡면이 유효한지, edge_mm 이 너무 크지 않은지 확인해야 한다"]

    mesh = rg.Mesh()
    for piece in pieces:
        if piece is not None:
            mesh.Append(piece)
    if len(pieces) > 1:
        notes.append("Brep 이 면 %d개로 나뉘어 메쉬화됐다 — 합쳐서 꿰맸다" % len(pieces))

    mesh.Vertices.CombineIdentical(True, True)
    mesh.Weld(math.radians(WELD_DEG))
    quads = mesh.Faces.QuadCount
    if quads:
        mesh.Faces.ConvertQuadsToTriangles()
        notes.append("사각형 면 %d개를 삼각형으로 쪼갰다" % quads)
    mesh.Faces.CullDegenerateFaces()
    mesh.Compact()

    verts = [(v.X, v.Y, v.Z) for v in mesh.Vertices.ToPoint3dArray()]
    faces = []
    for f in mesh.Faces:
        faces.append((f.A, f.B, f.C))
    notes.append("메쉬 정점 %d개, 삼각형 %d개 (목표 변 길이 %.1f mm)"
                 % (len(verts), len(faces), edge_mm))
    return verts, faces, notes


def to_mesh(uv, faces):
    # type: (list, list) -> object
    """평면 결과를 z=0 메쉬로."""
    mesh = rg.Mesh()
    for (x, y) in uv:
        mesh.Vertices.Add(float(x), float(y), 0.0)
    for (a, b, c) in faces:
        mesh.Faces.AddFace(a, b, c)
    mesh.Normals.ComputeNormals()
    mesh.Compact()
    return mesh


def _sigma_color(s):
    """σ<1 (성형에서 인장) 은 파랑, 1 은 흰색, σ>1 (주름 위험) 은 빨강."""
    t = max(-1.0, min(1.0, (s - 1.0) / FULL_COLOR_STRAIN))
    if t >= 0.0:
        v = int(COLOR_MAX - COLOR_SWING * t)
        return sd.Color.FromArgb(COLOR_MAX, v, v)
    v = int(COLOR_MAX - COLOR_SWING * (-t))
    return sd.Color.FromArgb(v, v, COLOR_MAX)


def to_strain_mesh(uv, faces, sigmas):
    # type: (list, list, list) -> object
    """요소별 σ 를 정점으로 평균 내 색칠한다."""
    mesh = to_mesh(uv, faces)
    acc = [0.0] * len(uv)
    cnt = [0] * len(uv)
    for t, (s1, _s2) in enumerate(sigmas):
        for v in faces[t]:
            acc[v] += s1
            cnt[v] += 1
    mesh.VertexColors.Clear()
    for i in range(len(uv)):
        mesh.VertexColors.Add(_sigma_color(acc[i] / cnt[i] if cnt[i] else 1.0))
    return mesh


def to_curve(poly):
    # type: (list) -> object
    """평면 폴리라인을 닫힌 곡선으로."""
    if not poly:
        return None
    pts = [rg.Point3d(float(x), float(y), 0.0) for (x, y) in poly]
    pts.append(pts[0])
    return rg.PolylineCurve(pts)

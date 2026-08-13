# -*- coding: utf-8 -*-
"""삼각형 하나의 기하 — 국소 등거리 좌표계, 면적, cotangent 가중.

**국소 좌표계가 이 프로젝트의 기준자다.** 3D 삼각형을 길이를 하나도 바꾸지 않고
평면에 눕힌 것이고, 전개 결과를 여기에 견주어 변형률을 잰다. 길이 보존이
깨지면 그 뒤의 모든 수치가 조용히 틀린다.

    p0 → (0, 0)
    p1 → (|p1-p0|, 0)
    p2 → (투영 길이, 남은 높이)     ← 항상 y > 0
"""

import math

MIN_AREA = 1e-12       # mm^2. 이보다 작으면 퇴화로 본다


class DegenerateTriangle(Exception):
    """면적이 0 에 가까운 삼각형. 역행렬이 폭발하므로 앞에서 끊는다."""


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def local_frame(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> tuple
    """3D 삼각형을 길이를 보존한 채 평면에 놓는다."""
    e1 = _sub(p1, p0)
    e2 = _sub(p2, p0)
    a = _norm(e1)
    if a <= 0.0:
        raise DegenerateTriangle("첫 변의 길이가 0 이다 — 퇴화 삼각형")
    ux = (e1[0] / a, e1[1] / a, e1[2] / a)
    b = _dot(e2, ux)
    h2 = _dot(e2, e2) - b * b
    c = math.sqrt(h2) if h2 > 0.0 else 0.0
    return ((0.0, 0.0), (a, 0.0), (b, c))


def area(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> float
    return 0.5 * _norm(_cross(_sub(p1, p0), _sub(p2, p0)))


def cotangents(p0, p1, p2):
    # type: (tuple, tuple, tuple) -> tuple
    """정점 i 에서의 각의 cotangent. cot θ = (u·v) / |u×v|, |u×v| = 2·면적."""
    two_a = 2.0 * area(p0, p1, p2)
    if two_a <= 0.0:
        raise DegenerateTriangle("면적이 0 이다 — 퇴화 삼각형")
    p = (p0, p1, p2)
    out = []
    for i in range(3):
        u = _sub(p[(i + 1) % 3], p[i])
        v = _sub(p[(i + 2) % 3], p[i])
        out.append(_dot(u, v) / two_a)
    return tuple(out)


class ElementData(object):
    """요소 하나의 사전계산 결과. 반복 중에 바뀌지 않는다."""

    __slots__ = ("local", "area", "cot", "inv")

    def __init__(self, local, area_, cot, inv):
        self.local = local
        self.area = area_
        self.cot = cot
        self.inv = inv


def prepare(verts, faces):
    # type: (list, list) -> list
    """모든 면의 국소 좌표·면적·cotangent·역행렬을 한 번에 계산한다."""
    out = []
    for fi, (i, j, k) in enumerate(faces):
        p0, p1, p2 = verts[i], verts[j], verts[k]
        a = area(p0, p1, p2)
        if a < MIN_AREA:
            raise DegenerateTriangle("면 %d: 면적이 %g 로 0 에 가깝다 — 퇴화 삼각형" % (fi, a))
        loc = local_frame(p0, p1, p2)
        # 국소 엣지행렬 D = [[x1-x0, x2-x0], [y1-y0, y2-y0]] = [[a, b], [0, c]]
        m00 = loc[1][0] - loc[0][0]
        m01 = loc[2][0] - loc[0][0]
        m10 = loc[1][1] - loc[0][1]
        m11 = loc[2][1] - loc[0][1]
        det = m00 * m11 - m01 * m10
        inv = (m11 / det, -m01 / det, -m10 / det, m00 / det)
        out.append(ElementData(loc, a, cotangents(p0, p1, p2), inv))
    return out

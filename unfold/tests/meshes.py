# -*- coding: utf-8 -*-
"""이론해를 아는 시험용 메쉬들. 전부 원판 위상(경계 루프 1개)이다.

전개 결과가 맞는지는 눈으로 못 본다. 그래서 **답을 아는 곡면**으로만 검사한다.

    plane_grid      전개 = 항등
    cylinder_patch  전개 가능 → 가로 R·beta, 세로 h 의 직사각형
    cone_patch      전개 가능 → 반경 l0..l1, 각 2π·sin(alpha) 의 부채꼴 띠
    sphere_cap      전개 불가 → 외곽 반경이 2R·sin(θ/2) 와 R·θ 사이
"""

import math


def _grid_faces(nx, ny):
    """(nx × ny) 격자를 삼각형으로. 방향이 전부 같도록 고정한다."""
    faces = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a = j * nx + i
            b = j * nx + (i + 1)
            c = (j + 1) * nx + (i + 1)
            d = (j + 1) * nx + i
            faces.append((a, b, c))
            faces.append((a, c, d))
    return faces


def plane_grid(nx=5, ny=4, w=100.0, h=80.0):
    verts = [(w * i / (nx - 1.0), h * j / (ny - 1.0), 0.0)
             for j in range(ny) for i in range(nx)]
    return verts, _grid_faces(nx, ny)


def cylinder_patch(R=500.0, beta=0.8, h=300.0, nu=9, nv=5):
    """x-z 평면 안에서 휜 원기둥 조각. 세로(y)는 곧다."""
    verts = []
    for j in range(nv):
        y = h * j / (nv - 1.0)
        for i in range(nu):
            u = beta * i / (nu - 1.0)
            verts.append((R * math.sin(u), y, R * (1.0 - math.cos(u))))
    return verts, _grid_faces(nu, nv)


def cone_patch(alpha=0.4, l0=200.0, l1=600.0, beta=0.9, nu=9, nv=5):
    """꼭짓점이 원점, 축이 +z 인 원뿔의 조각. 모선 길이 l0..l1, 감싼 각 beta."""
    verts = []
    sa, ca = math.sin(alpha), math.cos(alpha)
    for j in range(nv):
        l = l0 + (l1 - l0) * j / (nv - 1.0)
        for i in range(nu):
            psi = beta * i / (nu - 1.0)
            verts.append((l * sa * math.cos(psi), l * sa * math.sin(psi), l * ca))
    return verts, _grid_faces(nu, nv)


def sphere_cap(R=500.0, theta=0.6, nr=6, nt=16):
    """극점 하나 + 고리 nr 겹. 원판 위상이고 축대칭이다."""
    verts = [(0.0, 0.0, R)]

    def idx(r, t):
        return 1 + (r - 1) * nt + (t % nt)

    for r in range(1, nr + 1):
        phi = theta * r / float(nr)
        for t in range(nt):
            psi = 2.0 * math.pi * t / nt
            verts.append((R * math.sin(phi) * math.cos(psi),
                          R * math.sin(phi) * math.sin(psi),
                          R * math.cos(phi)))
    faces = []
    for t in range(nt):
        faces.append((0, idx(1, t), idx(1, t + 1)))
    for r in range(1, nr):
        for t in range(nt):
            a, b = idx(r, t), idx(r + 1, t)
            c, d = idx(r + 1, t + 1), idx(r, t + 1)
            faces.append((a, b, c))
            faces.append((a, c, d))
    return verts, faces

# -*- coding: utf-8 -*-
"""ARAP 반복에 넣을 초기 평면 배치.

ARAP 은 접힌 초기값에서 못 빠져나온다. 그래서 두 단계로 간다.

  1. 최적평면 투영 — 얕은 외장 패널은 여기서 끝난다(뒤집힘 0)
  2. 뒤집힘이 있으면 Tutte 매립 — 원판 위상 + 볼록 경계면 **단사가 보장**된다.
     심하게 왜곡되지만 ARAP 이 회복시킨다.

**LSCM 을 쓰지 않는 이유**: 별도의 복소 최소자승 조립이 필요한데, Tutte 는
이미 있는 라플라시안 솔버를 그대로 쓴다. 등각성은 어차피 반복이 지운다.
"""

import math

import solver as sv

FLIP_TOL = 1e-12          # 부호면적이 이보다 작으면 뒤집힘/퇴화로 센다


def _tri_normal(p0, p1, p2):
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _frame(n):
    """법선 n 에 직교하는 정규직교 기저 (u, v) 를 만든다."""
    ax = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    ux = (ax[1] * n[2] - ax[2] * n[1], ax[2] * n[0] - ax[0] * n[2],
          ax[0] * n[1] - ax[1] * n[0])
    ul = math.sqrt(sum(c * c for c in ux))
    u = (ux[0] / ul, ux[1] / ul, ux[2] / ul)
    v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2],
         n[0] * u[1] - n[1] * u[0])
    return u, v


def project(verts, faces):
    # type: (list, list) -> list
    """면적 가중 평균 법선으로 정한 최적평면에 정사영한다."""
    nx = ny = nz = 0.0
    for (i, j, k) in faces:
        cx, cy, cz = _tri_normal(verts[i], verts[j], verts[k])
        nx += cx; ny += cy; nz += cz          # 외적 길이가 곧 2·면적이라 가중이 붙는다
    ln = math.sqrt(nx * nx + ny * ny + nz * nz)
    if ln <= 0.0:
        raise ValueError("면적 가중 법선이 0 이다 — 앞뒤가 상쇄됐거나 면적이 없다")
    n = (nx / ln, ny / ln, nz / ln)
    u, v = _frame(n)
    return [(p[0] * u[0] + p[1] * u[1] + p[2] * u[2],
             p[0] * v[0] + p[1] * v[1] + p[2] * v[2]) for p in verts]


def signed_area(uv, face):
    # type: (list, tuple) -> float
    a, b, c = uv[face[0]], uv[face[1]], uv[face[2]]
    return 0.5 * ((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]))


def count_flips(uv, faces):
    # type: (list, list) -> int
    """**소수파 방향의 면 수**를 돌려준다.

    배치 전체가 거울상으로 나오는 일이 있다(_frame 이 법선에 직교하는 기저를
    어느 쪽으로 잡느냐에 달렸다). 그걸 "전부 뒤집힘"으로 세면 멀쩡한 배치를
    버리게 되므로, 과반이 음수면 거울상으로 보고 다시 센다.

    부호면적은 거울에 대해 **정확히** 부호가 뒤집히므로, 결과적으로 이 함수는
    `min(음수 면 수, 양수 면 수)` 다. 그래서 과반이 접힌 메쉬에서는 접힌 수를
    과소보고한다 — 실측 [2026-08-14, sphere_cap R=300 nr=6 nt=16]:

        theta 1.9 → 음수 32/176, 반환 32
        theta 2.5 → 음수 64/176, 반환 64
        theta 3.0 → 음수 96/176, 반환 **80**

    **그래도 이 함수가 이끄는 판단은 바뀌지 않는다.** 쓰이는 곳은 layout() 의
    투영↔Tutte 선택과 경고 문구뿐이고 둘 다 0 이냐 아니냐만 본다. 그리고 0 이
    되는 경우는 **모든** 면이 한 방향일 때뿐이다 — 그건 접힘이 아니라 거울상이고,
    정확히 이 분기가 노리는 경우다. 80 이든 96 이든 행동은 같다.
    """
    neg = sum(1 for f in faces if signed_area(uv, f) <= FLIP_TOL)
    if neg > len(faces) - neg:
        flipped = [(x, -y) for (x, y) in uv]
        return sum(1 for f in faces if signed_area(flipped, f) <= FLIP_TOL)
    return neg


def tutte(verts, topo):
    # type: (list, object) -> list
    """경계를 원에 붙이고 내부를 균등 가중 라플라시안으로 푼다."""
    loop = topo.boundary_loops[0]
    lens = []
    for a in range(len(loop)):
        p, q = verts[loop[a]], verts[loop[(a + 1) % len(loop)]]
        lens.append(math.sqrt(sum((p[t] - q[t]) ** 2 for t in range(3))))
    total = sum(lens)
    if total <= 0.0:
        raise ValueError("경계 길이가 0 이다")

    radius = total / (2.0 * math.pi)      # 둘레를 보존하는 원
    fixed = {}
    acc = 0.0
    for a, vidx in enumerate(loop):
        ang = 2.0 * math.pi * acc / total
        fixed[vidx] = (radius * math.cos(ang), radius * math.sin(ang))
        acc += lens[a]

    n = len(verts)
    lap = sv.Sparse(n)
    seen = set()
    for (i, j, k) in topo.faces:
        for a, b in ((i, j), (j, k), (k, i)):
            e = (min(a, b), max(a, b))
            if e in seen:
                continue
            seen.add(e)
            lap.add(a, a, 1.0); lap.add(b, b, 1.0)
            lap.add(a, b, -1.0); lap.add(b, a, -1.0)

    out = []
    for axis in (0, 1):
        mat = lap.copy()          # 축마다 다른 값으로 고정하므로 원본을 보존한다
        rhs = [0.0] * n
        mat.pin_many(dict((v, p[axis]) for v, p in fixed.items()), rhs)
        # cg 의 반복 수를 버린다 — **여기서는** 실을 신호가 아니다.
        # 균등 가중 라플라시안은 가중이 전부 +1 이라 경계를 고정하면 정부호가
        # 보장되고(음수 cotangent 가 없다), 상한도 넉넉하다. 그래도 실패했다면
        # 배치가 접혀 layout() 의 flips 로 드러난다.
        # ARAP 쪽(flatten._global_step)은 사정이 다르다 — 둔각 삼각형이 많으면
        # cotangent 가 음수가 되어 정부호를 잃으므로 거기서는 반드시 받는다.
        sol, _iters = sv.cg(mat.matvec, rhs, tol=1e-12, maxiter=20 * n + 200)
        out.append(sv.tolist(sol))
    return list(zip(out[0], out[1]))


def layout(verts, faces, topo):
    # type: (list, list, object) -> tuple
    """초기 배치를 정한다. (uv, method, flips) 를 돌려준다."""
    uv = project(verts, faces)
    flips = count_flips(uv, faces)
    if flips == 0:
        return uv, "projection", 0
    uv = tutte(verts, topo)
    return uv, "tutte", count_flips(uv, faces)

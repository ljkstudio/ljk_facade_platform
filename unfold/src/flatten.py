# -*- coding: utf-8 -*-
"""ARAP 평탄화 — local-global 반복.

    사전계산 : 요소별 국소 등거리 좌표 + cotangent (3D 원본에서 한 번)
    반복 {
      local  : 요소마다 야코비안 → 최근접 회전, 그리고 주름 가중
      global : 가중 cotangent 라플라시안 L·x = b 를 x·y 축에 대해 각각
    }

**주름 벌점을 IRLS 로 넣기 때문에 L 이 매 반복 바뀐다.** 그래서 사전 분해를
쓰지 않고 CG + warm start 로 간다(solver.py 참고).

**게이지 고정**: ARAP 해는 평행이동·회전만큼 자유도가 남는다. 정점 0 을 원점에
고정해 풀고, 마지막에 강체 정렬한다. 이게 없으면 같은 입력이 매번 다른 방향으로
나와 회귀 픽스처가 성립하지 않는다.

**축대칭 형상에서는 정렬 방향이 여전히 자유롭다**(공분산이 등방이라 주축이 없다).
그래서 테스트는 좌표가 아니라 회전 불변량으로 비교한다.
"""

import math

import element as el
import energy as en
import initial as ini
import solver as sv

DEFAULT_ITERS = 30
ENERGY_TOL = 1e-6         # 상대 에너지 변화가 이보다 작으면 수렴으로 본다
ENERGY_FLOOR = 1e-30      # 상대 판정의 분모 하한 — 에너지가 0 인 평면에서 0 나눗셈을 막는다
# CG 잔차 허용치 (rhs 크기에 상대적).
#
# **바깥 루프가 필요로 하는 것보다 더 정확하게 풀 이유가 없다.** 바깥은 에너지
# 상대변화 1e-6 에서 멈추는데 예전 값(1e-11)은 안쪽 선형계를 그보다 다섯 자리
# 더 정확하게 풀고 있었다. 실측 2026-08-14 (돔 2049정점, Rhino 8 py39, numpy 없음):
#
#     1e-11 : 5.66 s  CG 4194회   σmax 1.070200  (기준)
#     1e-09 : 4.67 s  CG 3530회   Δσmax 3.3e-11
#     1e-07 : 2.74 s  CG 1978회   Δσmax 6.6e-08   ← 채택
#     1e-05 : 1.19 s  CG  752회   Δσmax 2.1e-06   골든 픽스처 1e-6 을 넘는다
#
# 1e-7 을 고른 근거는 "빠르다"가 아니라 **결과가 안 움직인다**는 것이다.
# 회귀 방어선(golden fixture 상대오차 1e-6)보다 한 자리 아래다.
CG_REL = 1e-9
CG_TOL_FLOOR = 1.0        # rhs 가 0 에 가까울 때 허용치까지 0 이 되는 것을 막는다
CG_CAP_PER_VERTEX = 20    # CG 반복 상한 = 이것 × 정점 수 + CG_CAP_BASE
CG_CAP_BASE = 500

# 삼각형의 (엣지 국소인덱스 쌍, 마주보는 정점의 국소인덱스)
_EDGES = (((0, 1), 2), ((1, 2), 0), ((2, 0), 1))


class FlattenResult(object):
    __slots__ = ("uv", "faces", "elements", "sigmas", "energy_history",
                 "iterations", "converged", "method", "flips", "notes")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def align(uv, faces):
    # type: (list, list) -> list
    """결정론적 강체 정렬 — 무게중심을 원점에, 주축을 +X 로, 앞면을 위로."""
    n = len(uv)
    cx = sum(p[0] for p in uv) / n
    cy = sum(p[1] for p in uv) / n
    pts = [(p[0] - cx, p[1] - cy) for p in uv]

    if sum(ini.signed_area(pts, f) for f in faces) < 0.0:
        pts = [(x, -y) for (x, y) in pts]        # 통째로 뒤집혔으면 되돌린다

    sxx = sum(x * x for x, _y in pts)
    syy = sum(y * y for _x, y in pts)
    sxy = sum(x * y for x, y in pts)
    ang = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    ca, sa = math.cos(-ang), math.sin(-ang)
    pts = [(ca * x - sa * y, sa * x + ca * y) for (x, y) in pts]

    # 180도 모호성 — 3차 모멘트의 부호로 고정한다
    m3x = sum(x ** 3 for x, _y in pts)
    if m3x < 0.0:
        pts = [(-x, -y) for (x, y) in pts]
    return pts


def _local_step(elements, faces, uv, penalty):
    """요소별 최근접 회전·주름 가중·에너지를 구한다."""
    rots, weights, sigmas = [], [], []
    total = 0.0
    for t, ed in enumerate(elements):
        i, j, k = faces[t]
        jac = en.jacobian(ed, uv[i], uv[j], uv[k])
        s1, s2 = en.singular_values(jac)
        rots.append(en.closest_rotation(jac))
        weights.append(en.wrinkle_weight(s1, penalty))
        sigmas.append((s1, s2))
        total += en.element_energy(ed.area, s1, s2)
    return rots, weights, sigmas, total


def _global_step(n, elements, faces, rots, weights, prev):
    """가중 cotangent 라플라시안을 조립해 x·y 를 푼다."""
    mat = sv.Sparse(n)
    bx = [0.0] * n
    by = [0.0] * n
    for t, ed in enumerate(elements):
        f = faces[t]
        rot = rots[t]
        w_t = weights[t]
        for (p, q), opp in _EDGES:
            w = w_t * ed.cot[opp]
            i, j = f[p], f[q]
            mat.add(i, i, w); mat.add(j, j, w)
            mat.add(i, j, -w); mat.add(j, i, -w)
            dx = ed.local[p][0] - ed.local[q][0]
            dy = ed.local[p][1] - ed.local[q][1]
            rx = rot[0] * dx + rot[1] * dy
            ry = rot[2] * dx + rot[3] * dy
            bx[i] += w * rx; bx[j] -= w * rx
            by[i] += w * ry; by[j] -= w * ry

    mat.pin(0)
    bx[0] = 0.0
    by[0] = 0.0

    out = []
    stalled = 0
    cap = CG_CAP_PER_VERTEX * n + CG_CAP_BASE
    # 야코비 전처리. cotangent 라플라시안은 삼각형 모양과 정점 차수에 따라
    # 대각이 자릿수 단위로 달라 조건수가 커진다 — 대각으로 나누는 것만으로
    # 반복이 눈에 띄게 준다. **정확도는 팔지 않는다** (허용치는 그대로다).
    diag = mat.diagonal()
    for b, prev_axis in ((bx, [p[0] for p in prev]), (by, [p[1] for p in prev])):
        scale = math.sqrt(sum(v * v for v in b))
        tol = CG_REL * (scale + CG_TOL_FLOOR)
        warm = list(prev_axis)
        warm[0] = 0.0
        sol, used = sv.cg(mat.matvec, b, x0=warm, tol=tol, maxiter=cap, precond=diag)
        if used >= cap:
            # 수렴 실패이거나 준정부호 붕괴다. **버리면 안 되는 신호다** —
            # 둔각 삼각형이 많으면 cotangent 가중이 음수가 되어 실제로 일어나고,
            # 그때 이 축의 좌표는 아무 의미가 없다.
            stalled += 1
        out.append(sv.tolist(sol))
    return list(zip(out[0], out[1])), stalled


def run(verts, faces, topo, props, iters=DEFAULT_ITERS, tol=ENERGY_TOL):
    # type: (list, list, object, object, int, float) -> FlattenResult
    """평탄화 본체."""
    notes = []
    elements = el.prepare(verts, faces)
    uv, method, flips0 = ini.layout(verts, faces, topo)
    if method == "tutte":
        notes.append("투영이 접혀 Tutte 매립으로 초기화했다 (깊은 곡면)")
    if flips0:
        notes.append("초기 배치에 뒤집힌 요소가 %d개 남았다" % flips0)

    penalty = props.wrinkle_penalty
    history = []
    sigmas = []
    converged = False
    used = 0
    stalls = 0

    for step in range(1, iters + 1):
        rots, weights, sigmas, e_now = _local_step(elements, faces, uv, penalty)
        history.append(e_now)
        used = step
        if len(history) >= 2:
            prev = history[-2]
            if prev - e_now <= tol * max(prev, ENERGY_FLOOR):
                converged = True
                break
        uv, stalled = _global_step(len(verts), elements, faces, rots, weights, uv)
        stalls += stalled

    # 마지막 배치에 대한 σ 를 다시 잰다 — 반복 중 값은 직전 배치의 것이다
    _r, _w, sigmas, e_final = _local_step(elements, faces, uv, penalty)
    history.append(e_final)

    uv = align(uv, faces)
    flips = ini.count_flips(uv, faces)
    if flips:
        notes.append("결과에 뒤집힌 요소가 %d개 있다 — 반복을 늘리거나 메쉬를 고르게 해야 한다" % flips)
    if not converged:
        notes.append("반복 상한 %d 에서 멈췄다 — 수렴하지 않았다" % iters)
    if stalls:
        notes.append("선형해가 %d번 실패했다 — 이 결과의 좌표를 믿으면 안 된다. "
                     "둔각 삼각형이 많아 cotangent 가중이 음수가 되면 강성행렬이 "
                     "정부호를 잃는다. 메쉬를 고르게 하거나 요소 크기를 바꿔야 한다" % stalls)

    return FlattenResult(uv=uv, faces=faces, elements=elements, sigmas=sigmas,
                         energy_history=history, iterations=used,
                         converged=converged, method=method, flips=flips,
                         notes=notes)

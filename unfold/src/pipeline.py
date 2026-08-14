# -*- coding: utf-8 -*-
"""공개 진입점 — 위상 검사부터 재단선까지 한 번에.

**판단은 전부 여기 아래에서 끝난다.** GH 어댑터는 이 결과를 화면에 옮기기만
한다. 어댑터가 판단을 시작하면 같은 판단이 두 곳에 생기고, 둘이 어긋나는 날
화면과 숫자가 다른 말을 하게 된다(J-006 TRAP-03 과 같은 종류의 사고다).
"""

import blank as bk
import element as el
import flatten as fl
import material as mt
import metrics as mx
import report as rp
import solver as sv
import topology as tp

DEFAULT_ALLOW_MM = 15.0
DEFAULT_FIT_TOL = 1.0
DEFAULT_ITERS = 30

# ── 얼마나 큰 메쉬까지 받을 것인가 ────────────────────────────────────────
#
# GH 스크립트 컴포넌트는 Rhino UI 스레드에서 돈다. 계산 시간이 곧 **화면이
# 멈춰 있는 시간**이다. 그래서 상한은 정점 수가 아니라 시간 예산으로 정한다 —
# 사용자가 겪는 것은 "정점 5889개"가 아니라 "6초 동안 멈춘 Rhino"다.
#
# 실측 2026-08-14 (panel_dome, Rhino 8.33 py39, 이 PC):
#
#   numpy 있음 : 2049정점 0.50 s · 5889정점 1.44 s · 16385정점 6.14 s  → ≈0.37 ms/정점
#   numpy 없음 : 2049정점 10.28 s                                      → ≈5.0  ms/정점
#
# **한 상한을 두 백엔드에 같이 쓰면 한쪽은 과보호, 다른 쪽은 무방비가 된다.**
# 예전 값 5000 은 순수 파이썬 시절에 정해진 것인데, numpy 에서는 1.2초짜리
# 메쉬를 막고 순수 파이썬에서는 25초짜리를 통과시킨다.
FREEZE_BUDGET_S = 3.0
MS_PER_VERT_NUMPY = 0.37
MS_PER_VERT_PURE = 5.0


def _ms_per_vert():
    # type: () -> float
    return MS_PER_VERT_NUMPY if sv.fast_backend() else MS_PER_VERT_PURE


def estimate_seconds(n_verts):
    # type: (int) -> float
    """이 환경에서 이 크기의 메쉬가 몇 초쯤 걸릴지. 추정이지 보장이 아니다."""
    return n_verts * _ms_per_vert() / 1000.0


def default_max_verts():
    # type: () -> int
    """시간 예산에서 거꾸로 계산한 정점 상한."""
    return int(FREEZE_BUDGET_S * 1000.0 / _ms_per_vert())


class Outcome(object):
    __slots__ = ("ok", "uv", "faces", "curve", "sigmas", "warn", "info",
                 "metrics", "flatten", "blank")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _fail(warn):
    return Outcome(ok=False, uv=[], faces=[], curve=[], sigmas=[], warn=warn,
                   info="\n".join(warn), metrics=None, flatten=None, blank=None)


def run(verts, faces, props=None, allow_mm=DEFAULT_ALLOW_MM, fit_tol=DEFAULT_FIT_TOL,
        iters=DEFAULT_ITERS, max_verts=None):
    # type: (list, list, object, float, float, int, int) -> Outcome
    """전개 한 판.

    `max_verts` 를 주지 않으면 시간 예산에서 계산한 값을 쓴다(`default_max_verts`).
    명시하면 그 값이 이긴다 — 오래 걸려도 좋으니 촘촘하게 보고 싶을 때가 있다.
    """
    props = props or mt.DEFAULT
    if not props.ok:
        return _fail(["[경고] 물성: " + p for p in props.problems])

    cap = default_max_verts() if max_verts is None else max_verts
    if len(verts) > cap:
        return _fail([
            "[경고] 정점이 %d개다 — 이 환경에서 약 %.0f초 걸린다 (상한 %d개, 예산 %.0f초). "
            "계산하는 동안 Rhino 는 멈춰 있다. 요소 크기(edge_mm)를 키우거나, "
            "오래 걸려도 좋으면 max_verts 를 올려라.%s"
            % (len(verts), estimate_seconds(len(verts)), cap, FREEZE_BUDGET_S,
               "" if sv.fast_backend() else
               " **numpy 를 못 쓰고 있다** — 스크립트 첫 줄의 `# r: numpy` 가 빠지면 "
               "같은 메쉬가 20배 느리다")])

    topo = tp.build(len(verts), faces)
    if not topo.ok:
        return _fail(["[경고] 위상: " + p for p in topo.problems])

    try:
        res = fl.run(verts, faces, topo, props, iters=iters)
    except el.DegenerateTriangle as ex:
        return _fail(["[경고] 메쉬: %s — 요소 크기를 바꾸거나 곡면을 정리해야 한다" % ex])

    m = mx.evaluate(res, props)
    bl = bk.build(res.uv, topo, allow_mm=allow_mm, fit_tol=fit_tol)
    info, warn = rp.summarize(res, m, bl, props)
    for note in props.notes:
        warn.append("[참고] 물성: " + note)

    return Outcome(ok=True, uv=res.uv, faces=faces, curve=bl.curve, sigmas=res.sigmas,
                   warn=warn, info=info, metrics=m, flatten=res, blank=bl)

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
import topology as tp

DEFAULT_ALLOW_MM = 15.0
DEFAULT_FIT_TOL = 1.0
DEFAULT_ITERS = 30
DEFAULT_MAX_VERTS = 5000


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
        iters=DEFAULT_ITERS, max_verts=DEFAULT_MAX_VERTS):
    # type: (list, list, object, float, float, int, int) -> Outcome
    """전개 한 판."""
    props = props or mt.DEFAULT
    if not props.ok:
        return _fail(["[경고] 물성: " + p for p in props.problems])

    if len(verts) > max_verts:
        return _fail(["[경고] 정점이 %d개로 상한 %d개를 넘었다 — 요소 크기(edge_mm)를 키워야 한다. "
                      "그대로 돌리면 Rhino 가 오래 얼어붙는다" % (len(verts), max_verts)])

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

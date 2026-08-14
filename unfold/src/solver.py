# -*- coding: utf-8 -*-
"""희소 대칭 선형계를 켤레기울기로 푼다.

**numpy 는 의존성이 아니라 가속기다.** Rhino 8 py39 site-packages 에 numpy 가
없다는 것이 실측되어 있다(2026-08-14). 그래서 순수 파이썬 경로가 정본이고,
numpy 가 있으면 같은 답을 더 빨리 낸다. 두 경로의 일치는 테스트가 지킨다.

**왜 Cholesky 가 아니라 CG 인가.** 주름 벌점을 반복 재가중(IRLS)으로 넣기
때문에 강성행렬이 매 반복 바뀐다 → 사전 분해를 재사용할 수 없다. CG 는 분해가
없으므로 그 대가를 치르지 않는다. 두 결정이 서로를 지지한다.

**warm start 가 얼마나 버는지는 행렬의 형태에 달렸다** [실측 2026-08-14].
2차원 격자에서 12×12 는 59→54회, 24×24 는 128→116회로 약 10% 준다.
1차원 사슬에서는 **하나도 안 준다** — matvec 한 번이 정보를 한 칸씩만 옮겨
CG 가 n 회를 꽉 채워야 하기 때문이다(n=60 에서 59회, n=200 에서 199회, 차이 0).
실제 메쉬 라플라시안에서의 값은 아직 재지 않았다 [미검증].
"""

import math

try:
    import numpy
except ImportError:          # Rhino 8 py39 의 기본 상태
    numpy = None

HAS_NUMPY = numpy is not None
FORCE_PURE = False           # 테스트가 순수 경로를 강제할 때 True


class _Pure(object):
    """리스트 기반 벡터 연산."""

    @staticmethod
    def asvec(x):
        return [float(v) for v in x]

    @staticmethod
    def zeros(n):
        return [0.0] * n

    @staticmethod
    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    @staticmethod
    def sub(a, b):
        return [x - y for x, y in zip(a, b)]

    @staticmethod
    def axpy(s, x, y):
        """s*x + y"""
        return [s * xi + yi for xi, yi in zip(x, y)]


class _Numpy(object):
    """numpy 배열 기반. 인터페이스는 _Pure 와 같다."""

    @staticmethod
    def asvec(x):
        return numpy.asarray(x, dtype=numpy.float64)

    @staticmethod
    def zeros(n):
        return numpy.zeros(n, dtype=numpy.float64)

    @staticmethod
    def dot(a, b):
        return float(numpy.dot(a, b))

    @staticmethod
    def sub(a, b):
        return a - b

    @staticmethod
    def axpy(s, x, y):
        return s * x + y


def _backend():
    return _Numpy if (HAS_NUMPY and not FORCE_PURE) else _Pure


def tolist(x):
    # type: (object) -> list
    """백엔드에 무관하게 파이썬 리스트로 되돌린다."""
    return [float(v) for v in x]


class Sparse(object):
    """대칭 희소행렬. 요소 조립처럼 같은 자리에 여러 번 더한다."""

    def __init__(self, n):
        # type: (int) -> None
        self.n = n
        self._d = {}
        self._ready = False

    def add(self, i, j, v):
        # type: (int, int, float) -> None
        if v == 0.0:
            return
        k = (i, j)
        self._d[k] = self._d.get(k, 0.0) + v
        self._ready = False

    def pin(self, idx):
        # type: (int) -> None
        """정점 하나를 0 에 고정한다 — 라플라시안의 평행이동 자유도를 없앤다.

        행과 열을 **둘 다** 지운다. 열을 남기면 다른 행이 고정된 값을 계속
        보게 되어 대칭이 깨지고 CG 가 수렴하지 않는다.
        """
        for k in [k for k in self._d if k[0] == idx or k[1] == idx]:
            del self._d[k]
        self._d[(idx, idx)] = 1.0
        self._ready = False

    def _finalize(self):
        items = sorted(self._d.items())
        self._r = [ij[0] for ij, _v in items]
        self._c = [ij[1] for ij, _v in items]
        self._v = [v for _ij, v in items]
        if HAS_NUMPY:
            self._nr = numpy.array(self._r, dtype=numpy.int64)
            self._nc = numpy.array(self._c, dtype=numpy.int64)
            self._nv = numpy.array(self._v, dtype=numpy.float64)
        self._ready = True

    def matvec(self, x):
        # type: (object) -> object
        if not self._ready:
            self._finalize()
        if HAS_NUMPY and not FORCE_PURE:
            xa = numpy.asarray(x, dtype=numpy.float64)
            return numpy.bincount(self._nr, weights=self._nv * xa[self._nc],
                                  minlength=self.n)
        out = [0.0] * self.n
        for i, j, v in zip(self._r, self._c, self._v):
            out[i] += v * x[j]
        return out


def cg(matvec, b, x0=None, tol=1e-10, maxiter=1000):
    # type: (object, object, object, float, int) -> tuple
    """켤레기울기. (해, 사용한 반복 수) 를 돌려준다.

    **반복 수가 maxiter 이면 이 해를 믿으면 안 된다.** 그게 유일한 실패 신호다.

    두 가지 실패가 그 신호로 합쳐진다. 하나는 반복 상한 도달, 다른 하나는
    준정부호 붕괴(pAp ≤ 0)다. 후자는 조작된 경우가 아니다 — 둔각 삼각형이
    많으면 cotangent 가중이 음수가 되어 강성행렬이 정부호를 잃는다. 둘 다
    호출자에게는 "이 답을 쓰지 마라"로 같으므로 구별하지 않는다.

    **붕괴에서 그 시점의 반복 수를 돌려주면 안 된다** — 그러면 정상 수렴과
    구별되지 않아 호출자가 쓰레기를 믿는다.
    """
    V = _backend()
    n = len(b)
    b = V.asvec(b)
    x = V.zeros(n) if x0 is None else V.asvec(x0)
    r = V.sub(b, V.asvec(matvec(x)))
    p = V.asvec(r)
    rs = V.dot(r, r)
    if math.sqrt(rs) <= tol:
        return x, 0
    for it in range(1, maxiter + 1):
        ap = V.asvec(matvec(p))
        pap = V.dot(p, ap)
        if pap <= 0.0:
            # 준정부호 붕괴. maxiter 를 돌려줘 실패 신호를 낸다 — it 을 돌려주면
            # 정상 수렴과 구별되지 않는다.
            return x, maxiter
        alpha = rs / pap
        x = V.axpy(alpha, p, x)
        r = V.axpy(-alpha, ap, r)
        rs_new = V.dot(r, r)
        if math.sqrt(rs_new) <= tol:
            return x, it
        p = V.axpy(rs_new / rs, p, r)
        rs = rs_new
    return x, maxiter

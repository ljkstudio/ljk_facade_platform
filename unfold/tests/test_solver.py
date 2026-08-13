# -*- coding: utf-8 -*-
"""solver.py 테스트 — 두 경로가 같은 답을 내는가.

**numpy 는 의존성이 아니라 가속기다.** Rhino 8 py39 에 numpy 가 없다는 것이
실측되어 있으므로(2026-08-14), 순수 파이썬 경로가 정본이고 numpy 는 같은 답을
더 빨리 내야 한다. 그 '같은 답'을 여기서 못박는다.
"""

import math

import pytest

import solver as sv


def path_laplacian(n):
    """1차원 사슬의 라플라시안. 손으로 답을 아는 가장 단순한 SPD 계다."""
    sp = sv.Sparse(n)
    for i in range(n - 1):
        sp.add(i, i, 1.0)
        sp.add(i + 1, i + 1, 1.0)
        sp.add(i, i + 1, -1.0)
        sp.add(i + 1, i, -1.0)
    return sp


@pytest.fixture(autouse=True)
def restore_backend():
    before = sv.FORCE_PURE
    yield
    sv.FORCE_PURE = before


def test_matvec_matches_hand_computation():
    sp = sv.Sparse(3)
    sp.add(0, 0, 2.0)
    sp.add(0, 2, 1.0)
    sp.add(2, 1, -3.0)
    got = sv.tolist(sp.matvec([1.0, 2.0, 4.0]))
    assert got == pytest.approx([2.0 * 1.0 + 1.0 * 4.0, 0.0, -3.0 * 2.0])


def test_duplicate_entries_accumulate():
    """조립은 요소마다 같은 자리에 더한다 — 덮어쓰면 강성이 통째로 틀린다."""
    sp = sv.Sparse(1)
    sp.add(0, 0, 1.5)
    sp.add(0, 0, 2.5)
    assert sv.tolist(sp.matvec([2.0])) == pytest.approx([8.0])


def test_pin_replaces_row_and_column_with_identity():
    sp = path_laplacian(3)
    sp.pin(0)
    # 0번 행은 항등이고, 0번 열도 비어야 한다 (다른 행이 x[0] 을 안 본다)
    assert sv.tolist(sp.matvec([5.0, 0.0, 0.0])) == pytest.approx([5.0, 0.0, 0.0])


def test_cg_solves_a_small_spd_system_exactly():
    """A = [[4,1],[1,3]], b = [1,2] → x = [1/11, 7/11]"""
    sp = sv.Sparse(2)
    sp.add(0, 0, 4.0); sp.add(0, 1, 1.0)
    sp.add(1, 0, 1.0); sp.add(1, 1, 3.0)
    x, iters = sv.cg(sp.matvec, [1.0, 2.0], tol=1e-14)
    assert sv.tolist(x) == pytest.approx([1.0 / 11.0, 7.0 / 11.0], abs=1e-10)
    assert iters <= 2          # 2차원이면 CG 는 2회 안에 정확히 끝난다


def test_cg_solves_pinned_laplacian_with_known_answer():
    """사슬 0-1-2-3, x0 을 고정하고 끝에 힘 1 → 기울기 1 의 직선이 답이다."""
    n = 4
    sp = path_laplacian(n)
    sp.pin(0)
    b = [0.0] * n
    b[n - 1] = 1.0
    x, _ = sv.cg(sp.matvec, b, tol=1e-14, maxiter=200)
    assert sv.tolist(x) == pytest.approx([0.0, 1.0, 2.0, 3.0], abs=1e-8)


def test_pure_and_numpy_paths_agree():
    if not sv.HAS_NUMPY:
        pytest.skip("이 환경에 numpy 가 없다")
    n = 40
    b = [math.sin(i * 0.7) for i in range(n)]

    def solve():
        sp = path_laplacian(n)
        sp.pin(0)
        bb = list(b); bb[0] = 0.0
        x, _ = sv.cg(sp.matvec, bb, tol=1e-13, maxiter=2000)
        return sv.tolist(x)

    sv.FORCE_PURE = True
    pure = solve()
    sv.FORCE_PURE = False
    fast = solve()
    assert pure == pytest.approx(fast, abs=1e-8)


def grid_laplacian(k):
    """(k × k) 격자의 라플라시안. 워엄 스타트가 실제로 값어치를 하는 형태다."""
    n = k * k
    sp = sv.Sparse(n)
    for j in range(k):
        for i in range(k):
            a = j * k + i
            for di, dj in ((1, 0), (0, 1)):
                if i + di < k and j + dj < k:
                    b = (j + dj) * k + (i + di)
                    sp.add(a, a, 1.0); sp.add(b, b, 1.0)
                    sp.add(a, b, -1.0); sp.add(b, a, -1.0)
    return sp


def test_warm_start_from_the_exact_solution_costs_nothing():
    """이미 답을 알고 시작하면 반복이 0 이어야 한다 — x0 가 실제로 쓰인다는 증거."""
    n = 60
    sp = path_laplacian(n)
    sp.pin(0)
    b = [0.0] * n; b[n - 1] = 1.0
    x, _cold = sv.cg(sp.matvec, b, tol=1e-12, maxiter=5000)
    _again, iters = sv.cg(sp.matvec, b, x0=x, tol=1e-12, maxiter=5000)
    assert iters == 0


def test_warm_start_reduces_iterations_on_a_2d_laplacian():
    """ARAP 반복 사이에 b 가 조금만 바뀐다 — 그때 warm start 가 값어치를 한다.

    **1차원 사슬로는 이걸 보일 수 없다** [실측 2026-08-14]. 사슬에서는 matvec 한
    번이 정보를 한 칸씩만 옮기므로 CG 가 n 회를 꽉 채워야 하고, 워엄 스타트든
    아니든 똑같다 — n=60 에서 59회, n=200 에서 199회로 **차이가 0** 이었다.
    격자에서는 줄어든다: 12×12 는 59→54, 24×24 는 128→116.
    실제 쓰임(메쉬 라플라시안)이 격자 쪽이므로 그쪽으로 검사한다.
    """
    k = 12
    n = k * k
    sp = grid_laplacian(k)
    sp.pin(0)
    b1 = [0.0] * n; b1[n - 1] = 1.0
    x1, cold = sv.cg(sp.matvec, b1, tol=1e-12, maxiter=5000)
    b2 = list(b1); b2[n - 1] = 1.001
    _x2, warm = sv.cg(sp.matvec, b2, x0=x1, tol=1e-12, maxiter=5000)
    assert warm < cold, "cold=%d warm=%d" % (cold, warm)


def test_cg_reports_when_it_did_not_converge():
    """조용히 틀린 답을 돌려주면 안 된다."""
    sp = path_laplacian(50)
    sp.pin(0)
    b = [1.0] * 50; b[0] = 0.0
    _x, iters = sv.cg(sp.matvec, b, tol=1e-30, maxiter=3)
    assert iters == 3          # 상한에 걸렸음을 호출자가 알 수 있다

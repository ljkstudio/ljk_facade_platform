"""grid.py 테스트 모듈 (v1).

Rhino 환경에서 실행해야 합니다 (GhPython 또는 RhinoPython).
"""

import Rhino.Geometry as rg
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from grid import build_grid, compute_grid_counts, get_grid_indices, get_flat_index


def test_grid_counts_default():
    """디폴트 (1000, 1000, 200) → 6x6."""
    nx, ny = compute_grid_counts(1000.0, 1000.0, 200.0)
    assert nx == 6, "nx should be 6, got {}".format(nx)
    assert ny == 6, "ny should be 6, got {}".format(ny)
    print("PASS: test_grid_counts_default")


def test_grid_counts_2000():
    """2000, 2000, 200 → 11x11."""
    nx, ny = compute_grid_counts(2000.0, 2000.0, 200.0)
    assert nx == 11, "nx should be 11, got {}".format(nx)
    assert ny == 11, "ny should be 11, got {}".format(ny)
    print("PASS: test_grid_counts_2000")


def test_build_grid_36():
    """6x6=36개 그리드 생성 검증."""
    plane = rg.Plane.WorldXY
    pts, nx, ny = build_grid(plane, 1000.0, 1000.0, 200.0)
    assert len(pts) == 36, "Should have 36 pts, got {}".format(len(pts))
    assert nx == 6
    assert ny == 6
    print("PASS: test_build_grid_36")


def test_grid_origin():
    """첫 번째 포인트가 base_plane.Origin에 위치."""
    plane = rg.Plane.WorldXY
    pts, nx, ny = build_grid(plane, 1000.0, 1000.0, 200.0)
    assert abs(pts[0].X) < 1e-6, "First pt X should be 0"
    assert abs(pts[0].Y) < 1e-6, "First pt Y should be 0"
    print("PASS: test_grid_origin")


def test_grid_spacing():
    """인접 포인트 간 간격이 spacing과 일치."""
    plane = rg.Plane.WorldXY
    spacing = 200.0
    pts, nx, ny = build_grid(plane, 1000.0, 1000.0, spacing)
    d = pts[0].DistanceTo(pts[1])
    assert abs(d - spacing) < 1e-6, "Spacing should be {}, got {}".format(spacing, d)
    print("PASS: test_grid_spacing")


def test_grid_custom_plane():
    """커스텀 Plane에서 그리드 생성."""
    origin = rg.Point3d(100, 200, 50)
    plane = rg.Plane(origin, rg.Vector3d.ZAxis)
    pts, nx, ny = build_grid(plane, 400.0, 400.0, 200.0)
    assert abs(pts[0].X - 100) < 1e-6, "First pt X should be 100"
    assert abs(pts[0].Y - 200) < 1e-6, "First pt Y should be 200"
    print("PASS: test_grid_custom_plane")


def test_index_conversion():
    """인덱스 변환 roundtrip 검증."""
    nx = 6
    for idx in range(36):
        i, j = get_grid_indices(idx, nx)
        flat = get_flat_index(i, j, nx)
        assert flat == idx, "Index roundtrip failed: {} -> ({},{}) -> {}".format(idx, i, j, flat)
    print("PASS: test_index_conversion")


def test_grid_invalid_input():
    """유효하지 않은 입력 시 ValueError."""
    plane = rg.Plane.WorldXY
    try:
        build_grid(plane, 1000.0, 1000.0, -10.0)
        assert False, "Should raise ValueError"
    except ValueError:
        pass

    try:
        build_grid(plane, 0.0, 1000.0, 200.0)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    print("PASS: test_grid_invalid_input")


def run_all():
    """모든 그리드 테스트를 실행합니다."""
    test_grid_counts_default()
    test_grid_counts_2000()
    test_build_grid_36()
    test_grid_origin()
    test_grid_spacing()
    test_grid_custom_plane()
    test_index_conversion()
    test_grid_invalid_input()
    print("\n=== All grid tests passed ===")


if __name__ == "__main__":
    run_all()

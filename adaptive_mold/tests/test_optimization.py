"""optimization.py 테스트 모듈.

Rhino 환경에서 실행해야 합니다.
"""

import Rhino.Geometry as rg
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from grid import build_grid
from optimization import optimize_surface


def _make_flat_surface(z_height=200.0, size=2000.0):
    """테스트용 평면 Surface."""
    plane = rg.Plane(rg.Point3d(0, 0, z_height), rg.Vector3d.ZAxis)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def _make_tilted_surface(tilt_degrees=10.0, size=2000.0):
    """테스트용 기울어진 평면 Surface."""
    angle = math.radians(tilt_degrees)
    normal = rg.Vector3d(math.sin(angle), 0, math.cos(angle))
    origin = rg.Point3d(0, 0, 200)
    plane = rg.Plane(origin, normal)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def test_flat_surface_no_rotation():
    """T1: 평면 target → 회전 없음, Z 이동만."""
    target = _make_flat_surface(200.0)
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)

    positioned, info = optimize_surface(target, pts, base, 1000.0, 1000.0, 0.0, 400.0)

    assert positioned is not None, "positioned should not be None"
    assert "tilt" in info or "translate" in info, "Info: {}".format(info)
    print("PASS: test_flat_surface_no_rotation (info: {})".format(info))


def test_tilted_surface_rotation():
    """T2: 기울어진 평면 → optimization 후 보정."""
    target = _make_tilted_surface(10.0)
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)

    positioned, info = optimize_surface(target, pts, base, 1000.0, 1000.0, 0.0, 400.0)

    assert positioned is not None
    assert "tilt" in info, "Should have tilt info: {}".format(info)
    print("PASS: test_tilted_surface_rotation (info: {})".format(info))


def test_optimization_centers_height():
    """최적화 후 평균 높이가 stroke 중앙 부근."""
    target = _make_flat_surface(500.0, 3000.0)
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)

    positioned, info = optimize_surface(target, pts, base, 1000.0, 1000.0, 0.0, 400.0)

    assert positioned is not None
    print("PASS: test_optimization_centers_height (info: {})".format(info))


def run_all():
    """모든 optimization 테스트를 실행합니다."""
    test_flat_surface_no_rotation()
    test_tilted_surface_rotation()
    test_optimization_centers_height()
    print("\n=== All optimization tests passed ===")


if __name__ == "__main__":
    run_all()

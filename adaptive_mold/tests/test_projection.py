"""projection.py 테스트 모듈 (v1).

Rhino 환경에서 실행해야 합니다.
"""

import Rhino.Geometry as rg
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from grid import build_grid
from projection import calculate_heights, _clamp_height
from extension import EXTENSION_METHOD_SURFACE


def _make_flat_surface(z_height=200.0, size=2000.0):
    """테스트용 평면 Surface."""
    plane = rg.Plane(rg.Point3d(0, 0, z_height), rg.Vector3d.ZAxis)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def test_clamp_basic():
    """클램핑 기본 동작."""
    h, clamped = _clamp_height(500.0, 0.0, 400.0)
    assert h == 400.0, "Should clamp to 400, got {}".format(h)
    assert clamped is True

    h, clamped = _clamp_height(-10.0, 0.0, 400.0)
    assert h == 0.0, "Should clamp to 0, got {}".format(h)
    assert clamped is True

    h, clamped = _clamp_height(200.0, 0.0, 400.0)
    assert h == 200.0
    assert clamped is False
    print("PASS: test_clamp_basic")


def test_flat_surface_heights():
    """평면 target에 대한 높이 계산."""
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)
    z = 200.0
    target = _make_flat_surface(z, 3000.0)

    heights, clamp, ext = calculate_heights(
        pts, target, target, base, 0.0, 400.0, EXTENSION_METHOD_SURFACE
    )

    assert len(heights) == 36, "Should have 36 heights"

    h_set = set(round(h, 0) for h in heights)
    assert len(h_set) <= 2, "All heights should be ~equal: {}".format(h_set)
    print("PASS: test_flat_surface_heights")


def test_clamp_flags_deep_surface():
    """T5: 깊은 곡면 → clamp_flags 발생."""
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)
    target = _make_flat_surface(600.0, 3000.0)

    heights, clamp, ext = calculate_heights(
        pts, target, target, base, 0.0, 200.0, EXTENSION_METHOD_SURFACE
    )

    n_clamped = sum(1 for c in clamp if c)
    assert n_clamped > 0, "Should have clamped pins"
    assert all(h <= 200.0 for h in heights), "All heights should be <= max"
    print("PASS: test_clamp_flags_deep_surface (clamped={})".format(n_clamped))


def test_extension_flags_small_surface():
    """T4: 작은 곡면 → extension_flags 발생."""
    base = rg.Plane.WorldXY
    pts, nx, ny = build_grid(base, 1000.0, 1000.0, 200.0)
    target = _make_flat_surface(200.0, 600.0)

    heights, clamp, ext = calculate_heights(
        pts, target, target, base, 0.0, 400.0, EXTENSION_METHOD_SURFACE
    )

    n_ext = sum(1 for e in ext if e)
    n_panel = sum(1 for e in ext if not e)
    assert n_ext > 0, "Should have extension pins"
    assert n_panel > 0, "Should have panel pins"
    print("PASS: test_extension_flags_small_surface (panel={}, ext={})".format(n_panel, n_ext))


def run_all():
    """모든 projection 테스트를 실행합니다."""
    test_clamp_basic()
    test_flat_surface_heights()
    test_clamp_flags_deep_surface()
    test_extension_flags_small_surface()
    print("\n=== All projection tests passed ===")


if __name__ == "__main__":
    run_all()

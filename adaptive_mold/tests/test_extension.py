"""extension.py 테스트 모듈.

Rhino 환경에서 실행해야 합니다.
"""

import Rhino.Geometry as rg
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from extension import extend_surface, tangent_extrapolate, EXTENSION_METHOD_SURFACE, EXTENSION_METHOD_TANGENT


def _make_nurbs_surface(size=600.0, z_height=200.0):
    """테스트용 NURBS Surface (작은 크기)."""
    plane = rg.Plane(rg.Point3d(0, 0, z_height), rg.Vector3d.ZAxis)
    interval = rg.Interval(-size / 2, size / 2)
    srf = rg.PlaneSurface(plane, interval, interval)
    return srf.ToNurbsSurface()


def test_extend_surface_basic():
    """기본 surface extend 동작."""
    srf = _make_nurbs_surface(600.0, 200.0)
    result, method, branch = extend_surface(srf, 1000.0, 1000.0)
    assert result is not None, "Extended surface should not be None"
    assert method in [EXTENSION_METHOD_SURFACE, EXTENSION_METHOD_TANGENT]
    assert branch, "branch should be set"
    print("PASS: test_extend_surface_basic (method: {})".format(method))


def test_tangent_extrapolate():
    """tangent fallback 외삽."""
    plane = rg.Plane(rg.Point3d(0, 0, 200.0), rg.Vector3d.ZAxis)
    interval = rg.Interval(-300, 300)
    srf = rg.PlaneSurface(plane, interval, interval)

    base = rg.Plane.WorldXY
    far_pt = rg.Point3d(800, 800, 0)

    h = tangent_extrapolate(far_pt, srf, base)
    assert h is not None, "Tangent extrapolate should return a height"
    assert h > 0, "Height should be > 0, got {}".format(h)
    print("PASS: test_tangent_extrapolate (h={:.1f})".format(h))


def run_all():
    """모든 extension 테스트를 실행합니다."""
    test_extend_surface_basic()
    test_tangent_extrapolate()
    print("\n=== All extension tests passed ===")


if __name__ == "__main__":
    run_all()

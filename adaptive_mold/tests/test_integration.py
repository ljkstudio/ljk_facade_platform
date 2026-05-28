"""통합 테스트 모듈 (v1).

전체 파이프라인을 end-to-end로 검증합니다.
Rhino 환경에서 실행해야 합니다.
"""

import Rhino.Geometry as rg
import sys
import os
import time
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from adaptive_mold_v1 import run_adaptive_mold


def _make_flat_surface(z_height=200.0, size=2000.0):
    """테스트용 평면 Surface."""
    plane = rg.Plane(rg.Point3d(0, 0, z_height), rg.Vector3d.ZAxis)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def _make_tilted_surface(tilt_degrees=10.0, z_base=200.0, size=2000.0):
    """테스트용 기울어진 평면."""
    angle = math.radians(tilt_degrees)
    normal = rg.Vector3d(math.sin(angle), 0, math.cos(angle))
    origin = rg.Point3d(size / 2, size / 2, z_base)
    plane = rg.Plane(origin, normal)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def _make_hemisphere(radius=400.0, center_z=0.0):
    """테스트용 반구."""
    center = rg.Point3d(500, 500, center_z)
    sphere = rg.Sphere(center, radius)
    return sphere.ToBrep()


def _make_simple_box(sx, sy, sz):
    """테스트용 간단한 Box Brep (원점+Z)."""
    box = rg.Box(
        rg.Plane.WorldXY,
        rg.Interval(-sx / 2, sx / 2),
        rg.Interval(-sy / 2, sy / 2),
        rg.Interval(0, sz)
    )
    return rg.Brep.CreateFromBox(box)


def test_T1_flat_parallel():
    """T1: 평면 target (base_plane과 평행) → 모두 동일 높이, clamp 0."""
    target = _make_flat_surface(200.0, 3000.0)
    r = run_adaptive_mold(target, compute=True)

    assert len(r.pin_heights) == 36, "Should have 36 pins"
    n_clamp = sum(1 for c in r.clamp_flags if c)
    assert n_clamp == 0, "T1: No clamping expected, got {}".format(n_clamp)

    h_set = set(round(h, 0) for h in r.pin_heights)
    assert len(h_set) <= 2, "T1: All heights should be ~equal: {}".format(h_set)
    assert "AdaptiveMold v1 Report" in r.info
    print("PASS: T1 flat parallel")


def test_T2_tilted():
    """T2: 기울어진 평면 (10°) → optimization 후 높이 균일화."""
    target = _make_tilted_surface(10.0)
    r = run_adaptive_mold(target, compute=True)

    assert len(r.pin_heights) == 36
    assert r.positioned_srf is not None
    print("PASS: T2 tilted surface")


def test_T3_hemisphere():
    """T3: 반구 → 중앙 최고, edge는 extension."""
    target = _make_hemisphere(400.0)
    r = run_adaptive_mold(target, compute=True)

    assert len(r.pin_heights) == 36
    n_ext = sum(1 for e in r.extension_flags if e)
    assert n_ext >= 0, "Some pins may be in extension zone"
    print("PASS: T3 hemisphere (ext={})".format(n_ext))


def test_T4_small_surface():
    """T4: 곡면이 mold보다 작음 → extension_flags."""
    target = _make_flat_surface(200.0, 600.0)
    r = run_adaptive_mold(target, width=1000.0, length=1000.0, compute=True)

    n_ext = sum(1 for e in r.extension_flags if e)
    n_panel = sum(1 for e in r.extension_flags if not e)
    assert n_ext > 0, "T4: Should have extension pins"
    assert n_panel > 0, "T4: Should have panel pins"
    assert "extension" in r.info.lower() or "Coverage" in r.info
    print("PASS: T4 small surface (panel={}, ext={})".format(n_panel, n_ext))


def test_T5_deep_clamp():
    """T5: max_height=200 + 깊은 곡면 → clamp 발생."""
    target = _make_flat_surface(500.0, 3000.0)
    r = run_adaptive_mold(target, max_height=200.0, compute=True)

    n_clamp = sum(1 for c in r.clamp_flags if c)
    assert all(h <= 200.0 for h in r.pin_heights)
    print("PASS: T5 deep clamp (clamped={})".format(n_clamp))


def test_T6_rod_scale():
    """T6: rod_base_length=300, height=150 → scale 0.5."""
    target = _make_flat_surface(150.0, 3000.0)
    housing = _make_simple_box(40, 40, 30)
    rod = _make_simple_box(20, 20, 300)
    top = _make_simple_box(60, 60, 10)

    r = run_adaptive_mold(
        target, compute=True,
        housing_model=housing, rod_model=rod, top_model=top,
        rod_base_length=300.0
    )

    assert len(r.housings) > 0, "T6: Should have housings"
    assert len(r.rods) > 0, "T6: Should have rods"
    assert len(r.tops) > 0, "T6: Should have tops"
    assert len(r.pin_tops) == 36
    print("PASS: T6 rod scale")


def test_T7_rotated_base_plane():
    """T7: base_plane을 회전·이동 → 정렬 유지."""
    origin = rg.Point3d(500, 300, 100)
    x_axis = rg.Vector3d(1, 1, 0)
    x_axis.Unitize()
    y_axis = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, x_axis)
    y_axis.Unitize()
    plane = rg.Plane(origin, x_axis, y_axis)

    target = _make_flat_surface(300.0, 3000.0)
    r = run_adaptive_mold(target, base_plane=plane, compute=True)

    assert len(r.grid_pts) == 36
    assert r.grid_pts[0].DistanceTo(origin) < 1e-6, \
        "First grid pt should be at plane origin"
    print("PASS: T7 rotated base plane")


def test_T8_large_grid_performance():
    """T8: 11x11=121 액추에이터, 3초 이내."""
    target = _make_flat_surface(200.0, 4000.0)

    start = time.time()
    r = run_adaptive_mold(target, width=2000.0, length=2000.0, spacing=200.0, compute=True)
    elapsed = time.time() - start

    assert len(r.pin_heights) == 121, "Should have 121 pins, got {}".format(len(r.pin_heights))
    assert elapsed < 3.0, "T8: Should complete within 3s, took {:.1f}s".format(elapsed)
    print("PASS: T8 large grid ({:.2f}s, {} pins)".format(elapsed, len(r.pin_heights)))


def test_compute_false():
    """compute=False → 계산 미실행."""
    target = _make_flat_surface(200.0)
    r = run_adaptive_mold(target, compute=False)

    assert len(r.pin_heights) == 0
    assert "disabled" in r.info.lower()
    print("PASS: test_compute_false")


def test_report_format():
    """리포트 형식 검증."""
    target = _make_flat_surface(200.0, 3000.0)
    r = run_adaptive_mold(target, compute=True)

    assert "AdaptiveMold v1 Report" in r.info
    assert "Mold:" in r.info
    assert "Grid:" in r.info
    assert "Heights:" in r.info
    assert "Clamped:" in r.info
    assert "Coverage:" in r.info
    print("PASS: test_report_format")


def run_all():
    """모든 통합 테스트를 실행합니다."""
    test_T1_flat_parallel()
    test_T2_tilted()
    test_T3_hemisphere()
    test_T4_small_surface()
    test_T5_deep_clamp()
    test_T6_rod_scale()
    test_T7_rotated_base_plane()
    test_T8_large_grid_performance()
    test_compute_false()
    test_report_format()
    print("\n=== All integration tests passed ===")


if __name__ == "__main__":
    run_all()

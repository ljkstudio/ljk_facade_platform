#! python 3
# -*- coding: utf-8 -*-
"""Phase B(곡면 정렬) 진단 — 회전이 기울기를 없애는가, 키우는가.

배경:
    T2(10도 기울어진 평면)에서 36개 중 18개가 stroke 한계에 걸렸다.
    문서상 의도는 "optimization 후 높이 균일화"인데 결과가 정반대다.

결정적 실험:
    입력 기울기를 0/5/10/20도로 바꿔가며 **회전 후 남은 기울기**를 측정한다.

      잔여 ≈ 0         → 회전 정상. 원인은 다른 곳
      잔여 ≈ 입력      → 회전이 아무 일도 안 함
      잔여 ≈ 입력 x 2  → 회전 방향이 반대 (부호 오류)

    이 스크립트는 아무것도 고치지 않는다. 측정만 한다.

Rhino 안에서 실행: ScriptEditor → 열기 → Run
"""

import os
import sys
import math

import Rhino
import Rhino.Geometry as rg

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    HERE = r"C:\Users\leeja\Documents\dev\26_AdaptiveMold_development\adaptive_mold\tools"

SRC_DIR = os.path.normpath(os.path.join(HERE, "..", "src"))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO_ROOT, "plugin", "fixtures", "_diag_phase_b.txt")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _purge():
    src_norm = os.path.normcase(os.path.normpath(SRC_DIR))
    for name in list(sys.modules.keys()):
        path = getattr(sys.modules.get(name), "__file__", None)
        if path and os.path.normcase(os.path.normpath(path)).startswith(src_norm):
            del sys.modules[name]


_purge()

from grid import build_grid                                    # noqa: E402
from optimization import _measure_distances                    # noqa: E402
from optimization import _compute_grid_center_on_plane         # noqa: E402
from utils import get_brep_from_input, safe_duplicate_brep     # noqa: E402


_LOG = []


def log(msg=""):
    print(msg)
    _LOG.append(msg)


def make_tilted(tilt_degrees, z_base=200.0, size=2000.0):
    """test_integration._make_tilted_surface와 동일한 생성식."""
    angle = math.radians(tilt_degrees)
    normal = rg.Vector3d(math.sin(angle), 0, math.cos(angle))
    origin = rg.Point3d(size / 2, size / 2, z_base)
    plane = rg.Plane(origin, normal)
    interval = rg.Interval(-size / 2, size / 2)
    return rg.PlaneSurface(plane, interval, interval)


def fit_tilt_degrees(grid_pts, base_plane, brep):
    """현재 곡면의 '높이장 기울기'를 도(度)로 측정한다.

    optimization.optimize_surface와 같은 방식으로 (local_x, local_y, height)
    공간에서 평면을 피팅하고, 그 법선이 Z축과 이루는 각을 돌려준다.
    이 값이 0이면 모든 핀 높이가 같다는 뜻이다.
    """
    distances, sample_pts = _measure_distances(grid_pts, base_plane, brep)
    valid = [d for d in distances if d is not None]

    if len(valid) < 3:
        return (None, distances, valid)

    fit = rg.Plane.FitPlaneToPoints(sample_pts)
    if fit is None:
        return (None, distances, valid)

    if hasattr(fit, "__len__"):
        ok = fit[0] == rg.PlaneFitResult.Success
        plane = fit[1]
    else:
        ok, plane = True, fit

    if not ok:
        return (None, distances, valid)

    dot = plane.Normal * rg.Vector3d.ZAxis
    dot = max(-1.0, min(1.0, dot))
    ang = math.degrees(math.acos(abs(dot)))
    return (ang, distances, valid)


def spread(values):
    if not values:
        return 0.0
    return max(values) - min(values)


def apply_phase_b_rotation(brep, grid_pts, base_plane, width, length, sign,
                           normalize_normal=False):
    """optimization.optimize_surface의 회전 단계만 재현한다.

    sign=-1 이 현재 구현. sign=+1 이 반대 방향.
    normalize_normal=True 면 fit 법선을 +Z 반구로 뒤집은 뒤 각을 계산한다.

    회전만 적용하고 Z 평행이동은 하지 않는다 (기울기만 보려는 것).
    """
    distances, sample_pts = _measure_distances(grid_pts, base_plane, brep)
    valid = [d for d in distances if d is not None]
    if len(valid) < 3:
        return (None, None)

    fit = rg.Plane.FitPlaneToPoints(sample_pts)
    if hasattr(fit, "__len__"):
        ok = fit[0] == rg.PlaneFitResult.Success
        fit_plane = fit[1]
    else:
        ok, fit_plane = True, fit
    if not ok:
        return (None, None)

    positioned = safe_duplicate_brep(brep, "target")
    current_normal = fit_plane.Normal
    target_normal = rg.Vector3d.ZAxis

    if normalize_normal and (current_normal * target_normal) < 0:
        current_normal = -current_normal

    rot_axis = rg.Vector3d.CrossProduct(current_normal, target_normal)
    if rot_axis.Length <= 1e-10:
        return (positioned, 0.0)

    rot_axis.Unitize()
    dot = current_normal * target_normal
    dot = max(-1.0, min(1.0, dot))
    rot_angle = math.acos(dot)

    pivot = _compute_grid_center_on_plane(base_plane, width, length)
    rot_axis_world = (
        base_plane.XAxis * rot_axis.X +
        base_plane.YAxis * rot_axis.Y +
        base_plane.ZAxis * rot_axis.Z
    )
    rot_axis_world.Unitize()

    xform = rg.Transform.Rotation(sign * rot_angle, rot_axis_world, pivot)
    positioned.Transform(xform)
    return (positioned, math.degrees(rot_angle))


def main():
    base_plane = rg.Plane.WorldXY
    width = length = 1000.0
    spacing = 200.0
    grid_pts, nx, ny = build_grid(base_plane, width, length, spacing)

    log("Rhino {}".format(Rhino.RhinoApp.Version))
    log("Phase B 진단 — 회전 후 남은 기울기 측정")
    log("그리드 {}x{} = {}개, 몰드 {:.0f}x{:.0f}, stroke 0~400".format(
        nx, ny, nx * ny, width, length))
    log("")
    log("A=현재(-각), B=부호만반대(+각), C=법선정규화+(+각)")
    log("")
    log("{:>6} | {:>8} {:>8} | {:>9} {:>9} {:>9} | {:>7} {:>7} {:>7}".format(
        "입력", "각(A/B)", "각(C)", "잔여A", "잔여B", "잔여C", "폭A", "폭B", "폭C"))
    log("-" * 92)

    for tilt in (0.0, 5.0, 10.0, 20.0):
        srf = make_tilted(tilt)
        brep = get_brep_from_input(srf)

        rotated_a, ang_ab = apply_phase_b_rotation(
            brep, grid_pts, base_plane, width, length, -1.0)
        rotated_b, _ = apply_phase_b_rotation(
            brep, grid_pts, base_plane, width, length, +1.0)
        rotated_c, ang_c = apply_phase_b_rotation(
            brep, grid_pts, base_plane, width, length, +1.0, normalize_normal=True)

        res = []
        for rotated in (rotated_a, rotated_b, rotated_c):
            if rotated is None:
                res.append((None, []))
            else:
                a, _d, v = fit_tilt_degrees(grid_pts, base_plane, rotated)
                res.append((a, v))

        def fmt(v):
            return "{:.3f}".format(v) if v is not None else "-"

        log("{:>5.1f}° | {:>7}° {:>7}° | {:>8}° {:>8}° {:>8}° | {:>7} {:>7} {:>7}".format(
            tilt,
            fmt(ang_ab), fmt(ang_c),
            fmt(res[0][0]), fmt(res[1][0]), fmt(res[2][0]),
            "{:.1f}".format(spread(res[0][1])),
            "{:.1f}".format(spread(res[1][1])),
            "{:.1f}".format(spread(res[2][1])),
        ))

    log("")
    log("판정 기준:")
    log("  잔여A ≈ 입력 x 2 → 현재 구현의 회전 방향이 반대")
    log("  잔여C ≈ 0 이고 각(C) ≈ 입력 → 법선 정규화가 구조적으로 옳은 수정")
    log("  각(A/B)가 180-입력 이면 fit 법선이 -Z를 향한다는 뜻 (방향 미보장)")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(_LOG))
    log("")
    log("기록: {}".format(OUT))


try:
    main()
except Exception:
    import traceback
    tb = traceback.format_exc()
    print(tb)
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(_LOG) + "\n\n[예외]\n" + tb)
    except Exception:
        pass
    raise

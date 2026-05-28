"""Phase B: Surface Optimization (회전 + 평행이동) 모듈.

grid_pt들에서 곡면까지의 수직거리를 측정 → best-fit plane →
그 plane을 수평으로 만드는 회전 + Z 평행이동을 곡면에 적용합니다.
"""

import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as rgi
import math

from utils import (
    get_brep_from_input, safe_duplicate_brep,
    add_warning, add_remark, check_not_none
)


def optimize_surface(target_srf, grid_pts, base_plane, width, length,
                     min_height, max_height, component=None):
    # type: (...) -> tuple[rg.Brep | None, str]
    """목표 곡면을 stroke 범위 안에 맞도록 최적 위치로 정렬합니다.

    1. 각 grid_pt에서 법선 방향으로 ray → target_srf 교점까지 거리 측정
    2. in-bounds 포인트로 best-fit plane 계산
    3. fit plane의 법선을 수평으로 만드는 회전 적용
    4. 평균 높이를 stroke 중앙에 맞추는 Z 평행이동 적용

    Args:
        target_srf: 목표 곡면 (Surface/Brep).
        grid_pts: 그리드 포인트 리스트.
        base_plane: 몰드 베이스 평면.
        width: mold 가로 (mm).
        length: mold 세로 (mm).
        min_height: 최소 stroke (mm).
        max_height: 최대 stroke (mm).
        component: GhPython 컴포넌트 인스턴스.

    Returns:
        (positioned_srf, opt_info) 튜플.
        positioned_srf: 최적화된 곡면 (Brep).
        opt_info: 최적화 정보 문자열.
    """
    brep = get_brep_from_input(target_srf)
    if brep is None:
        return (None, "optimization skipped: invalid surface")

    raw_distances, sample_pts = _measure_distances(grid_pts, base_plane, brep)

    valid_distances = [d for d in raw_distances if d is not None]
    if len(valid_distances) < 3:
        add_warning(component, "Not enough in-bounds points for optimization ({})".format(
            len(valid_distances)))
        positioned = safe_duplicate_brep(brep, "target_srf")
        if len(valid_distances) > 0:
            target_h = (min_height + max_height) / 2.0
            avg_d = sum(valid_distances) / len(valid_distances)
            delta_z = target_h - avg_d
            trans = rg.Transform.Translation(base_plane.ZAxis * delta_z)
            positioned.Transform(trans)
            return (positioned, "translate only (dz={:.1f}mm, {} pts)".format(
                delta_z, len(valid_distances)))
        return (positioned, "no optimization (0 in-bounds points)")

    # best-fit plane
    fit_result = rg.Plane.FitPlaneToPoints(sample_pts)
    if fit_result is None or (hasattr(fit_result, '__len__') and len(fit_result) < 2):
        positioned = safe_duplicate_brep(brep, "target_srf")
        return (positioned, "plane fit failed, no optimization")

    if hasattr(fit_result, '__len__'):
        fit_ok = fit_result[0] == rg.PlaneFitResult.Success
        fit_plane = fit_result[1]
    else:
        fit_ok = True
        fit_plane = fit_result

    if not fit_ok:
        positioned = safe_duplicate_brep(brep, "target_srf")
        target_h = (min_height + max_height) / 2.0
        avg_d = sum(valid_distances) / len(valid_distances)
        delta_z = target_h - avg_d
        trans = rg.Transform.Translation(base_plane.ZAxis * delta_z)
        positioned.Transform(trans)
        return (positioned, "plane fit failed, translate only (dz={:.1f}mm)".format(delta_z))

    # 회전: fit_plane.Normal → (0,0,1) in local space
    positioned = safe_duplicate_brep(brep, "target_srf")
    if positioned is None:
        return (None, "DuplicateBrep failed")

    current_normal = fit_plane.Normal
    target_normal = rg.Vector3d.ZAxis

    rot_axis = rg.Vector3d.CrossProduct(current_normal, target_normal)
    rot_axis_len = rot_axis.Length

    tilt_angle = 0.0
    if rot_axis_len > 1e-10:
        rot_axis.Unitize()
        dot = current_normal * target_normal
        dot = max(-1.0, min(1.0, dot))
        rot_angle = math.acos(dot)
        tilt_angle = math.degrees(rot_angle)

        pivot = _compute_grid_center_on_plane(base_plane, width, length)

        rot_axis_world = (
            base_plane.XAxis * rot_axis.X +
            base_plane.YAxis * rot_axis.Y +
            base_plane.ZAxis * rot_axis.Z
        )
        rot_axis_world.Unitize()

        rot_xform = rg.Transform.Rotation(-rot_angle, rot_axis_world, pivot)
        positioned.Transform(rot_xform)

    # 회전 후 재측정 → Z 평행이동
    new_distances_raw, _ = _measure_distances(grid_pts, base_plane, positioned)
    new_valid = [d for d in new_distances_raw if d is not None]

    target_h = (min_height + max_height) / 2.0
    if len(new_valid) > 0:
        avg_new = sum(new_valid) / len(new_valid)
    else:
        avg_new = target_h

    delta_z = target_h - avg_new
    trans_xform = rg.Transform.Translation(base_plane.ZAxis * delta_z)
    positioned.Transform(trans_xform)

    opt_info = "tilt={:.1f}deg, dz={:.1f}mm".format(tilt_angle, delta_z)
    add_remark(component, "Surface optimized: {}".format(opt_info))

    return (positioned, opt_info)


def _measure_distances(grid_pts, base_plane, brep):
    # type: (list[rg.Point3d], rg.Plane, rg.Brep) -> tuple[list[float | None], list[rg.Point3d]]
    """각 grid_pt에서 법선 방향으로 곡면까지 거리를 측정합니다.

    Returns:
        (raw_distances, sample_pts_for_fit) 튜플.
        raw_distances: 거리 리스트 (None = 곡면 밖).
        sample_pts_for_fit: plane fitting용 로컬 좌표 포인트.
    """
    normal = base_plane.ZAxis
    raw_distances = []
    sample_pts = []

    for pt in grid_pts:
        hit_dist = _ray_cast_distance(pt, normal, brep)
        if hit_dist is not None:
            raw_distances.append(hit_dist)
            result = base_plane.RemapToPlaneSpace(pt)
            if result[0]:
                local_pt = result[1]
                sample_pts.append(rg.Point3d(local_pt.X, local_pt.Y, hit_dist))
        else:
            raw_distances.append(None)

    return (raw_distances, sample_pts)


def _ray_cast_distance(pt, direction, brep):
    # type: (rg.Point3d, rg.Vector3d, rg.Brep) -> float | None
    """양방향 ray-cast로 Brep과의 교점 거리를 계산합니다."""
    ray_pos = rg.Ray3d(pt, direction)
    t_pos = rgi.Intersection.RayShoot(ray_pos, [brep], 1)
    if t_pos is not None and len(t_pos) > 0:
        hit_pt = ray_pos.PointAt(t_pos[0])
        return pt.DistanceTo(hit_pt)

    ray_neg = rg.Ray3d(pt, -direction)
    t_neg = rgi.Intersection.RayShoot(ray_neg, [brep], 1)
    if t_neg is not None and len(t_neg) > 0:
        hit_pt = ray_neg.PointAt(t_neg[0])
        return pt.DistanceTo(hit_pt)

    return None


def _compute_grid_center_on_plane(base_plane, width, length):
    # type: (rg.Plane, float, float) -> rg.Point3d
    """그리드 중심을 base_plane 위에 투영한 World 좌표."""
    return base_plane.PointAt(width / 2.0, length / 2.0, 0)

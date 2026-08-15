# -*- coding: utf-8 -*-
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


# ──────────────────────────────────────
# Phase B 가지 식별자 (골든 픽스처 대조용)
#
# projection.py 의 BRANCH_* 와 같은 목적이다. 어느 경로로 정렬했는지가
# 출력에 남지 않아, C# 포팅본이 다른 가지를 타도 숫자가 비슷하면 모른다.
# 값은 C# 포팅본과 문자열까지 일치해야 한다.
# ──────────────────────────────────────

OPT_INVALID_SURFACE = "invalid_surface"   # Brep 추출 실패
OPT_TRANSLATE_ONLY = "translate_only"     # 유효점 < 3, 평행이동만
OPT_NO_POINTS = "no_points"               # 유효점 0, 아무것도 안 함
OPT_FIT_NONE = "fit_none"                 # FitPlaneToPoints 가 None
OPT_FIT_FAILED = "fit_failed"             # fit 실패 → 평행이동만
OPT_DUP_FAILED = "dup_failed"             # DuplicateBrep 실패
OPT_FULL = "full"                         # 회전 + 평행이동 (정상 경로)


def optimize_surface(target_srf, grid_pts, base_plane, width, length,
                     min_height, max_height, component=None):
    # type: (...) -> tuple[rg.Brep | None, str, str]
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
        (positioned_srf, opt_info, branch) 튜플.
        positioned_srf: 최적화된 곡면 (Brep).
        opt_info: 최적화 정보 문자열.
        branch: 탄 가지 (OPT_* 상수). 골든 픽스처 대조용 진단이며
            계산에는 쓰이지 않는다.
    """
    brep = get_brep_from_input(target_srf)
    if brep is None:
        return (None, "optimization skipped: invalid surface", OPT_INVALID_SURFACE)

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
                delta_z, len(valid_distances)), OPT_TRANSLATE_ONLY)
        return (positioned, "no optimization (0 in-bounds points)", OPT_NO_POINTS)

    # best-fit plane
    fit_result = rg.Plane.FitPlaneToPoints(sample_pts)
    if fit_result is None or (hasattr(fit_result, '__len__') and len(fit_result) < 2):
        positioned = safe_duplicate_brep(brep, "target_srf")
        return (positioned, "plane fit failed, no optimization", OPT_FIT_NONE)

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
        return (positioned, "plane fit failed, translate only (dz={:.1f}mm)".format(delta_z),
                OPT_FIT_FAILED)

    # 회전: fit_plane.Normal → (0,0,1) in local space
    positioned = safe_duplicate_brep(brep, "target_srf")
    if positioned is None:
        return (None, "DuplicateBrep failed", OPT_DUP_FAILED)

    current_normal = fit_plane.Normal
    target_normal = rg.Vector3d.ZAxis

    # FitPlaneToPoints는 법선 방향(부호)을 보장하지 않는다. 정규화하지 않으면
    # rot_angle이 실제 기울기가 아니라 (180 - 기울기)로 나온다.
    # 실측: 입력 5/10/20도에서 회전각이 175/170/160도로 계산됐다.
    if (current_normal * target_normal) < 0:
        current_normal = -current_normal

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

        # 벡터 a를 b로 돌리려면 축 (a x b) 둘레로 **+각도**만큼 돌려야 한다.
        # 이전 구현은 -rot_angle을 써서 기울기를 없애는 대신 2배로 키웠다.
        # 실측: 입력 5/10/20도 -> 잔여 10/20/40도 (오차 없이 정확히 2배).
        rot_xform = rg.Transform.Rotation(rot_angle, rot_axis_world, pivot)
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

    return (positioned, opt_info, OPT_FULL)


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
    """양방향 ray-cast로 Brep과의 교점 거리를 계산합니다.

    Note:
        `Intersection.RayShoot(Ray3d, IEnumerable<GeometryBase>, int)`는
        **교점 Point3d 배열**을 반환한다. 곡선 파라미터가 아니다.
        이전 구현은 반환값을 `Ray3d.PointAt(double)`에 넘겨
        레이가 곡면에 맞는 즉시 TypeError로 죽었다.
        사양서 01_core_geometry_adaptive_mold_v1.md §ray_to_brep_distance가
        처음부터 올바른 형태를 명시하고 있었다.
    """
    ray_pos = rg.Ray3d(pt, direction)
    hits_pos = rgi.Intersection.RayShoot(ray_pos, [brep], 1)
    if hits_pos is not None and len(hits_pos) > 0:
        return pt.DistanceTo(hits_pos[0])

    ray_neg = rg.Ray3d(pt, -direction)
    hits_neg = rgi.Intersection.RayShoot(ray_neg, [brep], 1)
    if hits_neg is not None and len(hits_neg) > 0:
        return pt.DistanceTo(hits_neg[0])

    return None


def _compute_grid_center_on_plane(base_plane, width, length):
    # type: (rg.Plane, float, float) -> rg.Point3d
    """그리드 중심을 base_plane 위에 투영한 World 좌표."""
    return base_plane.PointAt(width / 2.0, length / 2.0, 0)

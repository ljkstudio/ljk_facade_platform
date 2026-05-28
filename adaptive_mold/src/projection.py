"""Phase D: Height Calculation & Clamping 모듈.

모든 grid_pt에서 extended_srf(또는 positioned_srf)로 투영하여
핀 높이를 산출하고, stroke 범위로 클램핑합니다.
"""

import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as rgi

from utils import get_brep_from_input, check_not_none
from extension import tangent_extrapolate, EXTENSION_METHOD_TANGENT


def calculate_heights(grid_pts, positioned_srf, extended_srf, base_plane,
                      min_height, max_height, extension_method):
    # type: (...) -> tuple[list[float], list[bool], list[bool]]
    """모든 grid_pt에서 높이를 계산하고 클램핑합니다.

    Args:
        grid_pts: 그리드 포인트 리스트.
        positioned_srf: 최적화된 원본 곡면 (패널 영역 판정용).
        extended_srf: 확장된 곡면 (확장 영역 투영용).
        base_plane: 몰드 베이스 평면.
        min_height: 최소 stroke (mm).
        max_height: 최대 stroke (mm).
        extension_method: 확장 방식 ("surface_extend" 또는 "tangent_fallback").

    Returns:
        (pin_heights, clamp_flags, extension_flags) 튜플.
    """
    positioned_brep = get_brep_from_input(positioned_srf)
    extended_brep = get_brep_from_input(extended_srf)

    normal = base_plane.ZAxis
    pin_heights = []
    clamp_flags = []
    extension_flags = []

    for pt in grid_pts:
        h = None
        is_extension = False

        if positioned_brep is not None:
            h = _ray_cast_height(pt, normal, positioned_brep)

        if h is not None:
            is_extension = False
        else:
            is_extension = True
            if extended_brep is not None and extension_method != EXTENSION_METHOD_TANGENT:
                h = _ray_cast_height(pt, normal, extended_brep)
            if h is None and positioned_brep is not None:
                h = tangent_extrapolate(pt, positioned_brep, base_plane)
            if h is None:
                h = _closest_point_height(pt, normal, extended_brep or positioned_brep)

        if h is None:
            h = (min_height + max_height) / 2.0
            is_extension = True

        h, clamped = _clamp_height(h, min_height, max_height)
        pin_heights.append(h)
        clamp_flags.append(clamped)
        extension_flags.append(is_extension)

    return (pin_heights, clamp_flags, extension_flags)


def _ray_cast_height(pt, direction, brep):
    # type: (rg.Point3d, rg.Vector3d, rg.Brep) -> float | None
    """양방향 ray-cast로 높이를 계산합니다.

    Args:
        pt: 시작점.
        direction: ray 방향 (법선).
        brep: 대상 Brep.

    Returns:
        교점까지 거리 (float) 또는 None.
    """
    if brep is None:
        return None

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


def _closest_point_height(pt, normal, brep):
    # type: (rg.Point3d, rg.Vector3d, rg.Brep) -> float | None
    """ClosestPoint fallback으로 높이를 계산합니다."""
    if brep is None:
        return None

    cp = brep.ClosestPoint(pt)
    if cp is None:
        return None

    vec = cp - pt
    height = vec * rg.Vector3d(normal)
    return abs(height)


def _clamp_height(h, min_height, max_height):
    # type: (float, float, float) -> tuple[float, bool]
    """높이를 stroke 범위로 클램핑합니다.

    Args:
        h: 원본 높이.
        min_height: 최소 stroke.
        max_height: 최대 stroke.

    Returns:
        (클램핑된 높이, 클램핑 발생 여부) 튜플.
    """
    if h < min_height:
        return (min_height, True)
    elif h > max_height:
        return (max_height, True)
    return (h, False)

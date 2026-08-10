# -*- coding: utf-8 -*-
"""Phase C: Surface Edge Extension 모듈.

positioned_srf를 mold 전체 영역으로 확장합니다.
우선 Surface.Extend()를 시도하고, 실패 시 tangent plane 외삽 fallback을 사용합니다.
"""

import Rhino.Geometry as rg

from utils import (
    get_surface_from_input, get_brep_from_input,
    add_warning, add_remark, check_not_none
)


EXTENSION_METHOD_SURFACE = "surface_extend"
EXTENSION_METHOD_TANGENT = "tangent_fallback"


def extend_surface(positioned_srf, width, length, component=None):
    # type: (rg.Brep | rg.Surface, float, float, object) -> tuple[rg.Brep | rg.Surface | None, str]
    """positioned_srf를 mold 전체 영역으로 확장합니다.

    우선 Surface.Extend()를 UV 양방향으로 시도합니다.
    실패 시 원본을 그대로 반환하고 tangent_fallback 모드를 표시합니다.

    Args:
        positioned_srf: 최적화된 곡면 (Brep 또는 Surface).
        width: mold 가로 (mm).
        length: mold 세로 (mm).
        component: GhPython 컴포넌트 인스턴스.

    Returns:
        (extended_srf, method) 튜플.
        extended_srf: 확장된 곡면.
        method: 사용된 확장 방식 ("surface_extend" 또는 "tangent_fallback").
    """
    srf = get_surface_from_input(positioned_srf)
    if srf is None:
        add_warning(component, "Surface extension: could not extract surface")
        brep = get_brep_from_input(positioned_srf)
        return (brep, EXTENSION_METHOD_TANGENT)

    extension_length = max(width, length) * 1.5

    try:
        extended = srf

        extended = _try_extend(extended, rg.IsoStatus.South, extension_length)
        extended = _try_extend(extended, rg.IsoStatus.North, extension_length)
        extended = _try_extend(extended, rg.IsoStatus.West, extension_length)
        extended = _try_extend(extended, rg.IsoStatus.East, extension_length)

        if extended is not None and extended is not srf:
            brep = extended.ToBrep()
            if brep is not None:
                add_remark(component, "Surface extended via Surface.Extend()")
                return (brep, EXTENSION_METHOD_SURFACE)

    except Exception:
        pass

    add_warning(component, "Surface.Extend() failed, using tangent fallback")
    brep = get_brep_from_input(positioned_srf)
    return (brep, EXTENSION_METHOD_TANGENT)


def _try_extend(surface, iso_status, length):
    # type: (rg.Surface, rg.IsoStatus, float) -> rg.Surface | None
    """한 방향으로 Surface.Extend를 시도합니다.

    Args:
        surface: 확장할 서피스.
        iso_status: 확장 방향 (North/South/East/West).
        length: 확장 길이.

    Returns:
        확장된 Surface 또는 실패 시 원본.
    """
    if surface is None:
        return None

    try:
        result = surface.Extend(iso_status, length, True)
        if result is not None:
            return result
    except Exception:
        pass

    return surface


def tangent_extrapolate(grid_pt, positioned_srf, base_plane):
    # type: (rg.Point3d, rg.Brep | rg.Surface, rg.Plane) -> float | None
    """Tangent plane 외삽으로 grid_pt의 높이를 계산합니다.

    곡면 밖의 포인트에 대해:
    1. positioned_srf.ClosestPoint로 곡면 edge 위 가장 가까운 점 찾기
    2. 그 점의 접평면 계산
    3. grid_pt에서 base_plane.Normal 방향으로 접평면과의 교점까지 거리

    Args:
        grid_pt: 그리드 포인트 (World 좌표).
        positioned_srf: 위치 최적화된 곡면.
        base_plane: 몰드 베이스 평면.

    Returns:
        외삽된 높이 (float) 또는 None.
    """
    brep = get_brep_from_input(positioned_srf)
    if brep is None:
        return None

    cp = brep.ClosestPoint(grid_pt)
    if cp is None:
        return None

    closest_pt = cp

    srf_normal = _get_surface_normal_at_point(positioned_srf, closest_pt)
    if srf_normal is None:
        srf_normal = base_plane.ZAxis

    tangent_plane = rg.Plane(closest_pt, srf_normal)

    normal = base_plane.ZAxis
    line = rg.Line(grid_pt, grid_pt + normal * 10000.0)

    intersect_result = rg.Intersect.Intersection.LinePlane(line, tangent_plane)
    if intersect_result[0]:
        t = intersect_result[1]
        hit_pt = line.PointAt(t)
        vec = hit_pt - grid_pt
        height = vec * rg.Vector3d(normal)
        return abs(height)

    return None


def _get_surface_normal_at_point(geo, point):
    # type: (rg.Brep | rg.Surface, rg.Point3d) -> rg.Vector3d | None
    """곡면 위 한 점의 법선 벡터를 반환합니다."""
    srf = get_surface_from_input(geo)
    if srf is None:
        return None

    result = srf.ClosestPoint(point)
    if result[0]:
        u, v = result[1], result[2]
        normal = srf.NormalAt(u, v)
        if normal is not None:
            return normal

    return None

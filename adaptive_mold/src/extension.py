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


# ──────────────────────────────────────
# Phase C 가지 식별자 (골든 픽스처 대조용)
#
# method 는 Phase D 의 분기가 쓰는 계산 입력이라 손대지 않는다. 대신
# "왜 그 method 가 됐는지"를 따로 남긴다 — no_surface 와 tangent_fallback
# 은 둘 다 method="tangent_fallback" 이라 method 만으로는 구별되지 않는다.
# ──────────────────────────────────────

EXT_NO_SURFACE = "no_surface"               # get_surface_from_input 실패
EXT_SURFACE_EXTEND = "surface_extend"       # Surface.Extend 성공
EXT_TANGENT_FALLBACK = "tangent_fallback"   # 실패 → 접평면 외삽


def extend_surface(positioned_srf, width, length, component=None):
    # type: (rg.Brep | rg.Surface, float, float, object) -> tuple[rg.Brep | rg.Surface | None, str, str]
    """positioned_srf를 mold 전체 영역으로 확장합니다.

    우선 Surface.Extend()를 UV 양방향으로 시도합니다.
    실패 시 원본을 그대로 반환하고 tangent_fallback 모드를 표시합니다.

    Args:
        positioned_srf: 최적화된 곡면 (Brep 또는 Surface).
        width: mold 가로 (mm).
        length: mold 세로 (mm).
        component: GhPython 컴포넌트 인스턴스.

    Returns:
        (extended_srf, method, branch) 튜플.
        extended_srf: 확장된 곡면.
        method: 사용된 확장 방식 ("surface_extend" 또는 "tangent_fallback").
        branch: 탄 가지 (EXT_* 상수). 골든 픽스처 대조용 진단이며
            계산에는 쓰이지 않는다.
    """
    # get_surface_from_input 은 첫 face만 쓰는데 component 를 받지 않아
    # 조용히 나머지를 버린다. 호출부인 여기서 경고한다.
    brep_in = get_brep_from_input(positioned_srf)
    if brep_in is not None and brep_in.Faces.Count > 1:
        add_warning(component,
                    u"target_srf 의 face 가 {} 개다. 곡면 확장(Phase C)은 첫 face "
                    u"만 쓰므로 결과가 나머지 face 를 반영하지 않는다. 단일 face 로 "
                    u"합치거나 face 마다 따로 돌릴 것.".format(brep_in.Faces.Count))

    srf = get_surface_from_input(positioned_srf)
    if srf is None:
        add_warning(component,
                    u"positioned_srf 에서 Surface 를 얻지 못해 곡면 확장을 "
                    u"건너뛰었다. 몰드 밖 핀은 전부 접평면 외삽값이 된다.")
        brep = get_brep_from_input(positioned_srf)
        return (brep, EXTENSION_METHOD_TANGENT, EXT_NO_SURFACE)

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
                add_remark(component, u"Phase C 확장 완료 — Surface.Extend 를 썼다.")
                return (brep, EXTENSION_METHOD_SURFACE, EXT_SURFACE_EXTEND)

    except Exception:
        pass

    # Warning 이 아니라 Remark 다. 흔하게 뜨는 경고는 경고 무시를 학습시킨다.
    add_remark(component,
               u"곡면 확장에 Surface.Extend 를 쓰지 못해 접평면 외삽으로 "
               u"대체했다. 몰드 안쪽(extension_flags=False) 핀은 영향이 없다.")
    brep = get_brep_from_input(positioned_srf)
    return (brep, EXTENSION_METHOD_TANGENT, EXT_TANGENT_FALLBACK)


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

"""Phase D: Height Calculation & Clamping 모듈.

모든 grid_pt에서 extended_srf(또는 positioned_srf)로 투영하여
핀 높이를 산출하고, stroke 범위로 클램핑합니다.
"""

import Rhino.Geometry as rg
import Rhino.Geometry.Intersect as rgi

from utils import get_brep_from_input, check_not_none
from extension import tangent_extrapolate, EXTENSION_METHOD_TANGENT


# ──────────────────────────────────────
# 폴백 가지 식별자 (골든 픽스처 대조용)
#
# 높이 하나를 구하는 데 폴백이 여러 단계인데, 어느 가지를 탔는지가
# 출력에 남지 않는다. C# 포팅본이 다른 가지를 타도 숫자가 비슷하면
# 모르고 지나가므로, 핀별로 가지를 기록해 픽스처에 함께 덤프한다.
# 값은 C# 포팅본과 문자열까지 정확히 일치해야 한다.
# ──────────────────────────────────────

BRANCH_RAY_POS_PANEL = "ray+/panel"    # positioned_srf, +법선 레이캐스트
BRANCH_RAY_NEG_PANEL = "ray-/panel"    # positioned_srf, -법선 레이캐스트
BRANCH_RAY_POS_EXT = "ray+/ext"        # extended_srf, +법선
BRANCH_RAY_NEG_EXT = "ray-/ext"        # extended_srf, -법선
BRANCH_TANGENT = "tangent"             # tangent_extrapolate 외삽
BRANCH_CLOSEST = "closest"             # ClosestPoint 투영
BRANCH_DEFAULT = "default"             # 전부 실패 → (min+max)/2


def calculate_heights(grid_pts, positioned_srf, extended_srf, base_plane,
                      min_height, max_height, extension_method,
                      branch_out=None):
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
        branch_out: 리스트를 넘기면 핀별로 탄 폴백 가지(BRANCH_*)를 채운다.
            None이면 아무것도 하지 않는다. **계산 결과에는 영향이 없다.**

    Returns:
        (pin_heights, clamp_flags, extension_flags) 튜플.
        반환 타입은 기존과 동일하다 — 진단은 branch_out으로만 나간다.
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
        branch = None

        if positioned_brep is not None:
            h, sign = _ray_cast_height(pt, normal, positioned_brep)
            if h is not None:
                branch = (BRANCH_RAY_POS_PANEL if sign == "+"
                          else BRANCH_RAY_NEG_PANEL)

        if h is not None:
            is_extension = False
        else:
            is_extension = True
            if extended_brep is not None and extension_method != EXTENSION_METHOD_TANGENT:
                h, sign = _ray_cast_height(pt, normal, extended_brep)
                if h is not None:
                    branch = (BRANCH_RAY_POS_EXT if sign == "+"
                              else BRANCH_RAY_NEG_EXT)
            if h is None and positioned_brep is not None:
                h = tangent_extrapolate(pt, positioned_brep, base_plane)
                if h is not None:
                    branch = BRANCH_TANGENT
            if h is None:
                h = _closest_point_height(pt, normal, extended_brep or positioned_brep)
                if h is not None:
                    branch = BRANCH_CLOSEST

        if h is None:
            h = (min_height + max_height) / 2.0
            is_extension = True
            branch = BRANCH_DEFAULT

        h, clamped = _clamp_height(h, min_height, max_height)
        pin_heights.append(h)
        clamp_flags.append(clamped)
        extension_flags.append(is_extension)

        if branch_out is not None:
            branch_out.append(branch)

    return (pin_heights, clamp_flags, extension_flags)


def _ray_cast_height(pt, direction, brep):
    # type: (rg.Point3d, rg.Vector3d, rg.Brep) -> tuple[float | None, str | None]
    """양방향 ray-cast로 높이를 계산합니다.

    Args:
        pt: 시작점.
        direction: ray 방향 (법선).
        brep: 대상 Brep.

    Returns:
        (교점까지 거리, 성공한 방향) 튜플.
        방향은 "+"(법선) 또는 "-"(역법선). 둘 다 실패하면 (None, None).

    Note:
        `Intersection.RayShoot(Ray3d, IEnumerable<GeometryBase>, int)`는
        **교점 Point3d 배열**을 반환한다. 곡선 파라미터가 아니다.
        이전 구현은 반환값을 `Ray3d.PointAt(double)`에 넘겨
        레이가 곡면에 맞는 즉시 TypeError로 죽었다.
        `optimization.py::_ray_cast_distance`에도 같은 결함이 복제돼 있었다.
        사양서 01_core_geometry_adaptive_mold_v1.md §ray_to_brep_distance가
        처음부터 올바른 형태를 명시하고 있었다.
    """
    if brep is None:
        return (None, None)

    ray_pos = rg.Ray3d(pt, direction)
    hits_pos = rgi.Intersection.RayShoot(ray_pos, [brep], 1)
    if hits_pos is not None and len(hits_pos) > 0:
        return (pt.DistanceTo(hits_pos[0]), "+")

    ray_neg = rg.Ray3d(pt, -direction)
    hits_neg = rgi.Intersection.RayShoot(ray_neg, [brep], 1)
    if hits_neg is not None and len(hits_neg) > 0:
        return (pt.DistanceTo(hits_neg[0]), "-")

    return (None, None)


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

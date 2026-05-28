"""Phase E: 3D Model Transformation 모듈.

사용자가 제공한 housing/rod/top 모델을 각 그리드 포인트에 배치합니다.
- housing: 단순 이동 (PlaneToPlane)
- rod: 이동 + Z 스케일 (pin_height / rod_base_length)
- top: rod 상단으로 이동
"""

import Rhino.Geometry as rg

from utils import safe_duplicate_brep, add_warning, check_not_none


def get_housing_height(housing_model):
    # type: (rg.Brep) -> float
    """Housing 모델의 높이를 bounding box에서 자동 계산합니다.

    Args:
        housing_model: Housing Brep (원점에 +Z 방향 모델링).

    Returns:
        Housing 높이 (mm). 유효하지 않으면 0.0.
    """
    if housing_model is None:
        return 0.0

    bbox = housing_model.GetBoundingBox(True)
    if not bbox.IsValid:
        return 0.0

    return bbox.Max.Z - bbox.Min.Z


def transform_models(grid_pts, pin_heights, base_plane,
                     housing_model, rod_model, top_model,
                     rod_base_length, component=None):
    # type: (...) -> tuple[list[rg.Brep], list[rg.Brep], list[rg.Brep], list[rg.Point3d]]
    """각 그리드 포인트에 housing/rod/top 모델 인스턴스를 배치합니다.

    Args:
        grid_pts: 그리드 포인트 리스트.
        pin_heights: 각 액추에이터 높이 리스트.
        base_plane: 몰드 베이스 평면.
        housing_model: Housing Brep (원점+Z 모델링).
        rod_model: Rod Brep (원점+Z 모델링).
        top_model: Top Brep (원점+Z 모델링).
        rod_base_length: Rod 기준 길이 (mm).
        component: GhPython 컴포넌트 인스턴스.

    Returns:
        (housings, rods, tops, pin_tops) 튜플.
    """
    housing_height = get_housing_height(housing_model)
    normal = base_plane.ZAxis
    source_plane = rg.Plane.WorldXY

    housings = []
    rods = []
    tops = []
    pin_tops = []

    has_housing = housing_model is not None
    has_rod = rod_model is not None
    has_top = top_model is not None

    if rod_base_length is None or rod_base_length <= 0:
        rod_base_length = 1.0
        if has_rod:
            add_warning(component, "rod_base_length invalid, using 1.0")

    fail_count = 0

    for idx, (pt, h) in enumerate(zip(grid_pts, pin_heights)):
        target_plane = rg.Plane(pt, normal)

        # Housing
        if has_housing:
            h_inst = _place_model(housing_model, source_plane, target_plane)
            if h_inst is not None:
                housings.append(h_inst)
            else:
                fail_count += 1
        
        # Rod
        if has_rod:
            rod_origin = rg.Point3d(pt) + normal * housing_height
            rod_plane = rg.Plane(rod_origin, normal)

            scale_factor = h / rod_base_length
            r_inst = _place_scaled_model(rod_model, source_plane, rod_plane,
                                         1.0, 1.0, scale_factor)
            if r_inst is not None:
                rods.append(r_inst)
            else:
                fail_count += 1

        # Top
        if has_top:
            top_origin = rg.Point3d(pt) + normal * (housing_height + h)
            top_plane = rg.Plane(top_origin, normal)

            t_inst = _place_model(top_model, source_plane, top_plane)
            if t_inst is not None:
                tops.append(t_inst)

                top_bbox = t_inst.GetBoundingBox(True)
                if top_bbox.IsValid:
                    pin_tops.append(top_bbox.Center)
                else:
                    pin_tops.append(top_origin)
            else:
                fail_count += 1
                pin_tops.append(rg.Point3d(pt) + normal * (housing_height + h))
        else:
            pin_tops.append(rg.Point3d(pt) + normal * (housing_height + h))

    if fail_count > 0:
        add_warning(component, "{} model instances failed to transform".format(fail_count))

    return (housings, rods, tops, pin_tops)


def _place_model(model, source_plane, target_plane):
    # type: (rg.Brep, rg.Plane, rg.Plane) -> rg.Brep | None
    """모델을 source_plane에서 target_plane으로 이동 배치합니다.

    Args:
        model: 원본 Brep.
        source_plane: 원본 기준 평면 (보통 WorldXY).
        target_plane: 대상 평면.

    Returns:
        변환된 Brep 사본, 실패 시 None.
    """
    inst = safe_duplicate_brep(model, "model")
    if inst is None:
        return None

    xform = rg.Transform.PlaneToPlane(source_plane, target_plane)
    if not inst.Transform(xform):
        return None

    return inst


def _place_scaled_model(model, source_plane, target_plane,
                        scale_x, scale_y, scale_z):
    # type: (rg.Brep, rg.Plane, rg.Plane, float, float, float) -> rg.Brep | None
    """모델을 스케일한 후 target_plane으로 이동 배치합니다.

    스케일은 source_plane(WorldXY) 기준으로 먼저 적용한 후,
    PlaneToPlane으로 최종 위치에 배치합니다.

    Args:
        model: 원본 Brep.
        source_plane: 원본 기준 평면.
        target_plane: 대상 평면.
        scale_x: X 방향 스케일.
        scale_y: Y 방향 스케일.
        scale_z: Z 방향 스케일.

    Returns:
        변환된 Brep 사본, 실패 시 None.
    """
    inst = safe_duplicate_brep(model, "scaled_model")
    if inst is None:
        return None

    scale_xform = rg.Transform.Scale(source_plane, scale_x, scale_y, scale_z)
    if not inst.Transform(scale_xform):
        return None

    place_xform = rg.Transform.PlaneToPlane(source_plane, target_plane)
    if not inst.Transform(place_xform):
        return None

    return inst

"""공용 유틸리티 모듈.

RhinoCommon API 안전 래퍼, GH 메시지 헬퍼, 로컬-월드 좌표 변환 등을 제공합니다.
"""

import Rhino.Geometry as rg
import Grasshopper as gh


GH_WARNING = gh.Kernel.GH_RuntimeMessageLevel.Warning
GH_ERROR = gh.Kernel.GH_RuntimeMessageLevel.Error
GH_REMARK = gh.Kernel.GH_RuntimeMessageLevel.Remark


# ──────────────────────────────────────
# GH 메시지 헬퍼
# ──────────────────────────────────────

def add_message(component, level, message):
    # type: (object, object, str) -> None
    """GH 컴포넌트에 런타임 메시지를 추가합니다."""
    if component is not None:
        component.AddRuntimeMessage(level, message)


def add_warning(component, message):
    # type: (object, str) -> None
    add_message(component, GH_WARNING, message)


def add_error(component, message):
    # type: (object, str) -> None
    add_message(component, GH_ERROR, message)


def add_remark(component, message):
    # type: (object, str) -> None
    add_message(component, GH_REMARK, message)


# ──────────────────────────────────────
# None 체크 / 입력 검증
# ──────────────────────────────────────

def check_not_none(value, name="result"):
    # type: (object, str) -> bool
    """RhinoCommon API 반환값이 None인지 검사합니다."""
    return value is not None


def validate_positive_float(value, name, default):
    # type: (object, str, float) -> float
    """양의 실수를 검증합니다. 유효하지 않으면 기본값을 반환합니다."""
    if value is None:
        return default
    try:
        val = float(value)
        if val <= 0:
            return default
        return val
    except (ValueError, TypeError):
        return default


def validate_non_negative_float(value, name, default):
    # type: (object, str, float) -> float
    """0 이상 실수를 검증합니다."""
    if value is None:
        return default
    try:
        val = float(value)
        if val < 0:
            return default
        return val
    except (ValueError, TypeError):
        return default


# ──────────────────────────────────────
# 좌표 변환 헬퍼
# ──────────────────────────────────────

def world_to_local(point, plane):
    # type: (rg.Point3d, rg.Plane) -> rg.Point3d
    """World 좌표를 Plane 로컬 좌표로 변환합니다.

    Args:
        point: World 좌표 Point3d.
        plane: 기준 Plane.

    Returns:
        로컬 좌표 Point3d (X, Y, Z = plane 기준).
    """
    xform = rg.Transform.ChangeBasis(rg.Plane.WorldXY, plane)
    pt = rg.Point3d(point)
    pt.Transform(xform)
    return pt


def local_to_world(point, plane):
    # type: (rg.Point3d, rg.Plane) -> rg.Point3d
    """Plane 로컬 좌표를 World 좌표로 변환합니다.

    Args:
        point: 로컬 좌표 Point3d.
        plane: 기준 Plane.

    Returns:
        World 좌표 Point3d.
    """
    xform = rg.Transform.ChangeBasis(plane, rg.Plane.WorldXY)
    pt = rg.Point3d(point)
    pt.Transform(xform)
    return pt


def get_surface_from_input(geo):
    # type: (object) -> rg.Surface | None
    """입력 지오메트리에서 Surface를 추출합니다.

    Brep이면 첫 번째 Face의 UnderlyingSurface를,
    Surface이면 그대로 반환합니다.

    Args:
        geo: 입력 지오메트리 (Surface 또는 Brep).

    Returns:
        rg.Surface 또는 None.
    """
    if geo is None:
        return None
    if isinstance(geo, rg.Surface):
        return geo
    if isinstance(geo, rg.Brep):
        if geo.Faces.Count > 0:
            return geo.Faces[0].UnderlyingSurface()
    return None


def get_brep_from_input(geo):
    # type: (object) -> rg.Brep | None
    """입력 지오메트리에서 Brep을 추출합니다."""
    if geo is None:
        return None
    if isinstance(geo, rg.Brep):
        return geo
    if isinstance(geo, rg.Surface):
        return geo.ToBrep()
    return None


def safe_duplicate_brep(brep, name="brep"):
    # type: (rg.Brep, str) -> rg.Brep | None
    """Brep을 안전하게 복제합니다. 실패 시 None."""
    if brep is None:
        return None
    dup = brep.DuplicateBrep()
    return dup

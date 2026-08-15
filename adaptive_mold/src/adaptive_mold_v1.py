# -*- coding: utf-8 -*-
"""AdaptiveMold v1 — GhPython 컴포넌트 진입점.

입력 곡면을 액추에이터 stroke 범위 안에 들도록 최적 위치로 정렬한 뒤,
곡면을 mold 영역 전체로 확장하고, 각 액추에이터의 높이를 산출하여
사용자의 3D 모델(housing/rod/top)을 변형시킵니다.

GhPython 컴포넌트에 붙여넣을 코드:
    import sys
    sys.path.insert(0, r"C:\\...\\adaptive_mold\\src")
    from adaptive_mold_v1 import ghpython_run

    (positioned_srf, extended_srf, housings, rods, tops,
     pin_heights, pin_tops, grid_pts, clamp_flags,
     extension_flags, info) = ghpython_run(
        target_srf, base_plane, width, length, spacing,
        max_height, min_height, housing_model, rod_model,
        top_model, rod_base_length, compute, ghenv.Component)

Inputs:
    target_srf      Surface/Brep    목표 곡면
    base_plane      Plane           몰드 베이스 평면 (기본 WorldXY)
    width           float           mold 가로 mm (기본 1000)
    length          float           mold 세로 mm (기본 1000)
    spacing         float           액추에이터 간격 mm (기본 200)
    max_height      float           최대 stroke mm (기본 400)
    min_height      float           최소 stroke mm (기본 0)
    housing_model   Brep            본체 (원점+Z)
    rod_model       Brep            로드 (원점+Z)
    top_model       Brep            상단 헤드 (원점+Z)
    rod_base_length float           rod 기준 길이 mm
    compute         bool            True일 때만 실행
"""

import Rhino.Geometry as rg

from grid import build_grid
from optimization import optimize_surface
from extension import extend_surface, EXTENSION_METHOD_TANGENT
from projection import calculate_heights
from transformation import transform_models
from utils import (
    validate_positive_float, validate_non_negative_float,
    get_brep_from_input, add_error, add_warning, add_remark
)


class AdaptiveMoldResult(object):
    """컴포넌트 출력 데이터 컨테이너."""

    def __init__(self):
        self.positioned_srf = None
        self.extended_srf = None
        self.housings = []
        self.rods = []
        self.tops = []
        self.pin_heights = []
        self.pin_tops = []
        self.grid_pts = []
        self.clamp_flags = []
        self.extension_flags = []
        self.info = ""
        # 핀별로 탄 폴백 가지 (projection.BRANCH_*). 골든 픽스처 대조용 진단이며
        # ghpython_run의 반환 튜플에는 포함되지 않는다.
        self.branch_taken = []
        # Phase B·C가 탄 가지 (optimization.OPT_* / extension.EXT_*).
        # branch_taken이 Phase D만 덮고 있어 B·C의 선택은 대조 대상이 아니었다.
        self.opt_branch = ""
        self.ext_branch = ""


def run_adaptive_mold(target_srf, base_plane=None,
                      width=1000.0, length=1000.0, spacing=200.0,
                      max_height=400.0, min_height=0.0,
                      housing_model=None, rod_model=None, top_model=None,
                      rod_base_length=None,
                      compute=True, component=None):
    # type: (...) -> AdaptiveMoldResult
    """AdaptiveMold v1 전체 파이프라인을 실행합니다.

    Phase A → B → C → D → E 순서로 실행합니다.

    Args:
        target_srf: 목표 곡면.
        base_plane: 몰드 베이스 평면 (None이면 WorldXY).
        width: mold 가로 (mm).
        length: mold 세로 (mm).
        spacing: 액추에이터 간격 (mm).
        max_height: 최대 stroke (mm).
        min_height: 최소 stroke (mm).
        housing_model: Housing Brep.
        rod_model: Rod Brep.
        top_model: Top Brep.
        rod_base_length: Rod 기준 길이 (mm).
        compute: True일 때만 실행.
        component: GhPython 컴포넌트 인스턴스.

    Returns:
        AdaptiveMoldResult 객체.
    """
    result = AdaptiveMoldResult()

    if not compute:
        result.info = "Compute is disabled. Set compute=True to run."
        add_remark(component, u"compute 가 꺼져 있다. 계산하려면 Boolean Toggle 을 True 로.")
        return result

    # --- 입력 검증 ---
    if base_plane is None:
        base_plane = rg.Plane.WorldXY

    width = validate_positive_float(width, "width", 1000.0)
    length = validate_positive_float(length, "length", 1000.0)
    spacing = validate_positive_float(spacing, "spacing", 200.0)
    max_height = validate_positive_float(max_height, "max_height", 400.0)
    min_height = validate_non_negative_float(min_height, "min_height", 0.0)

    if min_height >= max_height:
        add_error(component,
                  u"min_height ({}) 가 max_height ({}) 보다 크거나 같다. "
                  u"계산하지 않았다. 두 값을 확인할 것.".format(min_height, max_height))
        return result

    if target_srf is None:
        add_error(component, u"target_srf 가 비어 있다. Surface 또는 Brep 을 물릴 것.")
        return result

    target_brep = get_brep_from_input(target_srf)
    if target_brep is None:
        add_error(component,
                  u"target_srf 에서 Brep 을 얻지 못했다. Surface 또는 Brep 을 물릴 것 "
                  u"(Mesh·Curve·Point 는 받지 않는다).")
        return result

    # --- Phase A: Grid Generation ---
    try:
        grid_pts, nx, ny = build_grid(base_plane, width, length, spacing)
    except ValueError as e:
        add_error(component, str(e))
        return result

    result.grid_pts = grid_pts
    total_pins = nx * ny

    # spacing 이 몰드 크기를 나누지 못하면 가장자리가 비는데 지금까지 조용했다.
    rem_x = width - (nx - 1) * spacing
    rem_y = length - (ny - 1) * spacing
    if rem_x > 1e-9 or rem_y > 1e-9:
        add_remark(component,
                   u"spacing {:g} 이 몰드 크기를 나누지 못한다. 핀은 X 방향 {:g}mm, "
                   u"Y 방향 {:g}mm 까지만 덮는다 (나머지 {:g}/{:g}mm 는 비어 있다)."
                   .format(spacing, (nx - 1) * spacing, (ny - 1) * spacing, rem_x, rem_y))

    # --- Phase B: Surface Optimization ---
    positioned_srf, opt_info, opt_branch = optimize_surface(
        target_brep, grid_pts, base_plane, width, length,
        min_height, max_height, component
    )
    result.opt_branch = opt_branch

    if positioned_srf is None:
        add_error(component,
                  u"Phase B 정렬이 실패했다 (DuplicateBrep 실패). "
                  u"곡면이 유효한지 확인할 것.")
        return result

    result.positioned_srf = positioned_srf

    # --- Phase C: Surface Extension ---
    extended_srf, ext_method, ext_branch = extend_surface(
        positioned_srf, width, length, component
    )

    result.extended_srf = extended_srf
    result.ext_branch = ext_branch

    # --- Phase D: Height Calculation ---
    pin_heights, clamp_flags, extension_flags = calculate_heights(
        grid_pts, positioned_srf, extended_srf, base_plane,
        min_height, max_height, ext_method,
        branch_out=result.branch_taken
    )

    result.pin_heights = pin_heights
    result.clamp_flags = clamp_flags
    result.extension_flags = extension_flags

    # 클램핑은 "목표 곡면을 재현 못 한다"는 뜻인데 지금까지 캔버스는 초록이었다.
    n_clamped = sum(1 for c in clamp_flags if c)
    if n_clamped > 0:
        add_warning(component,
                    u"핀 {}/{} 개가 행정 한계에 걸렸다. 그 지점은 목표 곡면을 "
                    u"재현하지 못한다. clamp_flags 로 위치를 확인하고, "
                    u"max_height 를 늘리거나 곡면을 완만하게 할 것."
                    .format(n_clamped, total_pins))

    # --- Phase E: 3D Model Transformation ---
    if housing_model is not None or rod_model is not None or top_model is not None:
        housings, rods, tops, pin_tops = transform_models(
            grid_pts, pin_heights, base_plane,
            housing_model, rod_model, top_model,
            rod_base_length, component
        )
        result.housings = housings
        result.rods = rods
        result.tops = tops
        result.pin_tops = pin_tops
    else:
        normal = base_plane.ZAxis
        from transformation import get_housing_height
        hh = get_housing_height(housing_model)
        result.pin_tops = [
            rg.Point3d(pt) + normal * (hh + h)
            for pt, h in zip(grid_pts, pin_heights)
        ]

    # --- 통계 리포트 ---
    result.info = _build_report(
        nx, ny, width, length, opt_info, ext_method,
        pin_heights, clamp_flags, extension_flags, total_pins
    )

    add_remark(component, u"AdaptiveMold v1 계산 완료. 핀 {}개.".format(total_pins))
    return result


def _build_report(nx, ny, width, length, opt_info, ext_method,
                  pin_heights, clamp_flags, extension_flags, total_pins):
    # type: (...) -> str
    """통계 리포트 문자열을 생성합니다."""
    valid_heights = [h for h in pin_heights if h is not None]
    h_min = min(valid_heights) if valid_heights else 0
    h_max = max(valid_heights) if valid_heights else 0
    h_avg = sum(valid_heights) / len(valid_heights) if valid_heights else 0

    n_clamped = sum(1 for c in clamp_flags if c)
    n_panel = sum(1 for e in extension_flags if not e)
    n_extension = sum(1 for e in extension_flags if e)

    lines = [
        "AdaptiveMold v1 Report",
        "=" * 30,
        "Mold:        {:.0f} x {:.0f} mm   Grid: {} x {}  ({} actuators)".format(
            width, length, nx, ny, total_pins),
        "Surface:     optimized via {}".format(opt_info),
        "Extension:   {}".format(ext_method),
        "Coverage:    {} / {} on panel,  {} / {} in extension zone".format(
            n_panel, total_pins, n_extension, total_pins),
        "Heights:     min={:.0f}, max={:.0f}, avg={:.0f} mm".format(h_min, h_max, h_avg),
        "Clamped:     {} / {}".format(n_clamped, total_pins),
    ]

    return "\n".join(lines)


# ──────────────────────────────────────
# GhPython RunScript 래퍼
# ──────────────────────────────────────

def ghpython_run(target_srf, base_plane, width, length, spacing,
                 max_height, min_height, housing_model, rod_model,
                 top_model, rod_base_length, compute, component=None):
    # type: (...) -> tuple
    """GhPython 컴포넌트 RunScript에서 호출할 래퍼 함수.

    Returns:
        (positioned_srf, extended_srf, housings, rods, tops,
         pin_heights, pin_tops, grid_pts, clamp_flags,
         extension_flags, info) 튜플.
    """
    r = run_adaptive_mold(
        target_srf, base_plane, width, length, spacing,
        max_height, min_height, housing_model, rod_model,
        top_model, rod_base_length, compute, component
    )

    return (r.positioned_srf, r.extended_srf, r.housings, r.rods, r.tops,
            r.pin_heights, r.pin_tops, r.grid_pts, r.clamp_flags,
            r.extension_flags, r.info)

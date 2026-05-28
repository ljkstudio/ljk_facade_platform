# 01. core/geometry/adaptive_mold v1 작업지시서

> 마스터 문서: `00_platform_overview.md` 참조
> **참조 소프트웨어**:
> - AdapaTools (Adapa) — fabricability 검증, 패널 메타데이터, 레이저 프로젝션 컨셉
> - StudFinder (STUD-IO) — constraint satisfaction solver 접근 (후속 fabrication 단계에서 활용)

---

## 1. 컨텍스트

플랫폼의 **첫 번째 component**. `core/geometry/`의 핵심을 구성하며, 곡면 메탈 패널 정밀 제작의 시작점.

본 v1은 Adapa의 **AdapaTools** 워크플로우 (CAD → mould 형상 전송, fabricability 검증, 생산 메타데이터)를 메탈 패널 + 자체 adaptive mold 시스템에 맞게 재구성한다. 즉:

| Adapa | 본 프로젝트 |
|---|---|
| 콘크리트/GFRC 패널 중심 | 메탈 패널 중심 |
| 표준 D100 몰드 (2000×3000×900) | 사용자 정의 mold (width×length) |
| 핀 pitch 비공개(추정 100mm+) | 200mm pitch (더 정밀) |
| AdapaTools가 Rhino 6 베이스 | Rhino 8 + 자체 구조 |
| 비공개 라이센스, Rhino 계정 락 | 오픈 아키텍처, 외부 배포 가능 |
| 곡률 한계: R 400mm | 사용자 설정 가능 (메탈 material 의존) |

---

## 2. 책임 (One-Liner)

**입력 곡면을 액추에이터 stroke 범위 안에 들도록 최적 위치로 정렬 → 곡면을 mold 영역 전체로 확장 → 각 액추에이터 높이 산출 → fabricability 검증 → 사용자 3D 모델(housing/rod/top) 변형 + 패널 메타데이터 부여**

---

## 3. 모듈 분해

```
core/geometry/
├── grid.py                # Phase A: 그리드 생성
├── projection.py          # Phase D 일부: ray-cast 투영, 클램핑
├── optimization.py        # Phase B: plane fitting 기반 곡면 최적화
├── extension.py           # Phase C: 곡면 확장 (Surface.Extend + tangent fallback)
├── transformation.py      # Phase F: 3D 모델 인스턴스 변형
├── validation.py          # Phase E: fabricability 검증 ★ NEW (Adapa 참조)
├── panel_metadata.py      # 패널 메타데이터 ★ NEW (Adapa 참조)
└── adaptive_mold.py       # facade

core/shared/
└── types.py               # AdaptiveMoldResult, ActuatorInstance, PanelMetadata, FabricabilityCheck
```

알고리즘 흐름:
```
Phase A: Grid  →  Phase B: Optimize  →  Phase C: Extend  →
Phase D: Heights  →  Phase E: Validate  →  Phase F: Transform
```

---

## 4. 모듈별 상세 명세

### 4.1 `core/shared/types.py`

```python
from dataclasses import dataclass, field
from typing import List, Optional
import Rhino.Geometry as rg


@dataclass
class ActuatorInstance:
    """단일 액추에이터의 3D 모델 인스턴스."""
    housing: rg.Brep
    rod: rg.Brep
    top: rg.Brep
    pin_top: rg.Point3d  # 후속 멤브레인 작업용


@dataclass
class PanelMetadata:
    """
    AdapaTools 스타일 패널 생산 메타데이터.
    캐스팅·접착·고정 단계 작업자가 사용.
    """
    name: str = ""                            # 패널 고유명 (예: "P-A03-014")
    edge_numbering: List[int] = field(default_factory=list)  # 4개 엣지 번호
    mould_side: str = "front"                 # "front" or "back" (어느 면이 몰드 면)
    thickness_mm: float = 0.0
    bracket_positions: List[rg.Point3d] = field(default_factory=list)
    fixture_positions: List[rg.Point3d] = field(default_factory=list)
    laser_projection_lines: List[rg.Curve] = field(default_factory=list)
    notes: str = ""


@dataclass
class FabricabilityCheck:
    """
    AdapaTools 스타일 fabricability 검증 결과.
    is_fabricable이 False면 violation을 해결해야 제작 가능.
    """
    is_fabricable: bool
    violations: List[str]                # 제작 불가 사유
    warnings: List[str]                  # 제작 가능하나 권장 (해상도/정밀도)

    # 세부 측정값 (정보 출력용)
    max_pin_step_mm: float               # 인접 핀 간 최대 단차
    max_pin_step_limit_mm: float
    max_curvature_inv_mm: float          # 1/mm, 측정값
    max_curvature_limit_inv_mm: float
    min_curvature_radius_mm: float       # 환산값 (display용)
    out_of_bounds_pin_count: int
    clamped_pin_count: int


@dataclass
class AdaptiveMoldResult:
    """AdaptiveMold v1 실행 결과."""
    positioned_srf: rg.Brep
    extended_srf: Optional[rg.Brep]
    extension_method: str               # "surface_extend" | "tangent_fallback"
    grid_pts: List[rg.Point3d]
    pin_heights: List[float]
    pin_tops: List[rg.Point3d]
    housings: List[rg.Brep]
    rods: List[rg.Brep]
    tops: List[rg.Brep]
    clamp_flags: List[bool]
    extension_flags: List[bool]
    fabricability: FabricabilityCheck   # ★ NEW
    panel_metadata: Optional[PanelMetadata]  # ★ NEW
    info: str
    warnings: List[str] = field(default_factory=list)
```

### 4.2 `core/geometry/grid.py`

**책임**: base_plane 위에 그리드 포인트 생성.

```python
from typing import List, Tuple
import Rhino.Geometry as rg


def compute_grid_size(width: float, length: float, spacing: float) -> Tuple[int, int]:
    """
    Compute number of grid points in X and Y directions.

    Raises:
        ValueError: If any argument is non-positive.
    """
    if width <= 0 or length <= 0 or spacing <= 0:
        raise ValueError("width, length, spacing must be positive")
    nx = int(width // spacing) + 1
    ny = int(length // spacing) + 1
    return nx, ny


def generate_grid(
    base_plane: rg.Plane,
    nx: int,
    ny: int,
    spacing: float,
) -> List[rg.Point3d]:
    """
    Generate grid points on base_plane.
    Index convention: idx = j * nx + i  (row-major)
    """
    pts = []
    for j in range(ny):
        for i in range(nx):
            pts.append(base_plane.PointAt(i * spacing, j * spacing, 0.0))
    return pts
```

### 4.3 `core/geometry/projection.py`

**책임**: ray-cast 투영, 클램핑.

```python
from typing import List, Optional, Tuple
import Rhino.Geometry as rg


def ray_to_brep_distance(
    pt: rg.Point3d,
    direction: rg.Vector3d,
    target: rg.Brep,
    max_distance: float = 1e6,
) -> Optional[float]:
    """Ray from pt in direction, return distance to target Brep (None if miss)."""
    ray = rg.Ray3d(pt, direction)
    hits = rg.Intersect.Intersection.RayShoot(ray, [target], 1)
    if not hits or len(hits) == 0:
        return None
    d = pt.DistanceTo(hits[0])
    return d if d <= max_distance else None


def project_grid_to_surface(
    grid_pts: List[rg.Point3d],
    direction: rg.Vector3d,
    target: rg.Brep,
) -> List[Optional[float]]:
    return [ray_to_brep_distance(pt, direction, target) for pt in grid_pts]


def clamp_heights(
    heights: List[float],
    min_h: float,
    max_h: float,
) -> Tuple[List[float], List[bool]]:
    """Clamp to [min_h, max_h]. Returns (clamped, flags)."""
    clamped, flags = [], []
    for h in heights:
        if h < min_h:
            clamped.append(min_h); flags.append(True)
        elif h > max_h:
            clamped.append(max_h); flags.append(True)
        else:
            clamped.append(h); flags.append(False)
    return clamped, flags
```

### 4.4 `core/geometry/optimization.py`

**책임**: best-fit plane 산출, 회전 + 평행이동 변환 생성.

```python
from typing import List, Optional, Tuple
import math
import Rhino.Geometry as rg


def _world_to_plane_uv(pt: rg.Point3d, plane: rg.Plane) -> Tuple[float, float]:
    """World point → (u, v) in plane coords (dot products)."""
    vec = pt - plane.Origin
    u = vec * plane.XAxis
    v = vec * plane.YAxis
    return u, v


def fit_plane_to_distances(
    grid_pts: List[rg.Point3d],
    distances: List[Optional[float]],
    base_plane: rg.Plane,
) -> Optional[rg.Plane]:
    """
    Build (u, v, d) in base_plane local space, fit a plane.
    None values are skipped.
    """
    local_pts = []
    for pt, d in zip(grid_pts, distances):
        if d is None:
            continue
        u, v = _world_to_plane_uv(pt, base_plane)
        local_pts.append(rg.Point3d(u, v, d))

    if len(local_pts) < 3:
        return None

    fit_plane = rg.Plane.Unset
    res = rg.Plane.FitPlaneToPoints(local_pts, fit_plane)
    if res != rg.PlaneFitResult.Success:
        return None
    return fit_plane


def build_optimization_transform(
    fit_plane_local: rg.Plane,
    base_plane: rg.Plane,
    pivot_world: rg.Point3d,
    target_center_height: float,
) -> rg.Transform:
    """
    Rigid body transform (in WORLD space):
    1. Rotates surface so its fit_plane becomes parallel to base_plane.
    2. Translates along base_plane.Normal so heights center at target_center_height.
    """
    local_normal = fit_plane_local.Normal
    local_z = rg.Vector3d(0, 0, 1)

    axis_local = rg.Vector3d.CrossProduct(local_normal, local_z)
    angle = rg.Vector3d.VectorAngle(local_normal, local_z)

    if axis_local.Length < 1e-9:
        rot = rg.Transform.Identity
    else:
        axis_world = (
            base_plane.XAxis * axis_local.X
            + base_plane.YAxis * axis_local.Y
            + base_plane.ZAxis * axis_local.Z
        )
        axis_world.Unitize()
        rot = rg.Transform.Rotation(-angle, axis_world, pivot_world)

    current_avg = fit_plane_local.OriginZ
    delta_z = target_center_height - current_avg
    trans = rg.Transform.Translation(base_plane.ZAxis * delta_z)

    return trans * rot
```

### 4.5 `core/geometry/extension.py`

**책임**: 곡면을 mold 영역 전체로 확장.

```python
from typing import Optional, Tuple
import Rhino.Geometry as rg


def extend_surface(
    srf: rg.Brep,
    extend_length: float,
) -> Tuple[Optional[rg.Brep], str]:
    """Try Surface.Extend in 4 UV directions. Falls back if any fails."""
    if srf is None or srf.Surfaces.Count == 0:
        return None, "tangent_fallback"

    nurbs = srf.Surfaces[0].ToNurbsSurface()
    if nurbs is None:
        return None, "tangent_fallback"

    try:
        ext = nurbs
        for edge in [rg.IsoStatus.North, rg.IsoStatus.South,
                     rg.IsoStatus.East, rg.IsoStatus.West]:
            res = ext.Extend(edge, extend_length, True)
            if res is None:
                return None, "tangent_fallback"
            ext = res
        ext_brep = ext.ToBrep()
        return (ext_brep, "surface_extend") if ext_brep else (None, "tangent_fallback")
    except Exception:
        return None, "tangent_fallback"


def tangent_extrapolate_height(
    grid_pt: rg.Point3d,
    surface: rg.Brep,
    base_plane: rg.Plane,
) -> Optional[float]:
    """Closest point on surface → tangent plane → ray intersect → distance."""
    if surface is None or surface.Surfaces.Count == 0:
        return None
    underlying = surface.Surfaces[0]
    success, cp_u, cp_v = underlying.ClosestPoint(grid_pt)
    if not success:
        return None
    closest_pt = underlying.PointAt(cp_u, cp_v)
    normal = underlying.NormalAt(cp_u, cp_v)
    tangent_plane = rg.Plane(closest_pt, normal)

    line = rg.Line(grid_pt, grid_pt + base_plane.ZAxis * 1e6)
    success, t_param = rg.Intersect.Intersection.LinePlane(line, tangent_plane)
    if not success:
        return None
    hit = line.PointAt(t_param)
    return grid_pt.DistanceTo(hit)
```

### 4.6 `core/geometry/transformation.py`

**책임**: housing/rod/top 모델을 위치별로 변형.

```python
import Rhino.Geometry as rg
from ..shared.types import ActuatorInstance


def get_brep_z_height(model: rg.Brep) -> float:
    bbox = model.GetBoundingBox(True)
    return bbox.Max.Z - bbox.Min.Z


def transform_actuator(
    grid_pt: rg.Point3d,
    base_plane: rg.Plane,
    height: float,
    housing_model: rg.Brep,
    rod_model: rg.Brep,
    top_model: rg.Brep,
    rod_base_length: float,
) -> ActuatorInstance:
    """Transform housing/rod/top to grid_pt with rod scaled to height."""
    n = base_plane.ZAxis
    housing_h = get_brep_z_height(housing_model)

    # Housing
    h_target = rg.Plane(grid_pt, n)
    h_xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, h_target)
    housing = housing_model.DuplicateBrep()
    if housing is None:
        raise RuntimeError("Failed to duplicate housing_model")
    housing.Transform(h_xform)

    # Rod (scale Z + place)
    rod_origin = grid_pt + n * housing_h
    rod_target = rg.Plane(rod_origin, n)
    scale_z = height / rod_base_length if rod_base_length > 0 else 1.0
    scale = rg.Transform.Scale(rg.Plane.WorldXY, 1.0, 1.0, scale_z)
    place = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, rod_target)
    rod = rod_model.DuplicateBrep()
    if rod is None:
        raise RuntimeError("Failed to duplicate rod_model")
    rod.Transform(scale)
    rod.Transform(place)

    # Top
    top_origin = rod_origin + n * height
    top_target = rg.Plane(top_origin, n)
    t_xform = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, top_target)
    top = top_model.DuplicateBrep()
    if top is None:
        raise RuntimeError("Failed to duplicate top_model")
    top.Transform(t_xform)

    pin_top = top.GetBoundingBox(True).Center
    return ActuatorInstance(housing=housing, rod=rod, top=top, pin_top=pin_top)
```

### 4.7 `core/geometry/validation.py` ★ NEW (Adapa 참조)

**책임**: AdapaTools 스타일 fabricability 검증.

세 가지 핵심 검사:
1. **인접 핀 간 최대 단차** — 멤브레인이 따라갈 수 있는 경사 한계
2. **곡면 최대 곡률** — Adapa의 R 400mm 한계를 메탈 패널 특성에 맞춰 일반화
3. **out-of-bounds / clamped 핀 수** — 정밀도 저하 경고

```python
from typing import List, Tuple
import Rhino.Geometry as rg
from ..shared.types import FabricabilityCheck


def check_pin_to_pin_step(
    heights: List[float],
    nx: int,
    ny: int,
    max_step_mm: float,
) -> Tuple[float, bool]:
    """
    인접 핀(상하좌우 4방향) 간 최대 단차.
    
    Returns: (max_observed_step, is_within_limit)
    """
    max_step = 0.0
    for j in range(ny):
        for i in range(nx):
            idx = j * nx + i
            h = heights[idx]
            if i + 1 < nx:
                step = abs(h - heights[idx + 1])
                max_step = max(max_step, step)
            if j + 1 < ny:
                step = abs(h - heights[idx + nx])
                max_step = max(max_step, step)
    return max_step, max_step <= max_step_mm


def check_surface_curvature(
    srf: rg.Brep,
    max_curvature_inv_mm: float,
    sample_count: int = 25,
) -> Tuple[float, bool]:
    """
    곡면의 최대 principal curvature.
    
    Args:
        max_curvature_inv_mm: 1/mm. 예: 1/200 = 0.005 → 최소 곡률반경 200mm
        sample_count: 곡면 UV 샘플 수 (sqrt 단위 그리드)
    
    Returns: (max_observed_curvature, is_within_limit)
    """
    if srf is None or srf.Surfaces.Count == 0:
        return 0.0, True

    underlying = srf.Surfaces[0]
    udomain = underlying.Domain(0)
    vdomain = underlying.Domain(1)
    n = max(1, int(sample_count ** 0.5))

    max_curv = 0.0
    for i in range(n):
        for j in range(n):
            t_u = i / (n - 1) if n > 1 else 0.5
            t_v = j / (n - 1) if n > 1 else 0.5
            u = udomain.ParameterAt(t_u)
            v = vdomain.ParameterAt(t_v)
            curv = underlying.CurvatureAt(u, v)
            if curv is None:
                continue
            k1 = abs(curv.Kappa(0))
            k2 = abs(curv.Kappa(1))
            max_curv = max(max_curv, k1, k2)

    return max_curv, max_curv <= max_curvature_inv_mm


def run_fabricability_check(
    heights: List[float],
    nx: int,
    ny: int,
    target_srf: rg.Brep,
    max_pin_step_mm: float,
    max_curvature_inv_mm: float,
    clamp_flags: List[bool],
    extension_flags: List[bool],
) -> FabricabilityCheck:
    """
    전체 fabricability 검증.
    
    예시 사용:
        check = run_fabricability_check(
            heights=pin_heights, nx=6, ny=6,
            target_srf=positioned_srf,
            max_pin_step_mm=50.0,       # 권장: 핀 pitch의 25%
            max_curvature_inv_mm=1/200, # 최소 곡률반경 200mm
            clamp_flags=clamp_flags,
            extension_flags=extension_flags,
        )
        if not check.is_fabricable:
            for v in check.violations:
                gh.AddRuntimeMessage(Warning, v)
    """
    violations: List[str] = []
    warnings: List[str] = []

    # 1. Pin-to-pin step
    max_step, step_ok = check_pin_to_pin_step(heights, nx, ny, max_pin_step_mm)
    if not step_ok:
        violations.append(
            f"Pin-to-pin step {max_step:.1f}mm exceeds limit {max_pin_step_mm:.1f}mm. "
            "Membrane may tear or wrinkle."
        )

    # 2. Curvature
    max_curv, curv_ok = check_surface_curvature(target_srf, max_curvature_inv_mm)
    min_radius = 1.0 / max_curv if max_curv > 1e-9 else float('inf')
    limit_radius = 1.0 / max_curvature_inv_mm if max_curvature_inv_mm > 1e-9 else float('inf')
    if not curv_ok:
        violations.append(
            f"Surface curvature too sharp: min radius {min_radius:.0f}mm "
            f"(limit {limit_radius:.0f}mm). Panel cannot be formed."
        )

    # 3. Clamped pins (warning, not violation)
    n_clamp = sum(clamp_flags)
    if n_clamp > 0:
        warnings.append(
            f"{n_clamp} pin(s) clamped — surface may not be exactly replicated."
        )

    # 4. Extension coverage (warning if mostly extension)
    n_ext = sum(extension_flags)
    if n_ext > len(heights) * 0.5:
        warnings.append(
            f"{n_ext} of {len(heights)} pins are in extension zone — "
            "panel is much smaller than mold."
        )

    return FabricabilityCheck(
        is_fabricable=len(violations) == 0,
        violations=violations,
        warnings=warnings,
        max_pin_step_mm=max_step,
        max_pin_step_limit_mm=max_pin_step_mm,
        max_curvature_inv_mm=max_curv,
        max_curvature_limit_inv_mm=max_curvature_inv_mm,
        min_curvature_radius_mm=min_radius,
        out_of_bounds_pin_count=n_ext,
        clamped_pin_count=n_clamp,
    )
```

**디폴트 한계값** (사용자가 override 가능, 메탈 패널 특성에 맞춰 조정):
- `max_pin_step_mm`: 50mm (200mm pitch의 25%, ≈14° local slope)
- `max_curvature_inv_mm`: 1/200 = 0.005 (최소 반경 200mm)

> 실제 값은 패널 재료(알루미늄/스테인레스/티타늄)·두께·temper에 따라 결정. 추후 `MaterialSpec`과 연동 예정.

### 4.8 `core/geometry/panel_metadata.py` ★ NEW (Adapa 참조)

**책임**: 패널 생산 메타데이터 부여. AdapaTools가 패널 이름, 엣지 넘버링, mould 면, 브래킷 위치, 레이저 프로젝션 라인을 부여하는 방식을 차용.

```python
from typing import List, Optional
import Rhino.Geometry as rg
from ..shared.types import PanelMetadata


def build_metadata(
    panel_name: str,
    thickness_mm: float = 3.0,
    mould_side: str = "front",
) -> PanelMetadata:
    """기본값으로 PanelMetadata 생성."""
    if mould_side not in ("front", "back"):
        raise ValueError(f"mould_side must be 'front' or 'back', got {mould_side}")
    return PanelMetadata(
        name=panel_name,
        thickness_mm=thickness_mm,
        mould_side=mould_side,
    )


def attach_edge_numbering(
    metadata: PanelMetadata,
    panel_srf: rg.Brep,
    convention: str = "length_desc",
) -> PanelMetadata:
    """
    패널의 4(or n)개 엣지에 번호 부여.
    
    Args:
        convention: "length_desc" (길이 내림차순) | "ccw" (반시계 순)
    """
    if panel_srf is None or panel_srf.Edges.Count == 0:
        metadata.edge_numbering = []
        return metadata

    edges = list(panel_srf.Edges)
    if convention == "length_desc":
        edges_sorted = sorted(
            enumerate(edges), key=lambda x: x[1].GetLength(), reverse=True
        )
        metadata.edge_numbering = [orig_idx + 1 for orig_idx, _ in edges_sorted]
    else:  # ccw or default
        metadata.edge_numbering = list(range(1, len(edges) + 1))
    return metadata


def attach_brackets(
    metadata: PanelMetadata,
    bracket_points: List[rg.Point3d],
) -> PanelMetadata:
    """브래킷 위치 부여. Phase 2에서 secondary structure와 자동 동기화 예정."""
    metadata.bracket_positions = list(bracket_points)
    return metadata


def attach_fixtures(
    metadata: PanelMetadata,
    fixture_points: List[rg.Point3d],
) -> PanelMetadata:
    """고정구 위치 부여."""
    metadata.fixture_positions = list(fixture_points)
    return metadata


def attach_laser_projection_lines(
    metadata: PanelMetadata,
    lines: List[rg.Curve],
) -> PanelMetadata:
    """
    AdapaTools 스타일 레이저 프로젝션 라인.
    캐스팅·접착·고정 단계에서 작업자가 패널 위에서 위치 확인.
    Adapa는 레이저 프로젝션 하드웨어 사용. 우리는 v1에서 데이터만 부여.
    """
    metadata.laser_projection_lines = list(lines)
    return metadata
```

> v1에서는 메타데이터 **부여**만 구현. 레이저 프로젝션 하드웨어 연동, 브래킷 자동 산출은 Phase 2 (secondary structure 모듈)에서.

### 4.9 `core/geometry/adaptive_mold.py` (Facade)

```python
"""AdaptiveMold v1 - facade entry point."""
from typing import List, Optional
import Rhino.Geometry as rg

from ..shared.types import (
    AdaptiveMoldResult, ActuatorInstance, PanelMetadata, FabricabilityCheck,
)
from .grid import compute_grid_size, generate_grid
from .projection import project_grid_to_surface, clamp_heights
from .optimization import fit_plane_to_distances, build_optimization_transform
from .extension import extend_surface, tangent_extrapolate_height
from .transformation import transform_actuator
from .validation import run_fabricability_check
from . import panel_metadata as pmeta


def run(
    *,
    width: float,
    length: float,
    spacing: float,
    base_plane: rg.Plane,
    target_srf: rg.Brep,
    housing_model: rg.Brep,
    rod_model: rg.Brep,
    top_model: rg.Brep,
    rod_base_length: float,
    max_height: float = 400.0,
    min_height: float = 0.0,
    # ★ NEW (Adapa-style)
    max_pin_step_mm: float = 50.0,
    max_curvature_inv_mm: float = 1.0 / 200.0,
    panel_name: str = "",
    panel_thickness_mm: float = 3.0,
    mould_side: str = "front",
) -> AdaptiveMoldResult:
    """
    Run AdaptiveMold v1 full pipeline.
    
    Phases:
        A. Grid generation
        B. Surface optimization (rotation + translation)
        C. Surface edge extension
        D. Pin height calculation + clamping
        E. Fabricability validation  ★ NEW
        F. 3D model transformation + metadata  ★ NEW
    """
    warnings: List[str] = []

    # Phase A: Grid
    nx, ny = compute_grid_size(width, length, spacing)
    grid_pts = generate_grid(base_plane, nx, ny, spacing)

    # Phase B: Optimization
    raw_distances = project_grid_to_surface(grid_pts, base_plane.ZAxis, target_srf)
    fit = fit_plane_to_distances(grid_pts, raw_distances, base_plane)
    target_center = (min_height + max_height) / 2.0

    if fit is None:
        warnings.append("Plane fit failed; optimization skipped.")
        positioned_srf = target_srf.DuplicateBrep()
    else:
        pivot = base_plane.PointAt(width / 2.0, length / 2.0, 0.0)
        opt_xform = build_optimization_transform(fit, base_plane, pivot, target_center)
        positioned_srf = target_srf.DuplicateBrep()
        positioned_srf.Transform(opt_xform)

    # Phase C: Extension
    extend_len = max(width, length) * 1.5
    extended_srf, ext_method = extend_surface(positioned_srf, extend_len)
    if extended_srf is None:
        warnings.append("Surface.Extend failed; using tangent fallback.")

    # Phase D: Heights
    target_for_proj = extended_srf if extended_srf else positioned_srf
    distances = project_grid_to_surface(grid_pts, base_plane.ZAxis, target_for_proj)

    extension_flags: List[bool] = []
    raw_heights: List[float] = []
    for pt, d, raw_d in zip(grid_pts, distances, raw_distances):
        if d is not None:
            raw_heights.append(d)
            extension_flags.append(raw_d is None)
        else:
            ext_d = tangent_extrapolate_height(pt, positioned_srf, base_plane)
            if ext_d is None:
                ext_d = target_center
                warnings.append("Tangent extrapolation failed; used center value.")
            raw_heights.append(ext_d)
            extension_flags.append(True)

    pin_heights, clamp_flags = clamp_heights(raw_heights, min_height, max_height)

    # ★ Phase E: Fabricability Check (NEW - Adapa style)
    fabricability = run_fabricability_check(
        heights=pin_heights,
        nx=nx,
        ny=ny,
        target_srf=positioned_srf,
        max_pin_step_mm=max_pin_step_mm,
        max_curvature_inv_mm=max_curvature_inv_mm,
        clamp_flags=clamp_flags,
        extension_flags=extension_flags,
    )
    # violations / warnings를 종합 warnings로 누적
    for v in fabricability.violations:
        warnings.append(f"[FABRICABILITY] {v}")
    for w in fabricability.warnings:
        warnings.append(f"[FABRICABILITY] {w}")

    # Phase F: Transformation + Metadata
    actuators: List[ActuatorInstance] = []
    for pt, h in zip(grid_pts, pin_heights):
        actuators.append(transform_actuator(
            pt, base_plane, h,
            housing_model, rod_model, top_model, rod_base_length,
        ))

    # ★ Panel metadata (NEW)
    metadata = None
    if panel_name:
        metadata = pmeta.build_metadata(
            panel_name=panel_name,
            thickness_mm=panel_thickness_mm,
            mould_side=mould_side,
        )
        metadata = pmeta.attach_edge_numbering(metadata, positioned_srf)

    info = _format_report(
        nx, ny, width, length, spacing,
        pin_heights, clamp_flags, extension_flags, ext_method,
        fabricability, metadata,
    )

    return AdaptiveMoldResult(
        positioned_srf=positioned_srf,
        extended_srf=extended_srf,
        extension_method=ext_method,
        grid_pts=grid_pts,
        pin_heights=pin_heights,
        pin_tops=[a.pin_top for a in actuators],
        housings=[a.housing for a in actuators],
        rods=[a.rod for a in actuators],
        tops=[a.top for a in actuators],
        clamp_flags=clamp_flags,
        extension_flags=extension_flags,
        fabricability=fabricability,
        panel_metadata=metadata,
        info=info,
        warnings=warnings,
    )


def _format_report(nx, ny, width, length, spacing,
                   heights, clamp_flags, ext_flags, ext_method,
                   fab: FabricabilityCheck, meta: Optional[PanelMetadata]) -> str:
    n = len(heights)
    fab_status = "✓ FABRICABLE" if fab.is_fabricable else "✗ NOT FABRICABLE"
    lines = [
        "AdaptiveMold v1 Report",
        "──────────────────────",
        f"Mold:        {width:.0f} × {length:.0f} mm",
        f"Grid:        {nx} × {ny}  ({n} actuators @ {spacing:.0f}mm)",
        f"Heights:     min={min(heights):.0f}, max={max(heights):.0f}, "
        f"avg={sum(heights)/n:.0f} mm",
        f"Clamped:     {sum(clamp_flags)} / {n}",
        f"Extension:   {sum(ext_flags)} / {n} ({ext_method})",
        "",
        f"Fabricability: {fab_status}",
        f"  Max pin step:    {fab.max_pin_step_mm:.1f} / {fab.max_pin_step_limit_mm:.1f} mm",
        f"  Min curve R:     {fab.min_curvature_radius_mm:.0f} mm "
        f"(limit {1.0/fab.max_curvature_limit_inv_mm:.0f})",
    ]
    if meta:
        lines.extend([
            "",
            f"Panel:       {meta.name} ({meta.thickness_mm:.1f}mm, {meta.mould_side})",
            f"Edges:       {meta.edge_numbering}",
        ])
    return "\n".join(lines)
```

---

## 5. `gh_components/adaptive_mold_v1.py`

```python
"""
AdaptiveMold v1 — Grasshopper Python Component

Inputs (set on component):
    [Mold]
    width, length, spacing, max_height, min_height : Number
    base_plane                                      : Plane
    
    [Target]
    target_srf                                      : Brep
    
    [Actuator Model]
    housing_model, rod_model, top_model             : Brep
    rod_base_length                                 : Number
    
    [Fabricability — ★ Adapa-style]
    max_pin_step_mm        (default 50)             : Number
    min_curvature_radius_mm(default 200)            : Number  [→ 1/radius]
    
    [Panel Metadata — ★ Adapa-style]
    panel_name             (default "")             : Text
    panel_thickness_mm     (default 3)              : Number
    mould_side             (default "front")        : Text  ("front"|"back")
    
    compute                                         : Boolean

Outputs:
    [Geometry]
    positioned_srf, extended_srf                    : Brep
    housings, rods, tops                            : List[Brep]
    
    [Pin Data]
    pin_heights, pin_tops, grid_pts
    clamp_flags, extension_flags
    
    [Fabricability — ★ NEW]
    is_fabricable                                   : Boolean
    fab_violations, fab_warnings                    : List[Text]
    
    [Metadata — ★ NEW]
    panel_metadata                                  : (PanelMetadata as Text or custom)
    edge_numbering                                  : List[Number]
    
    info                                            : Text
"""
import sys
PLATFORM_ROOT = r"C:\dev\ljk_facade_platform"
if PLATFORM_ROOT not in sys.path:
    sys.path.insert(0, PLATFORM_ROOT)

import Grasshopper as gh
from core.geometry.adaptive_mold import run

if compute:
    try:
        # min_curvature_radius_mm을 max_curvature_inv_mm으로 변환
        max_curvature_inv_mm = 1.0 / max(min_curvature_radius_mm, 1e-6)

        result = run(
            width=width,
            length=length,
            spacing=spacing,
            base_plane=base_plane,
            target_srf=target_srf,
            housing_model=housing_model,
            rod_model=rod_model,
            top_model=top_model,
            rod_base_length=rod_base_length,
            max_height=max_height,
            min_height=min_height,
            max_pin_step_mm=max_pin_step_mm,
            max_curvature_inv_mm=max_curvature_inv_mm,
            panel_name=panel_name,
            panel_thickness_mm=panel_thickness_mm,
            mould_side=mould_side,
        )

        positioned_srf = result.positioned_srf
        extended_srf = result.extended_srf
        grid_pts = result.grid_pts
        pin_heights = result.pin_heights
        pin_tops = result.pin_tops
        housings = result.housings
        rods = result.rods
        tops = result.tops
        clamp_flags = result.clamp_flags
        extension_flags = result.extension_flags

        # ★ Fabricability
        is_fabricable = result.fabricability.is_fabricable
        fab_violations = result.fabricability.violations
        fab_warnings = result.fabricability.warnings

        # ★ Metadata
        panel_metadata = str(result.panel_metadata) if result.panel_metadata else ""
        edge_numbering = result.panel_metadata.edge_numbering if result.panel_metadata else []

        info = result.info

        # Warnings/Errors to GH
        if not is_fabricable:
            for v in fab_violations:
                ghenv.Component.AddRuntimeMessage(
                    gh.Kernel.GH_RuntimeMessageLevel.Error, v
                )
        for w in result.warnings:
            ghenv.Component.AddRuntimeMessage(
                gh.Kernel.GH_RuntimeMessageLevel.Warning, w
            )

    except Exception as e:
        ghenv.Component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Error, str(e)
        )
```

---

## 6. 테스트 케이스

```python
# tests/geometry/test_adaptive_mold.py

# ── Unit tests ──────────────────────────────────────────────
def test_compute_grid_size():
    assert compute_grid_size(1000, 1000, 200) == (6, 6)

def test_clamp_heights():
    h, f = clamp_heights([50, 250, 500], 0, 400)
    assert h == [50, 250, 400] and f == [False, False, True]

def test_pin_to_pin_step():
    # 6x6 평탄한 핀 + 한 핀만 + 100mm
    heights = [200.0] * 36
    heights[14] = 300.0  # 인덱스 14 (2, 2)
    max_step, ok = check_pin_to_pin_step(heights, 6, 6, max_step_mm=50.0)
    assert max_step == 100.0
    assert not ok

def test_surface_curvature_planar():
    plane_srf = ...  # planar Brep
    max_curv, ok = check_surface_curvature(plane_srf, 1.0/200.0)
    assert max_curv < 1e-6
    assert ok


# ── Integration tests ──────────────────────────────────────
def test_T1_planar_target(cylinder_brep, plane_target):
    """flat 곡면 → 모든 height 동일, fabricable=True."""
    result = run(...)
    assert all(abs(h - 200) < 1.0 for h in result.pin_heights)
    assert result.fabricability.is_fabricable
    assert len(result.fabricability.violations) == 0

def test_T8_too_sharp_curvature():
    """곡률이 너무 sharp한 곡면 → fabricable=False."""
    sharp_srf = ...  # R=100mm 곡면 (한계 200mm)
    result = run(..., min_curvature_radius_mm=200.0)
    assert not result.fabricability.is_fabricable
    assert "curvature too sharp" in " ".join(result.fabricability.violations)

def test_T9_panel_metadata():
    """panel_name 입력 시 metadata 부여."""
    result = run(..., panel_name="P-A03-014", panel_thickness_mm=4.0)
    assert result.panel_metadata is not None
    assert result.panel_metadata.name == "P-A03-014"
    assert result.panel_metadata.thickness_mm == 4.0
    assert len(result.panel_metadata.edge_numbering) > 0
```

전체 시나리오:
| ID | 입력 | 기대 |
|---|---|---|
| T1 | 평면 target | 모든 height 동일, fabricable=True |
| T2 | 반구 target | 중앙 최고, 대칭, fabricable=True (limit 안) |
| T3 | nx=ny=6 검증 | 36개 액추에이터 |
| T4 | 작은 패널 + 큰 mold | extension_flags 일부 True |
| T5 | max_height 초과 곡면 | clamp_flags 발생, warning |
| T6 | base_plane 회전 | 결과도 회전된 상태로 정합 |
| T7 | 11×11 (2m×2m) | 121 액추에이터, 1초 이내 |
| **T8** | 곡률 sharp (R=100mm) | **is_fabricable=False, violation 있음** |
| **T9** | panel_name 부여 | **PanelMetadata 정상 출력** |
| **T10** | pin_step 위반 시나리오 | **violation에 step 명시** |

---

## 7. 구현 순서

| # | 작업 | 검증 |
|---|---|---|
| 1 | `core/shared/types.py` (dataclass 4종) | import 가능 |
| 2 | `core/shared/validation.py` (입력 검증 헬퍼) | 단위 테스트 |
| 3 | `core/geometry/grid.py` | T1 부분 |
| 4 | `core/geometry/projection.py` | T1, T5 |
| 5 | `core/geometry/transformation.py` | uniform height로 36개 |
| 6 | `core/geometry/optimization.py` | 기울어진 평면 → 정렬 |
| 7 | `core/geometry/extension.py` | T4 |
| 8 | **`core/geometry/validation.py`** ★ | **T8, T10** |
| 9 | **`core/geometry/panel_metadata.py`** ★ | **T9** |
| 10 | `core/geometry/adaptive_mold.py` (facade) | 모든 시나리오 통합 |
| 11 | `gh_components/adaptive_mold_v1.py` | GH 실 동작 |
| 12 | `examples/gh_files/adaptive_mold_v1_demo.gh` | 데모 |
| 13 | `docs/components/adaptive_mold_v1.md` | 사용 문서 |

---

## 8. Definition of Done

- [ ] `core/geometry/` 8개 모듈 + `core/shared/types.py` 구현
- [ ] 모든 public 함수: type hint + Google docstring
- [ ] pytest 10개 시나리오 통과 (T8, T9, T10 포함)
- [ ] `gh_components/adaptive_mold_v1.py` Rhino 8에서 동작 확인
- [ ] **`is_fabricable=False`일 때 GH 컴포넌트가 명확히 에러 메시지 출력** ★
- [ ] **PanelMetadata가 `info` 출력 및 별도 outputs에 정상 표시** ★
- [ ] 데모 GH 파일 (dome / saddle / undersized panel / sharp curvature 4종)
- [ ] `docs/components/adaptive_mold_v1.md` (인덱싱·모델링 규약, fabricability 기본값 설명)
- [ ] 6×6 계산 < 1초
- [ ] 모든 RhinoCommon 호출에 None 체크

---

## 9. 후속 컴포넌트와의 인터페이스

| 출력 | 다음 사용처 |
|---|---|
| `positioned_srf` | `02_panel_split`: 패널 분할 입력 |
| `pin_tops` | `02_panel_split`: 멤브레인/캐스팅 표면 정의 |
| `pin_heights` | actuator 제어 신호 (PLC/모터 드라이버) |
| `extended_srf` | `07_scan_registration`: 측정값과 비교 기준 |
| **`panel_metadata`** | **`08_ifc/asset`: 디지털 에셋 메타데이터** |
| **`panel_metadata.laser_projection_lines`** | **`06_survey/total_station`: 현장 프로젝션** |
| **`panel_metadata.bracket_positions`** | **`03_fabrication/profile_bending`: 2차 구조 인터페이스** |
| **`fabricability.is_fabricable`** | **`10_management/order`: 발주 가능 여부 게이트** |

---

## 10. 알려진 한계 / v2 후보

- 멤브레인 시뮬레이션 미포함 (top_centers만 출력)
- 최적화는 least-squares (clamp 발생 시 minimax는 v2)
- 단일 face Brep 가정. 다중 face 곡면은 v2
- 인접 핀 간 단차만 검증, 대각선 단차 미검증 (v2에서 8방향 검사)
- 패널 메타데이터의 **레이저 프로젝션 라인 자동 생성** 미구현 (Phase 1.5 에서 panel_split과 함께)
- **브래킷/고정구 위치 자동 산출** 미구현 (Phase 2에서 secondary structure 모듈과 연동)
- MaterialSpec과 fabricability 한계의 자동 연동 미구현 (현재는 사용자가 수동 입력)

---

## 11. 참조 소프트웨어 — 무엇을 차용했고, 무엇이 다른가

### 11.1 Adapa AdapaTools에서 차용

| AdapaTools 컨셉 | 본 프로젝트 구현 |
|---|---|
| 패널의 fabricability 사전 검증 | `validation.py` (3-check 시스템) |
| 곡률 한계 검사 (Adapa: R 400mm 한계) | `check_surface_curvature` (사용자 설정 가능) |
| 패널 이름, 엣지 넘버링 | `PanelMetadata` |
| Mould 면(front/back) 지정 | `mould_side` 필드 |
| 패널 두께 메타데이터 | `thickness_mm` |
| 레이저 프로젝션 라인 | `laser_projection_lines` (v1은 데이터만, 하드웨어 연동은 v2) |
| 브래킷/고정구 위치 | `bracket_positions`, `fixture_positions` |

### 11.2 Adapa와 다른 점

| 항목 | Adapa | 본 프로젝트 |
|---|---|---|
| 대상 재료 | 콘크리트 / GFRC | 메탈 (알루미늄 / 스테인레스 등) |
| Pin pitch | 비공개 (큼) | 200mm (더 정밀) |
| 곡률 한계 | 고정 R 400mm | 사용자 설정 (재료별) |
| 라이센스 | Rhino 계정 락, 비공개 | 오픈, 외부 배포 가능 |
| 통합 범위 | mould 입력까지 | 전체 외장 시스템 (secondary structure, 측량, 발주까지) |
| 확장성 | Adapa 자체 R&D만 | 컴포넌트형, AI 에이전트 통합 가능 |

### 11.3 StudFinder (STUD-IO)에서 차용 — Phase 2에서 활용

StudFinder의 **Constraint Satisfaction Solver** 패턴이 본 v1에는 직접 사용되지 않지만, 후속 fabrication 모듈(`02_core_fabrication.md` 참조)의 `howick/solver.py`에서 동일한 디자인 철학을 적용한다.

핵심: **"제약(constraint)을 명시적으로 모델링하고, 솔버가 제약을 만족하면서 fabricable한 출력을 산출한다"** 는 패턴. 본 v1의 `validation.py`도 이 패턴의 단순화 버전 (검증만 수행, 해결책 자동 산출은 안 함).

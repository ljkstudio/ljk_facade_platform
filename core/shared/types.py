"""공유 dataclass 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FabricabilityCheck:
    """Fabricability 검증 결과."""

    is_fabricable: bool = True
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    max_pin_step_mm: float = 0.0
    max_pin_step_limit_mm: float = 50.0
    min_curvature_radius_mm: float = 0.0
    out_of_bounds_pin_count: int = 0
    clamped_pin_count: int = 0


@dataclass
class PanelMetadata:
    """패널 생산 메타데이터."""

    name: str = ""
    edge_numbering: List[int] = field(default_factory=list)
    mould_side: str = "front"
    thickness_mm: float = 0.0
    notes: str = ""


@dataclass
class AdaptiveMoldParams:
    """AdaptiveMold v1 입력 파라미터 (JSON 직렬화 가능)."""

    width: float = 1000.0
    length: float = 1000.0
    spacing: float = 200.0
    max_height: float = 400.0
    min_height: float = 0.0
    rod_base_length: float = 300.0
    panel_name: str = ""
    compute: bool = False


@dataclass
class Point3dData:
    """JSON 호환 Point3d."""

    x: float
    y: float
    z: float


@dataclass
class AdaptiveMoldResultData:
    """AdaptiveMold v1 결과 (JSON 직렬화 가능, REST/대시보드용)."""

    nx: int = 0
    ny: int = 0
    grid_pts: List[Point3dData] = field(default_factory=list)
    pin_heights: List[float] = field(default_factory=list)
    pin_tops: List[Point3dData] = field(default_factory=list)
    clamp_flags: List[bool] = field(default_factory=list)
    extension_flags: List[bool] = field(default_factory=list)
    extension_method: str = ""
    optimization_info: str = ""
    info: str = ""
    warnings: List[str] = field(default_factory=list)
    fabricability: Optional[FabricabilityCheck] = None

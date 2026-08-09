"""AdaptiveMold v1 REST request/response models."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from api.schemas.primitives import FabricabilityCheckSchema, Point3dSchema, PlaneSchema


class AdaptiveMoldParamsSchema(BaseModel):
    """AdaptiveMold v1 파라미터 (대시보드 ↔ GH 공유)."""

    width: float = Field(1000.0, gt=0, description="Mold 가로 mm")
    length: float = Field(1000.0, gt=0, description="Mold 세로 mm")
    spacing: float = Field(200.0, gt=0, description="액추에이터 간격 mm")
    max_height: float = Field(400.0, gt=0, description="최대 stroke mm")
    min_height: float = Field(0.0, ge=0, description="최소 stroke mm")
    rod_base_length: float = Field(300.0, gt=0, description="Rod 기준 길이 mm")
    panel_name: str = ""
    base_plane: PlaneSchema = Field(default_factory=PlaneSchema)


class AdaptiveMoldResultSchema(BaseModel):
    """AdaptiveMold v1 계산 결과 (JSON 직렬화)."""

    nx: int = 0
    ny: int = 0
    grid_pts: list[Point3dSchema] = Field(default_factory=list)
    pin_heights: list[float] = Field(default_factory=list)
    pin_tops: list[Point3dSchema] = Field(default_factory=list)
    clamp_flags: list[bool] = Field(default_factory=list)
    extension_flags: list[bool] = Field(default_factory=list)
    extension_method: str = ""
    optimization_info: str = ""
    info: str = ""
    warnings: list[str] = Field(default_factory=list)
    fabricability: Optional[FabricabilityCheckSchema] = None


class SessionStateSchema(BaseModel):
    """GH ↔ Dashboard 공유 세션 상태."""

    project_id: str = "default"
    project_name: str = "Untitled Panel"
    status: Literal["idle", "compute_requested", "synced", "error"] = "idle"
    params: AdaptiveMoldParamsSchema = Field(default_factory=AdaptiveMoldParamsSchema)
    result: Optional[AdaptiveMoldResultSchema] = None
    gh_connected: bool = False
    last_sync_at: Optional[str] = None
    last_gh_ping_at: Optional[str] = None
    compute_requested_at: Optional[str] = None
    error_message: Optional[str] = None


class ParamsUpdateRequest(BaseModel):
    """대시보드에서 파라미터 업데이트."""

    params: AdaptiveMoldParamsSchema


class SyncRequest(BaseModel):
    """GH에서 계산 결과 동기화."""

    result: AdaptiveMoldResultSchema
    params: Optional[AdaptiveMoldParamsSchema] = None


class GhPingRequest(BaseModel):
    """GH Bridge heartbeat."""

    client_id: str = "grasshopper"


class ProjectSummarySchema(BaseModel):
    """프로젝트 보드 항목."""

    project_id: str
    project_name: str
    status: str
    panel_name: str = ""
    actuator_count: int = 0
    last_sync_at: Optional[str] = None

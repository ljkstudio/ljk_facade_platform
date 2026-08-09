"""기본 geometry 타입 JSON schema."""

from pydantic import BaseModel, Field


class Point3dSchema(BaseModel):
    """3D point (mm)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class Vector3dSchema(BaseModel):
    """3D vector."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class PlaneSchema(BaseModel):
    """Rhino Plane equivalent."""

    origin: Point3dSchema = Field(default_factory=Point3dSchema)
    xaxis: Vector3dSchema = Field(default_factory=lambda: Vector3dSchema(x=1.0))
    yaxis: Vector3dSchema = Field(default_factory=lambda: Vector3dSchema(y=1.0))


class FabricabilityCheckSchema(BaseModel):
    """Fabricability 검증 결과."""

    is_fabricable: bool = True
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    max_pin_step_mm: float = 0.0
    max_pin_step_limit_mm: float = 50.0
    min_curvature_radius_mm: float = 0.0
    out_of_bounds_pin_count: int = 0
    clamped_pin_count: int = 0

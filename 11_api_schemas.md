# 11. api/schemas — Pydantic 공유 모델 작업지시서 (outline)

> 마스터 문서: `00_platform_overview.md` 참조
> **이 문서가 듀얼 트랙의 실질적 contract.** Track 1(GH/대시보드)과 Track 2(외부 클라이언트·에이전트)가 공유하는 데이터 모델.

---

## 1. 컨텍스트

플랫폼의 모든 통신은 이 schema를 따른다:

- **core/** 내부의 `@dataclass`들 (예: `AdaptiveMoldResult`)은 Python 객체
- **api/schemas/**의 Pydantic 모델들은 JSON 직렬화 가능한 동등물
- 두 표현 사이의 변환은 명시적 mapper로 수행

이 문서는 **모든 작업지시서보다 우선** 정립되어야 한다. 왜냐하면:
- core 함수가 무엇을 받고 무엇을 반환하는지가 schema에 못 박힘
- 모든 클라이언트(GH, 대시보드, AI 에이전트, 외부 시스템)가 같은 schema 사용
- schema가 바뀌면 모든 곳이 영향 → 처음에 잘 설계

---

## 2. 책임

- core dataclass와 1:1로 매핑되는 Pydantic 모델 정의
- RhinoCommon 타입(Brep, Point3d, Plane 등)의 JSON 직렬화 규약
- 요청/응답 모델 (Request/Response)
- 검증 규칙 (필드 범위, 필수값 등)

---

## 3. 디렉토리 구조

```
api/schemas/
├── __init__.py
├── primitives.py             # Point3d, Vector3d, Plane, Brep_ref 등 기본 타입
├── geometry/
│   ├── __init__.py
│   ├── adaptive_mold.py      # AdaptiveMoldRequest, AdaptiveMoldResponse
│   ├── panel_split.py        # (Phase 1.2)
│   └── ...
├── fabrication/
│   ├── __init__.py
│   ├── profile_bending.py
│   ├── pipe_laser.py
│   └── howick.py
├── survey/
├── ifc/
├── management/
└── ai_assistant.py
```

---

## 4. 핵심 디자인 결정

### 4.1 RhinoCommon 객체의 JSON 표현

| RhinoCommon | JSON 표현 | 비고 |
|---|---|---|
| `Point3d` | `{"x": float, "y": float, "z": float}` | 직관적 |
| `Vector3d` | `{"x": float, "y": float, "z": float}` | Point3d와 구분되는 필드 또는 type tag |
| `Plane` | `{"origin": Point3d, "xaxis": Vector3d, "yaxis": Vector3d}` | normal은 derived |
| `Curve` (NURBS) | `{"degree": int, "control_points": [Point3d], "knots": [float], "weights": [float]}` | NurbsCurve.ToJSON() 활용 가능 |
| `Brep` | `{"format": "3dm_base64", "data": str}` 또는 `{"format": "gltf", "data": str}` | 결정 필요 |
| `Transform` | 4×4 matrix `[[float]*4]*4` | row-major |
| `Mesh` | `{"vertices": [Point3d], "faces": [[int]]}` 또는 glTF | 결정 필요 |

> Brep과 Mesh의 직렬화 방식은 **성능 vs 호환성** trade-off가 큼. Phase 2a 진입 시 측정 후 확정.

### 4.2 ID와 참조

큰 geometry는 매번 JSON으로 주고받기 무겁다. 대안:

- **Server-side cache**: Brep 등을 서버에 저장하고 ID(`brep_uuid`)로 참조
- 요청/응답은 ID만 주고받음
- 별도 endpoint로 geometry GET/PUT

이 패턴이 디지털트윈에 자연스럽게 확장됨 (영속 자산).

### 4.3 core dataclass ↔ Pydantic mapping

```python
# core/shared/types.py
@dataclass
class AdaptiveMoldResult:
    positioned_srf: rg.Brep
    pin_heights: List[float]
    fabricability: FabricabilityCheck
    ...

# api/schemas/geometry/adaptive_mold.py
class AdaptiveMoldResponse(BaseModel):
    positioned_srf_id: str           # ← Brep을 ID로
    pin_heights: List[float]
    fabricability: FabricabilityCheckSchema
    ...
    
    @classmethod
    def from_core(cls, result: AdaptiveMoldResult, geom_cache: GeometryCache) -> "AdaptiveMoldResponse":
        return cls(
            positioned_srf_id=geom_cache.put(result.positioned_srf),
            pin_heights=result.pin_heights,
            fabricability=FabricabilityCheckSchema.from_core(result.fabricability),
            ...
        )
```

mapper는 **명시적 `from_core`/`to_core` 메서드**로 양방향 변환.

---

## 5. 예시 — AdaptiveMold v1

```python
# api/schemas/geometry/adaptive_mold.py
from pydantic import BaseModel, Field
from typing import List, Optional
from ..primitives import PlaneSchema, BrepRef


class AdaptiveMoldRequest(BaseModel):
    """01번 문서의 run() 시그니처를 그대로 반영."""
    width: float = Field(gt=0, description="Mold 가로 길이 mm")
    length: float = Field(gt=0, description="Mold 세로 길이 mm")
    spacing: float = Field(gt=0, description="액추에이터 간격 mm")
    base_plane: PlaneSchema
    target_srf_id: BrepRef           # 미리 업로드된 Brep ID
    housing_model_id: BrepRef
    rod_model_id: BrepRef
    top_model_id: BrepRef
    rod_base_length: float
    max_height: float = 400.0
    min_height: float = 0.0
    # Adapa-style
    max_pin_step_mm: float = 50.0
    min_curvature_radius_mm: float = 200.0
    # Metadata
    panel_name: str = ""
    panel_thickness_mm: float = 3.0
    mould_side: str = Field("front", pattern="^(front|back)$")


class FabricabilityCheckSchema(BaseModel):
    is_fabricable: bool
    violations: List[str]
    warnings: List[str]
    max_pin_step_mm: float
    max_pin_step_limit_mm: float
    min_curvature_radius_mm: float
    out_of_bounds_pin_count: int
    clamped_pin_count: int


class PanelMetadataSchema(BaseModel):
    name: str = ""
    edge_numbering: List[int] = []
    mould_side: str = "front"
    thickness_mm: float = 0.0
    # bracket/fixture는 ID 또는 좌표 — 결정 필요


class AdaptiveMoldResponse(BaseModel):
    positioned_srf_id: BrepRef
    extended_srf_id: Optional[BrepRef]
    extension_method: str
    grid_pts: List["Point3dSchema"]
    pin_heights: List[float]
    pin_tops: List["Point3dSchema"]
    housing_ids: List[BrepRef]
    rod_ids: List[BrepRef]
    top_ids: List[BrepRef]
    clamp_flags: List[bool]
    extension_flags: List[bool]
    fabricability: FabricabilityCheckSchema
    panel_metadata: Optional[PanelMetadataSchema]
    info: str
    warnings: List[str]
```

→ 이 schema가 정해지면:
- GH 컴포넌트의 출력도 같은 구조로 (Pydantic 객체로 변환 가능)
- 대시보드는 이 schema로 데이터 받음
- AI 에이전트도 같은 schema로 호출
- 외부 시스템 통합도 같은 schema 사용

---

## 6. 작업 우선순위

| # | 작업 | 시점 |
|---|---|---|
| 1 | `primitives.py` (Point3d, Vector3d, Plane, BrepRef) | **즉시 (GH 컴포넌트 개발과 평행)** |
| 2 | `geometry/adaptive_mold.py` schema | **01 GH 컴포넌트 개발 직후** |
| 3 | Brep 직렬화 방식 결정 (3dm vs glTF) | Phase 2a 진입 시 |
| 4 | server-side `GeometryCache` 구현 | Phase 2a |
| 5 | 나머지 schema들 | 각 core 모듈 개발과 평행 |

---

## 7. Definition of Done (단계별)

### Phase 1 (지금)
- [ ] `primitives.py` 정의
- [ ] `geometry/adaptive_mold.py` schema 정의 (server-side cache 없이 일단 inline)
- [ ] core dataclass ↔ Pydantic mapper 첫 케이스

### Phase 2a
- [ ] 전체 schema 디렉토리 구조
- [ ] Brep 직렬화 방식 확정
- [ ] `GeometryCache` 동작
- [ ] OpenAPI 문서로 schema 노출

---

## 8. 결정 필요 사항

- **Brep 직렬화**: 3dm base64 (호환성 ↑, 크기 ↑) vs glTF (표준, 크기 ↓, NURBS loss) vs 둘 다 지원
- **참조 ID 방식**: UUID vs 의미 있는 키 (panel name + timestamp)
- **Schema versioning**: v1 → v2 변화 시 backward compatibility 보장 방식

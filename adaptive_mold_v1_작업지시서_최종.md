# AdaptiveMold v1 — Cursor 작업지시서 (최종)

> 이 문서는 Adaptive Mold 프로젝트의 v1 컴포넌트 1개를 개발하기 위한 **단일 작업지시서**입니다.
> 이전 드래프트(`adaptive_mold_작업지시서.md`, `_v2.md`, `_v1_spec.md`)는 **이 문서로 대체**됩니다.

---

## 1. Component Identity

| 항목 | 값 |
|---|---|
| 컴포넌트명 | `AdaptiveMold v1` |
| 닉네임 | `AMv1` |
| 카테고리 / 서브카테고리 | `AdaptiveMold` / `Core` |
| 구현 언어 | Python 3 (Rhino 7+ GhPython, CPython 사용) |
| 외부 라이브러리 | RhinoCommon만. numpy 불사용 (`Plane.FitPlaneToPoints` 활용) |

---

## 2. 컴포넌트의 책임 (One-Liner)

> **입력 곡면을 액추에이터 stroke 범위 안에 들도록 최적 위치로 정렬한 뒤, 곡면을 mold 영역 전체로 확장하고, 각 액추에이터의 높이를 산출하여 사용자의 3D 모델(housing/rod/top)을 변형시킨다.**

---

## 3. Inputs

### 3.1 Mold 치수

| 이름 | 타입 | 기본값 | 단위 | 설명 |
|---|---|---|---|---|
| `width` | float | 1000 | mm | mold 가로 (X) |
| `length` | float | 1000 | mm | mold 세로 (Y) |
| `spacing` | float | 200 | mm | 액추에이터 간격 (X/Y 동일) |
| `base_plane` | Plane | WorldXY | — | mold 베이스 평면 |

> `nx = floor(width / spacing) + 1`, `ny = floor(length / spacing) + 1`
> 디폴트 (1000, 1000, 200) → 6 × 6 = 36개

### 3.2 Actuator 제약

| 이름 | 타입 | 기본값 | 단위 | 설명 |
|---|---|---|---|---|
| `max_height` | float | 400 | mm | rod 최대 stroke |
| `min_height` | float | 0 | mm | rod 최소 stroke |

### 3.3 Target 곡면

| 이름 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target_srf` | Surface / Brep | — | 곡면 패널 (몰드보다 작을 수 있음) |

### 3.4 사용자 3D 모델 (3-Part)

| 이름 | 타입 | 설명 |
|---|---|---|
| `housing_model` | Brep | 본체. **원점에 위치, +Z 방향으로 모델링** |
| `rod_model` | Brep | 로드. **원점에서 +Z 방향, 기본 길이 = `rod_base_length`** |
| `top_model` | Brep | 상단 헤드. **원점에 위치, +Z 방향** |
| `rod_base_length` | float | `rod_model`의 기준 길이 (mm). 이 값 기준으로 Z 스케일 |

> **모델링 규약**: 세 모델 모두 원점(0,0,0)에 +Z 방향으로 모델링되어 있어야 함.
> housing의 높이는 bounding box에서 자동 계산.

### 3.5 실행 제어

| 이름 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `compute` | bool | False | True일 때만 실행 |

---

## 4. Outputs

| 이름 | 타입 | 설명 |
|---|---|---|
| `positioned_srf` | Surface / Brep | 최적화로 회전·이동된 곡면 패널 (원본 크기) |
| `extended_srf` | Surface / Brep | mold 전체 영역으로 확장된 곡면 (시각 확인용) |
| `housings` | Brep[] | 변형된 housing 배열 |
| `rods` | Brep[] | 변형된 rod 배열 (Z 스케일 적용) |
| `tops` | Brep[] | 변형된 top 배열 |
| `pin_heights` | float[] | 각 액추에이터 높이 (길이 = nx × ny) |
| `pin_tops` | Point3d[] | 각 액추에이터 상단 중심점 |
| `grid_pts` | Point3d[] | 베이스 그리드 포인트 |
| `clamp_flags` | bool[] | True = stroke 클램핑 발생 |
| `extension_flags` | bool[] | True = 원본 곡면 외부 (확장 영역) |
| `info` | string | 통계 리포트 |

### `info` 예시
```
AdaptiveMold v1 Report
──────────────────────
Mold:        1000 × 1000 mm   Grid: 6 × 6  (36 actuators)
Surface:     optimized via tilt+translate (Δz=+87mm, tilt=2.3°)
Coverage:    24 / 36 on panel,  12 / 36 in extension zone
Heights:     min=58, max=391, avg=224 mm
Clamped:     0 / 36
Accuracy:    panel max-dev 1.4 mm, avg-dev 0.5 mm
```

---

## 5. 알고리즘 단계

```
[target_srf]
     │
     ▼
┌─────────────────────────────────────┐
│ Phase A: Grid Generation            │
│  - width/length/spacing → grid_pts  │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Phase B: Surface Optimization       │
│  - 각 grid_pt → target_srf 투영     │
│  - in-bounds 핀들만 사용해 plane fit│
│  - 회전 + 평행이동 → positioned_srf │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Phase C: Surface Edge Extension     │
│  - positioned_srf를 mold 전체로 확장│
│  - tangent plane 기반 외삽          │
│  - → extended_srf                   │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Phase D: Height Calculation         │
│  - 모든 grid_pt → extended_srf 투영 │
│  - stroke 클램핑                    │
│  - → pin_heights, clamp_flags       │
└──────────────┬──────────────────────┘
               ▼
┌─────────────────────────────────────┐
│ Phase E: 3D Model Transformation    │
│  - housing/rod/top 복사 후 변형     │
│  - rod는 Z방향 스케일               │
│  - → housings, rods, tops, pin_tops │
└─────────────────────────────────────┘
```

---

## 6. 알고리즘 상세

### Phase A. Grid Generation
```python
nx = int(width // spacing) + 1
ny = int(length // spacing) + 1
grid_pts = []
for j in range(ny):
    for i in range(nx):
        local = Point3d(i * spacing, j * spacing, 0)
        world = base_plane.PointAt(local.X, local.Y, 0)
        grid_pts.append(world)
```
**인덱싱 규약**: `idx = j * nx + i`

---

### Phase B. Surface Optimization (회전 + 평행이동)

**아이디어**: grid_pt들에서 곡면까지의 수직거리를 측정 → 거리들에 대해 **best-fit plane**을 구함 → 그 plane을 수평으로 만드는 회전 + Z 평행이동을 곡면에 적용.

```python
# 1) 각 grid_pt에서 base_plane.Normal 방향으로 ray → target_srf 교점까지 거리
raw_distances = []     # length = nx*ny, None이면 곡면 밖
sample_pts_for_fit = []  # plane fitting에 사용할 (x, y, d) 포인트

for pt in grid_pts:
    ray_origin = pt
    ray_dir = base_plane.ZAxis
    # ray-surface intersection
    result = Rhino.Geometry.Intersect.Intersection.RayShoot(...)
    # 또는 ProjectPointsToBreps
    if intersect_success:
        d = pt.DistanceTo(hit_pt)
        raw_distances.append(d)
        # plane fitting용: 그리드 로컬좌표(x,y)와 거리 d
        local = base_plane.RemapToPlaneSpace(pt)
        sample_pts_for_fit.append(Point3d(local.X, local.Y, d))
    else:
        raw_distances.append(None)

# 2) Best-fit plane (in-bounds 포인트만 사용)
ok, fit_plane = Rhino.Geometry.Plane.FitPlaneToPoints(sample_pts_for_fit)
if not ok or len(sample_pts_for_fit) < 3:
    # fallback: 평행이동만
    fit_plane = Plane.WorldXY
    fit_plane.Origin = Point3d(0, 0, mean(valid distances))

# 3) fit_plane.Normal을 (0,0,1)에 맞추는 회전 산출
target_normal = Vector3d.ZAxis  # plane fitting 공간 기준
current_normal = fit_plane.Normal
rot_axis = Vector3d.CrossProduct(current_normal, target_normal)
rot_angle = Vector3d.VectorAngle(current_normal, target_normal)

# 4) 회전 pivot: 그리드 중심을 base_plane 위에 투영한 점
grid_center_local = Point3d(width/2, length/2, 0)
pivot_world = base_plane.PointAt(grid_center_local.X, grid_center_local.Y, 0)

# 5) world space로 변환된 회전 axis (base_plane 기준이므로 변환 필요)
rot_axis_world = base_plane.PointAt(rot_axis.X, rot_axis.Y, rot_axis.Z) - base_plane.Origin
rot_xform = Transform.Rotation(-rot_angle, rot_axis_world, pivot_world)

# 6) 회전 적용
positioned_srf = target_srf.Duplicate()
positioned_srf.Transform(rot_xform)

# 7) 회전 후 다시 거리 측정 → 평균을 stroke 중앙(target_h)에 맞추는 Δz
new_distances = [project(pt, positioned_srf) for pt in grid_pts if in-bounds]
target_h = (min_height + max_height) / 2
delta_z = target_h - mean(new_distances)
trans_xform = Transform.Translation(base_plane.ZAxis * delta_z)
positioned_srf.Transform(trans_xform)
```

> **주의**: `Plane.FitPlaneToPoints`는 plane fitting 공간 좌표를 받으므로, sample 포인트들은 base_plane의 로컬좌표로 변환해서 넣는다. 회전 axis 변환도 동일.

---

### Phase C. Surface Edge Extension

**목표**: mold 전체 영역(width × length)을 덮도록 곡면을 확장. 확장 영역은 곡면 edge에서의 **접평면(tangent plane)**으로 외삽.

**우선 시도**: Rhino의 `Surface.Extend()` 사용
```python
# UV 양방향으로 충분히 확장
extension_length = max(width, length) * 1.5  # 안전 마진

extended_srf = positioned_srf  # 시작점
try:
    for edge in [IsoStatus.North, South, East, West]:
        extended_srf = extended_srf.Extend(edge, extension_length, True)
        if extended_srf is None:
            raise ValueError(f"Extend failed at {edge}")
except Exception:
    # Fallback: tangent plane 외삽 방식 (Phase D에서 처리)
    extended_srf = positioned_srf  # 그대로 두고, Phase D에서 tangent extrapolate
    extension_method = "tangent_fallback"
```

> Brep 입력의 경우 `Brep.Faces[0].UnderlyingSurface()` 사용 후 다시 Brep으로 wrap.
> Trimmed surface인 경우 underlying surface 기준 확장.

**Fallback: Tangent Plane Extrapolation** (Phase D 안에서 처리)
- 그리드 포인트가 확장 영역에 있으면:
  1. `positioned_srf.ClosestPoint(grid_pt)`로 곡면 edge 위 가장 가까운 점 찾기
  2. 그 점의 접평면 계산: `Plane(point, normal)`
  3. grid_pt에서 base_plane.Normal 방향으로 접평면과의 교점까지 거리 = height
  4. `extension_flags[i] = True` 표시

---

### Phase D. Height Calculation & Clamping
```python
pin_heights = []
clamp_flags = []
extension_flags = []

for pt in grid_pts:
    # 우선 positioned_srf로 투영 (원본 곡면 영역인지 판정)
    inside_panel = ray_intersect(pt, positioned_srf, base_plane.ZAxis)
    
    if inside_panel:
        h = distance(pt, hit_pt_on_positioned_srf)
        extension_flags.append(False)
    else:
        # extended_srf로 투영
        h = ray_intersect(pt, extended_srf, base_plane.ZAxis)
        if h is None:
            # 마지막 fallback: tangent extrapolation
            h = tangent_extrapolate(pt, positioned_srf, base_plane)
        extension_flags.append(True)
    
    # Stroke 클램핑
    if h < min_height:
        h = min_height
        clamped = True
    elif h > max_height:
        h = max_height
        clamped = True
    else:
        clamped = False
    
    pin_heights.append(h)
    clamp_flags.append(clamped)
```

---

### Phase E. 3D Model Transformation

**Housing 높이 자동 계산**
```python
hbox = housing_model.GetBoundingBox(True)
housing_height = hbox.Max.Z - hbox.Min.Z
```

**각 그리드 포인트에 모델 인스턴스 배치**
```python
housings, rods, tops, pin_tops = [], [], [], []

for pt, h in zip(grid_pts, pin_heights):
    # base_plane의 로컬 좌표계 → world
    n = base_plane.ZAxis
    
    # 1) Housing: 단순 이동
    h_xform = Transform.PlaneToPlane(Plane.WorldXY, Plane(pt, n))
    housing_inst = housing_model.DuplicateBrep()
    housing_inst.Transform(h_xform)
    housings.append(housing_inst)
    
    # 2) Rod: 이동 + Z 스케일
    rod_origin = pt + n * housing_height
    rod_plane = Plane(rod_origin, n)
    # 먼저 Z방향 1/rod_base_length 만큼 스케일 (단위화) → 다시 h 배율
    scale_factor = h / rod_base_length
    scale_xform = Transform.Scale(Plane.WorldXY, 1.0, 1.0, scale_factor)
    place_xform = Transform.PlaneToPlane(Plane.WorldXY, rod_plane)
    rod_inst = rod_model.DuplicateBrep()
    rod_inst.Transform(scale_xform)
    rod_inst.Transform(place_xform)
    rods.append(rod_inst)
    
    # 3) Top: rod 상단으로 이동
    top_origin = rod_origin + n * h
    top_plane = Plane(top_origin, n)
    t_xform = Transform.PlaneToPlane(Plane.WorldXY, top_plane)
    top_inst = top_model.DuplicateBrep()
    top_inst.Transform(t_xform)
    tops.append(top_inst)
    
    # 4) Top center (멤브레인 작업용)
    top_bbox = top_inst.GetBoundingBox(True)
    pin_tops.append(top_bbox.Center)
```

> **None 체크 필수**: `DuplicateBrep`, `Transform.PlaneToPlane`, `Brep.Extend` 등 모든 RhinoCommon 호출 결과를 검사하고 실패 시 `gh.AddRuntimeMessage(Warning, ...)` 호출.

---

## 7. 파일 구조

```
adaptive_mold/
├── README.md
├── src/
│   ├── __init__.py
│   ├── adaptive_mold_v1.py       # GhPython 컴포넌트 진입점
│   ├── grid.py                   # Phase A
│   ├── optimization.py           # Phase B (plane fitting, rotation)
│   ├── extension.py              # Phase C (surface extend + tangent fallback)
│   ├── projection.py             # Phase D (ray-cast, clamping)
│   ├── transformation.py         # Phase E (3D 모델 변형)
│   └── utils.py                  # 검증, 메시지, None 체크 헬퍼
├── tests/
│   ├── test_grid.py
│   ├── test_optimization.py
│   ├── test_extension.py
│   ├── test_projection.py
│   └── test_integration.py
└── examples/
    └── adaptive_mold_v1_demo.gh  # 데모 GH 파일
```

---

## 8. 구현 진행 순서

| 단계 | 작업 | 검증 |
|---|---|---|
| 1 | `utils.py` (None 체크, 메시지, 로컬-월드 변환 헬퍼) | 단위 테스트 |
| 2 | `grid.py` — Phase A | `test_grid.py` |
| 3 | `transformation.py` — Phase E (uniform height로 먼저) | 동작 확인: 36개 액추에이터가 동일 높이로 표시 |
| 4 | `projection.py` — Phase D (단순 projection, optimization 없이) | 평면/구 target에 대해 정확한 높이 |
| 5 | `optimization.py` — Phase B (plane fitting 회전) | 기울어진 평면 target → 회전 후 모든 핀 동일 높이 |
| 6 | `extension.py` — Phase C (Surface.Extend 우선, tangent fallback) | 작은 곡면 + 큰 mold → 확장 영역 핀들 정상 |
| 7 | `adaptive_mold_v1.py` 통합 컴포넌트 | 모든 출력 검증 |
| 8 | 데모 GH 파일 + README | E2E 확인 |

---

## 9. 테스트 케이스

| ID | 입력 | 기대 결과 |
|---|---|---|
| T1 | 평면 target (base_plane과 평행), 중앙 | pin_heights 모두 동일, clamp 0 |
| T2 | 기울어진 평면 (10°) | optimization 후 모두 동일 높이, extension_flags 일부 True 가능 |
| T3 | 반구 (R=400) 중앙 배치 | 중앙 최고, 대칭, edge는 extension |
| T4 | 곡면이 mold보다 작음 (600×600 곡면 / 1000×1000 mold) | 중앙 24핀은 panel, 외곽 12핀은 extension_flags=True |
| T5 | max_height=200 + 깊은 곡면 | optimization으로 회전, 그래도 clamp 발생 시 clamp_flags 정확히 표시 |
| T6 | rod_base_length=300, height=150 → scale 0.5 | rod가 시각적으로 절반 길이 |
| T7 | base_plane을 회전·이동시킨 상태 | 회전된 평면 기준으로 모든 출력 정렬 |
| T8 | width=length=2000, spacing=200 → 11×11 | 121개 액추에이터 정상 생성, 3초 이내 |

---

## 10. Definition of Done

- [ ] 8개 구현 단계 모두 완료
- [ ] 9번 테스트 케이스 모두 통과
- [ ] 모든 RhinoCommon Brep/Transform 호출에 None 체크 + 실패 시 `gh.AddRuntimeMessage(Warning, ...)` 적용
- [ ] `extended_srf`가 `Surface.Extend()` 성공 시 정상 출력, 실패 시 `tangent_fallback` 모드로 동작하고 info에 명시
- [ ] 데모 GH 파일에서:
  - 곡면 패널을 동적으로 변경하면 액추에이터 형상이 즉시 갱신
  - dome / saddle / 평면 / 트림된 곡면 4종 시연
- [ ] README에 인덱싱 규약(`idx = j*nx + i`), 모델링 규약(원점+Z), I/O 표, 알고리즘 5단계 다이어그램, 스크린샷 포함
- [ ] 6×6 그리드 계산 시간 < 1초 측정 결과 기록

---

## 11. 코딩 표준

- PEP 8, 타입 힌트
- 모든 public 함수에 docstring (Args / Returns / Raises 명시)
- 단위는 항상 mm
- 좌표계는 항상 `base_plane` 기준으로 시작, world로 변환할 때 명시적으로 처리
- **금기 사항**: numpy import, silent failure, magic number (모두 상수 또는 입력으로 노출)
- `gh.AddRuntimeMessage` 등급:
  - `Error`: 컴포넌트 동작 불가 (입력 누락, 길이 불일치)
  - `Warning`: 동작은 하지만 결과 신뢰도 낮음 (extension fallback, clamp 다수 발생)
  - `Remark`: 정보성 (optimization 적용량 등)

---

## 12. 후속 작업 (v2 이후, 이번 범위 아님)

- 멤브레인 메쉬 보간 (top_centers를 컨트롤로 사용)
- 멤브레인-원본곡면 편차 컬러 시각화
- L-infinity 최적화 (minimax) — clamp가 발생하는 경우 변형량 최소화
- 액추에이터 헤드를 볼조인트로 교체 옵션
- 시뮬레이션 애니메이션 (시간에 따라 형상 변화)

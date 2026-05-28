# 작업지시서: Adaptive Mold Grasshopper Component 개발

> **For Cursor**: 이 문서는 Rhino/Grasshopper용 Adaptive Mold(가변형 몰드) 컴포넌트 개발 지시서입니다. 각 Phase를 순차적으로 구현하고, 각 단계에서 동작하는 상태를 유지해 주세요.

---

## 1. 프로젝트 컨텍스트

- **프로젝트명**: Adaptive Mold Grasshopper Component
- **목적**: 곡면 패널(GFRC, 콘크리트, 복합재 등) 제작을 위한 가변형 핀 몰드 시스템을 Rhino/Grasshopper 환경에서 디자인·시뮬레이션
- **적용 대상**: 자유곡면 파사드 패널 제작 워크플로우 (예: 하나드림 오큘러스 패널 시스템)
- **참고 시스템**: Adapa Adaptive Mould, NedCam Flexible Mould

### Adaptive Mold이란?
N×M 그리드로 배치된 액추에이터 핀들의 높이를 개별 제어하여, 핀 상단에 덮인 유연한 멤브레인(러버 시트)이 목표 곡면을 근사하도록 만드는 재사용 가능한 몰드 시스템.

---

## 2. 개발 환경 및 제약

| 항목 | 값 |
|---|---|
| Rhino | 7 이상 |
| 언어 | **Python 3 (GhPython)** — RhinoCommon API 사용 |
| 단위 | 밀리미터(mm) |
| 좌표계 | World XY 기준, Base Plane 파라미터로 변환 |
| 외부 의존성 | 표준 라이브러리만, RhinoCommon 외 외부 패키지 금지 |

### 코딩 규칙
- PEP 8 준수, 타입 힌트 사용
- 모든 public 함수에 docstring (입력/출력/예외 명시)
- **RhinoCommon API 반환값은 항상 None/실패 체크 후 사용** (예: `Brep.CreatePipe()`, `Surface.ClosestPoint()` 등 — 이전에 겪었던 패턴)
- 에러는 silently fail 금지, `gh.AddRuntimeMessage()`로 사용자에게 노출

---

## 3. 컴포넌트 I/O 사양

### Inputs

| 이름 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `target_srf` | Surface/Brep | ✓ | 목표 곡면 |
| `base_plane` | Plane | ✓ | 몰드 베이스 평면 (그리드 배치 기준) |
| `u_count` | int | ✓ | U 방향 핀 개수 (기본 10) |
| `v_count` | int | ✓ | V 방향 핀 개수 (기본 10) |
| `spacing` | float | ✓ | 핀 간 간격 mm (기본 100.0) |
| `pin_diameter` | float | - | 핀 직경 mm (기본 50.0) |
| `pin_max_h` | float | - | 핀 최대 높이 mm (기본 500.0) |
| `pin_min_h` | float | - | 핀 최소 높이 mm (기본 0.0) |
| `membrane_res` | int | - | 멤브레인 메쉬 해상도 배율 (기본 4) |
| `compute` | bool | - | True일 때만 계산 실행 (성능 보호) |

### Outputs

| 이름 | 타입 | 설명 |
|---|---|---|
| `pin_tops` | Point3d[] | 핀 상단 중심점 |
| `pin_geo` | Brep[] | 핀 시각화 지오메트리 (실린더) |
| `pin_heights` | float[] | 각 핀 높이 |
| `membrane` | Mesh | 변형된 멤브레인 (목표곡면 근사) |
| `deviation` | float[] | 멤브레인-목표곡면 편차 |
| `max_dev` | float | 최대 편차 |
| `avg_dev` | float | 평균 편차 |
| `info` | string | 통계 요약 (clamped pin 개수, 편차 등) |

---

## 4. 파일 구조

```
adaptive_mold/
├── README.md
├── src/
│   ├── __init__.py
│   ├── component.py          # GhPython 진입점 (인스턴스 메서드 RunScript)
│   ├── grid.py               # 베이스 그리드 생성
│   ├── projection.py         # 목표 곡면으로의 투영 / 높이 산출
│   ├── pin.py                # 핀 지오메트리 생성
│   ├── membrane.py           # 멤브레인 메쉬 보간/시뮬레이션
│   ├── analysis.py           # 편차 계산, 통계
│   └── utils.py              # 공용 유틸 (None 체크, 메시지 등)
├── tests/
│   ├── test_grid.py
│   ├── test_projection.py
│   ├── test_membrane.py
│   └── test_integration.py
├── examples/
│   └── adaptive_mold_demo.gh # 데모 정의
└── docs/
    ├── usage.md
    └── algorithm.md
```

---

## 5. 구현 Phase

각 Phase는 독립적으로 동작·테스트 가능해야 함. Phase 종료 시 commit 단위.

### Phase 1: 베이스 그리드 + 곡면 투영 (MVP)
**목표**: 평면 그리드를 만들고 목표 곡면까지의 수직 거리를 핀 높이로 산출.

구현:
1. `grid.py`
   - `build_grid(base_plane, u_count, v_count, spacing) -> List[Point3d]`
   - base_plane 좌표계의 origin 기준으로 U×V 그리드 생성
2. `projection.py`
   - `project_to_surface(grid_pts, base_plane, target_srf) -> List[float]`
   - 각 그리드 포인트에서 base_plane 법선 방향으로 ray-cast → 곡면과의 교점까지 거리
   - **교점이 없는 핀은 None 반환** (out-of-bounds 표시), 추후 평균값 또는 최소값으로 채움
3. `component.py`에서 위 두 모듈 호출, `pin_tops`, `pin_heights` 출력

검증: 평면 target → 모든 높이 동일. 반구 target → 중앙이 가장 높음.

### Phase 2: 핀 시각화 + 제약 조건
**목표**: 실린더 핀 지오메트리 생성, max/min 높이 클램핑.

구현:
1. `pin.py`
   - `make_pin(base_pt, height, diameter) -> Brep`
   - `Cylinder` → `ToBrep(capBottom=True, capTop=True)`
   - **`Brep.CreateFromCylinder()` 결과 None 체크 필수**
2. `projection.py`에 클램핑 추가
   - height < min → min으로 클램프, clamped_count += 1
   - height > max → max로 클램프, clamped_count += 1
3. `info` 출력에 clamped 개수 포함

검증: 제약을 벗어나는 목표 곡면 입력 시 클램핑 메시지 출력.

### Phase 3: 멤브레인 메쉬 (선형 보간)
**목표**: 핀 상단점들 사이를 보간한 멤브레인 메쉬 생성.

구현:
1. `membrane.py`
   - `interpolate_membrane(pin_tops, u_count, v_count, membrane_res) -> Mesh`
   - 핀 상단점을 컨트롤로 사용, NURBS 표면 → 메쉬 (`Surface.CreateFromPoints` 또는 `NurbsSurface.CreateThroughPoints`)
   - 결과 표면을 `membrane_res` 배율로 mesh
2. `analysis.py`
   - `compute_deviation(membrane_mesh, target_srf) -> Tuple[List[float], float, float]`
   - 메쉬 정점마다 target_srf로 closest point → 거리

검증: 부드러운 곡면에서 편차 < spacing/10 수준.

### Phase 4: 멤브레인 정밀도 개선 (옵션)
**목표**: 멤브레인의 물리적 거동을 더 사실적으로.

옵션 A: Catmull-Clark / Loop subdivision으로 스무딩
옵션 B: Kangaroo 스타일 spring-mass 시뮬레이션 (각 핀 상단을 anchor로, 멤브레인 정점 사이를 spring으로 연결, 평형점까지 iteration)

> Phase 4는 시간이 남으면 진행. Phase 3로도 산출물 요건 충족.

### Phase 5: 시각화 + 통계
**목표**: 사용자 경험 개선.

- 편차에 따른 컬러 그라디언트 메쉬 (선택 출력)
- `info` 문자열 포맷:
  ```
  Adaptive Mold Report
  ────────────────────
  Pins: 100 (10×10)
  Clamped: 3 (max), 0 (min)
  Max deviation: 2.34 mm
  Avg deviation: 0.87 mm
  Coverage: 97% (3 pins out of range)
  ```

---

## 6. 핵심 알고리즘 의사코드

```python
def run_adaptive_mold(target_srf, base_plane, u_count, v_count, spacing,
                     pin_diameter, pin_max_h, pin_min_h, membrane_res):
    # 1. 그리드 생성
    grid_pts = build_grid(base_plane, u_count, v_count, spacing)

    # 2. 목표곡면 투영 → 높이
    raw_heights = project_to_surface(grid_pts, base_plane, target_srf)

    # 3. 제약 클램핑
    heights, clamp_info = clamp_heights(raw_heights, pin_min_h, pin_max_h)

    # 4. 핀 상단점 & 지오메트리
    pin_tops = [translate(pt, base_plane.Normal * h) for pt, h in zip(grid_pts, heights)]
    pin_geo  = [make_pin(pt, h, pin_diameter) for pt, h in zip(grid_pts, heights)]

    # 5. 멤브레인
    membrane = interpolate_membrane(pin_tops, u_count, v_count, membrane_res)

    # 6. 편차
    deviations, max_dev, avg_dev = compute_deviation(membrane, target_srf)

    # 7. 통계
    info = format_report(u_count, v_count, clamp_info, max_dev, avg_dev)

    return pin_tops, pin_geo, heights, membrane, deviations, max_dev, avg_dev, info
```

---

## 7. 테스트 케이스 (`tests/`)

| ID | 입력 | 기대 결과 |
|---|---|---|
| T1 | 평면 target | 모든 pin_heights 동일, max_dev ≈ 0 |
| T2 | 반구 (R=500) | 중앙 핀이 최고, 대칭성 유지 |
| T3 | 원통면 | 한 축 방향으로만 높이 변화 |
| T4 | pin_max_h=100 + 깊은 곡면 | clamped count > 0, info에 기록 |
| T5 | target이 base_plane 일부만 덮음 | out-of-range 핀 처리됨, 에러 없음 |
| T6 | u_count=v_count=2 (최소 그리드) | 4핀, 멤브레인 정상 생성 |
| T7 | u_count=v_count=50 (대형 그리드) | 5초 이내 계산 완료 |

---

## 8. Definition of Done

- [ ] Phase 1~3 완료 및 모든 테스트 케이스 통과
- [ ] `examples/adaptive_mold_demo.gh`에서 즉시 실행 가능
- [ ] `README.md`에 설치/사용법, I/O 표, 스크린샷 포함
- [ ] 100×100 그리드 계산 시간 측정 결과 문서화
- [ ] 모든 RhinoCommon API 호출에 None 체크 적용 확인
- [ ] `gh.AddRuntimeMessage()`로 경고/에러 사용자에게 전달
- [ ] 코드 내 TODO 없음, 미구현 함수 없음

---

## 9. 작업 순서 요청

1. 먼저 `README.md`와 파일 구조 스켈레톤 생성
2. Phase 1 구현 → 동작 확인 → commit
3. Phase 2 → 3 순차 진행, 각 Phase마다 테스트 추가
4. Phase 5(시각화/통계) 마무리
5. Phase 4는 시간 여유 있을 때
6. 최종적으로 데모 .gh 파일과 README 정비

---

## 10. 질문 / 결정 필요 사항

작업 중 다음 사항이 모호하면 **임의 결정하지 말고 질문**:
- 핀 그리드가 직교(rectangular)인지 삼각(triangular/hexagonal)인지 → **기본은 직교**
- 멤브레인이 핀 상단점을 정확히 지나는지(보간), 평형 형상인지(시뮬레이션) → **Phase 3은 보간**
- Base plane 외 영역의 핀 처리 → **out-of-range 표시, 평균 높이로 채움**

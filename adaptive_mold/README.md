# AdaptiveMold v1 — Grasshopper Component

곡면 패널(GFRC, 콘크리트, 복합재 등) 제작을 위한 **가변형 핀 몰드 시스템**을 Rhino/Grasshopper 환경에서 디자인·시뮬레이션하는 컴포넌트입니다.

## 개요

입력 곡면을 액추에이터 stroke 범위 안에 들도록 **최적 위치로 정렬**한 뒤, 곡면을 mold 영역 전체로 **확장**하고, 각 액추에이터의 높이를 산출하여 사용자의 3D 모델(housing/rod/top)을 **변형 배치**합니다.

## 설치

1. `adaptive_mold/src/` 폴더를 Rhino가 접근 가능한 경로에 배치합니다.
2. Grasshopper에서 GhPython 컴포넌트를 추가합니다.
3. GhPython 컴포넌트에 아래 코드를 입력합니다:

```python
import sys
sys.path.insert(0, r"C:\...\adaptive_mold\src")  # 실제 경로로 변경
from adaptive_mold_v1 import ghpython_run

(positioned_srf, extended_srf, housings, rods, tops,
 pin_heights, pin_tops, grid_pts, clamp_flags,
 extension_flags, info) = ghpython_run(
    target_srf, base_plane, width, length, spacing,
    max_height, min_height, housing_model, rod_model,
    top_model, rod_base_length, compute, ghenv.Component)
```

## 알고리즘 5단계

```
[target_srf]
     │
     ▼
Phase A: Grid Generation         width/length/spacing → grid_pts
     │
     ▼
Phase B: Surface Optimization    plane fitting → 회전 + Z이동 → positioned_srf
     │
     ▼
Phase C: Surface Extension       Surface.Extend / tangent fallback → extended_srf
     │
     ▼
Phase D: Height Calculation       ray-cast + clamping → pin_heights
     │
     ▼
Phase E: 3D Model Transform      housing/rod/top 복사·변형 → 배열 출력
```

## Input / Output 사양

### Inputs

| 이름 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `target_srf` | Surface/Brep | - | 목표 곡면 |
| `base_plane` | Plane | WorldXY | 몰드 베이스 평면 |
| `width` | float | 1000 | mold 가로 (mm) |
| `length` | float | 1000 | mold 세로 (mm) |
| `spacing` | float | 200 | 액추에이터 간격 (mm) |
| `max_height` | float | 400 | 최대 stroke (mm) |
| `min_height` | float | 0 | 최소 stroke (mm) |
| `housing_model` | Brep | - | 본체 (원점+Z 모델링) |
| `rod_model` | Brep | - | 로드 (원점+Z 모델링) |
| `top_model` | Brep | - | 상단 헤드 (원점+Z 모델링) |
| `rod_base_length` | float | - | rod 기준 길이 (mm) |
| `compute` | bool | False | True일 때만 실행 |

### Outputs

| 이름 | 타입 | 설명 |
|---|---|---|
| `positioned_srf` | Surface/Brep | 최적화된 곡면 패널 |
| `extended_srf` | Surface/Brep | mold 전체로 확장된 곡면 |
| `housings` | Brep[] | 변형된 housing 배열 |
| `rods` | Brep[] | 변형된 rod 배열 (Z 스케일) |
| `tops` | Brep[] | 변형된 top 배열 |
| `pin_heights` | float[] | 각 액추에이터 높이 |
| `pin_tops` | Point3d[] | 각 액추에이터 상단 중심점 |
| `grid_pts` | Point3d[] | 베이스 그리드 포인트 |
| `clamp_flags` | bool[] | stroke 클램핑 발생 여부 |
| `extension_flags` | bool[] | 원본 곡면 외부(확장 영역) 여부 |
| `info` | string | 통계 리포트 |

### 인덱싱 규약

`idx = j * nx + i` (row-major, j=Y방향, i=X방향)

`nx = floor(width / spacing) + 1`, `ny = floor(length / spacing) + 1`

디폴트 (1000, 1000, 200) → 6 × 6 = 36개

### 3D 모델링 규약

세 모델(housing, rod, top) 모두 **원점(0,0,0)**에 **+Z 방향**으로 모델링되어 있어야 합니다.
- housing 높이는 bounding box에서 자동 계산
- rod는 `rod_base_length` 기준으로 Z 스케일 적용

## 파일 구조

```
adaptive_mold/
├── README.md
├── src/
│   ├── __init__.py
│   ├── adaptive_mold_v1.py       # GhPython 컴포넌트 진입점
│   ├── grid.py                   # Phase A
│   ├── optimization.py           # Phase B
│   ├── extension.py              # Phase C
│   ├── projection.py             # Phase D
│   ├── transformation.py         # Phase E
│   └── utils.py                  # 공용 유틸리티
├── tests/
│   ├── test_grid.py
│   ├── test_optimization.py
│   ├── test_extension.py
│   ├── test_projection.py
│   └── test_integration.py
└── examples/
    └── adaptive_mold_v1_demo.gh
```

## 테스트

Rhino/Grasshopper 환경에서 실행:

```python
import sys
sys.path.insert(0, r"C:\...\adaptive_mold\tests")
from test_integration import run_all
run_all()
```

## 개발 환경

| 항목 | 값 |
|---|---|
| Rhino | 7 이상 |
| 언어 | Python 3 (GhPython, CPython) |
| 단위 | 밀리미터 (mm) |
| 외부 의존성 | RhinoCommon만 (numpy 불사용) |

## 참고 시스템

- [Adapa Adaptive Mould](https://www.adapa.dk/)
- [NedCam Flexible Mould](https://www.nedcam.com/)

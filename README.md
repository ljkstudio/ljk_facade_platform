# LJK Facade Platform

비정형 메탈 패널 외장 시스템을 위한 통합 플랫폼. **곡면을 주면 그것을 만들 수 있는 기계 설정을 뱉는 것**이 이 저장소의 일관된 목표입니다.

현재 구현된 것은 **Adaptive Mold** — 가변형 핀 몰드(다점프레스)의 역산기입니다. 목표 곡면을 넣으면 각 액추에이터가 올라가야 할 높이를 계산합니다.

> 전체 비전과 아키텍처 원칙은 [`00_platform_overview.md`](00_platform_overview.md)를 보세요. 이 README는 **지금 실제로 돌아가는 것**만 다룹니다.

---

## Adaptive Mold — 무엇을 하는가

곡면 패널(GFRC·콘크리트·복합재)을 만들려면 그 곡면 모양의 거푸집이 필요합니다. 패널마다 몰드를 새로 만드는 대신, **높이를 개별 조절하는 핀을 격자로 배열해 하나의 몰드로 여러 곡면을 성형**하는 방식이 있습니다. 문제는 "이 곡면을 만들려면 각 핀을 몇 mm 올려야 하는가"이고, 이 저장소가 그걸 풉니다.

```
목표 곡면
   │
   ├─ A. 그리드 생성        몰드 크기·핀 간격 → 베이스 격자점
   ├─ B. 곡면 정렬          평면 피팅 → 회전 + Z이동으로 stroke 범위 안에 넣음
   ├─ C. 곡면 확장          몰드가 곡면보다 클 때 경계 밖을 접선 연장
   ├─ D. 높이 산출          격자점에서 레이캐스트 → stroke 범위로 클램핑
   └─ E. 3D 모델 배치       housing / rod / top 실물 모델을 변형 배치
   │
   ▼
핀 높이 배열 + 클램핑·확장 플래그 + 시각화 지오메트리
```

기본값(몰드 1000×1000mm, 핀 간격 200mm)에서 **6×6 = 36개** 핀이 나옵니다. 인덱싱은 row-major `idx = j * nx + i`입니다.

**설계상 중요한 두 플래그:**
- `clamp_flags` — 그 핀이 액추에이터 stroke 한계에 걸렸다는 뜻. **참이면 그 지점은 목표 곡면을 재현하지 못합니다.**
- `extension_flags` — 그 핀이 원본 곡면 바깥(확장 영역)에 있다는 뜻. 계산된 높이가 실측이 아니라 외삽입니다.

둘 다 "계산은 됐지만 믿을 수 없다"는 신호이므로 무시하면 안 됩니다.

---

## 저장소 구조

```
├── 00_platform_overview.md      # 마스터 아키텍처 지시서
├── 01_core_geometry_*.md        # 컴포넌트별 지시서 (01 core, 10~12 API/UI)
│
├── adaptive_mold/               # ★ 역산기 본체 (Python, 동작함)
│   ├── src/                     #   grid / optimization / extension / projection / transformation
│   └── tests/                   #   Rhino 안에서 실행 (pytest 아님)
│
├── gh_components/               # Grasshopper 어댑터 + REST 브리지
│   └── gh_scripts/              #   GhPython 컴포넌트에 붙여넣는 RunScript
│
├── api/                         # FastAPI — GH ↔ 대시보드 통신 백본
├── core/                        # 공용 타입·검증 (shared)
├── dashboard/                   # Vite + React + TypeScript
└── tests/api/                   # pytest (API 전용)
```

### 구현 상태

| 영역 | 상태 |
|---|---|
| `adaptive_mold/src` | **동작함** — A~E 5단계 완성, RhinoCommon만 사용(numpy 불필요) |
| `gh_components` | **동작함** — GhPython 컴포넌트 + 대시보드 파라미터 pull |
| `api` | **부분** — `health`, `session`만. geometry 엔드포인트 없음 |
| `core/shared` | **부분** — types, validation |
| `core/geometry` | **빈 스텁** — 00번 문서는 여기 있어야 한다고 하나 실제 코드는 `adaptive_mold/src`에 있음 |
| `dashboard` | **부분** — 핀 그리드 뷰어, 프로젝트 보드 |

---

## 빠른 시작

### 1. Grasshopper에서 역산기 돌리기

Rhino 7 이상. GhPython 컴포넌트에 `gh_components/gh_scripts/AdaptiveMold_v1.py` 내용을 붙여넣고, `platform_path` 입력에 **이 저장소의 로컬 경로**를 넣습니다.

자세한 입출력 사양은 [`adaptive_mold/README.md`](adaptive_mold/README.md), 컴포넌트 배선은 [`gh_components/README.md`](gh_components/README.md)를 보세요.

### 2. API 서버 + 대시보드

```bash
pip install -e ".[dev]"
python -m api.server                      # http://127.0.0.1:8000  (docs: /docs)

cd dashboard && npm install && npm run dev # http://localhost:5173
```

그 다음 GH의 **Bridge** 컴포넌트로 파라미터를 pull하고, **AMv1**에서 `compute=True`로 계산합니다.

### 3. 테스트

```bash
pytest                                    # API 테스트만
```

`adaptive_mold/tests/`는 **pytest로 돌지 않습니다.** RhinoCommon이 필요해서 Rhino 안에서 실행해야 합니다:

```python
import sys; sys.path.insert(0, r"<repo>\adaptive_mold\tests")
from test_integration import run_all
run_all()
```

---

## 규약

- **단위는 항상 mm.** 다른 단위를 쓰면 변수명에 명시 (`length_m`)
- **좌표계는 `base_plane` 기준**에서 시작. world 변환 시 명시
- **RhinoCommon 반환값은 반드시 None 체크** — silent failure 방지의 핵심
- **커밋은 Conventional Commits** (`feat(geometry): ...`, `fix(api): ...`)
- **브랜치**: `main` 안정, `feature/<name>` 기능 개발
- 코드 스타일·에러 처리 등 전체 규약은 [`00_platform_overview.md`](00_platform_overview.md) §5–7

---

## 문서 지도

| 문서 | 내용 |
|---|---|
| [`00_platform_overview.md`](00_platform_overview.md) | 비전, 아키텍처 원칙, 로드맵, 규약 |
| [`01_core_geometry_adaptive_mold_v1.md`](01_core_geometry_adaptive_mold_v1.md) | Adaptive Mold 알고리즘 상세 지시서 |
| [`10_api_rest_server.md`](10_api_rest_server.md) · [`11_api_schemas.md`](11_api_schemas.md) | REST 백본 |
| [`12_dashboard_v1.md`](12_dashboard_v1.md) | 대시보드 |
| [`20_gha_csharp_port.md`](20_gha_csharp_port.md) | **C# `.gha` 플러그인 포팅 계획** |
| [`docs/journal/README.md`](docs/journal/README.md) | 개발 저널 기록 규약 — 다음 개발을 자동 생성하기 위한 재료 |
| [`adaptive_mold/README.md`](adaptive_mold/README.md) | 역산기 입출력 사양 |
| [`gh_components/README.md`](gh_components/README.md) | GH 컴포넌트 설치·배선 |

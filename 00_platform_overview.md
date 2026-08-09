# 00. LJK Facade Platform — 마스터 아키텍처 지시서

> 이 문서는 LJK Studio의 비정형 메탈 패널 외장 시스템 플랫폼의 **마스터 작업지시서**입니다.
> 모든 component별 지시서는 이 문서의 원칙과 구조를 따릅니다.

---

## 1. 비전

LJK Studio는 비정형 메탈 패널 건축 외장 분야의 기술 리더가 되는 것을 목표로 합니다. 본 플랫폼은 그 비전을 디지털로 구현하는 통합 시스템입니다.

### 단계별 비전

| Phase | 영역 | 핵심 내용 |
|---|---|---|
| Phase 1 | **곡면 패널 정밀 제작** | Adaptive Mold, 패널 분할 |
| Phase 2a | **세컨더리 스트럭처 + 패브리케이션** | 각파이프 2차 구조 프레임, 프로파일 밴딩, 파이프 레이저, Howick 경량 프레이밍 |
| Phase 2b | **측량 + 역설계** | 토탈스테이션 + Rhino 통합, 3D 스캔 기반 정합성 검토 |
| Phase 3 | **디지털 에셋 + 운영 관리** | IFC 디지털 에셋, 발주/제작/운반/적재/현장 운영 |
| Phase 4 | **AI 통합 플랫폼** | 컴포넌트 임베디드 AI → 전체 관장 AI 에이전트, 외장 시스템 온톨로지 |

---

## 2. 아키텍처 원칙

### 2.1 Core / Adapter 분리 (가장 중요)
**도메인 로직(core)과 GH UI(gh_components)를 분리한다.**

- `core/` 는 순수 Python 모듈. Rhino/GH 없이도 단위 테스트 가능
- `gh_components/` 는 GH에서 호출되는 얇은 어댑터
- 나중에 .gha (C#) 컴파일이 필요해지면 `core/`는 그대로 두고 어댑터만 교체

### 2.2 단일 책임
각 모듈은 한 가지 책임만. 하나의 파일이 200줄을 넘어가면 분리 검토.

### 2.3 명시적 의존성
- `core/X`는 `core/shared`와 RhinoCommon만 import
- `gh_components`는 `core`만 import
- `api`는 외부 라이브러리 자유

### 2.4 Forward Compatible
초기 코드도 나중의 AI 에이전트, 외부 배포, 다른 회사 사용을 염두에 둔다.

### 2.5 듀얼 트랙 + REST 백본 ★

UI/플랫폼은 두 트랙으로 평행 개발한다:

- **Track 1**: Rhino 내부 작은 대시보드 (B/C 사용자 위한 빠른 가치 검증)
- **Track 2**: 디지털트윈 플랫폼 뼈대 (외부 시스템·AI·실시간 모니터링)

두 트랙은 **REST API**를 공통 contract로 공유한다:

```
[GH Components]  [Dashboard]  [AutoCAD plugin]  [AI Agent]  [...]
       │             │              │              │
       └─────────────┴──────────────┴──────────────┘
                          │
                  ┌───────▼───────┐
                  │  REST API     │ ← Track 1/2 공유 contract
                  │  (FastAPI)    │
                  └───────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │   core/       │
                  └───────────────┘
```

- Phase 1 통신은 **REST + manual refresh** (synchronous request-response)
- Phase 3+에서 실시간 push (WebSocket/SSE) 추가
- 같은 REST endpoint를 모든 클라이언트가 공유 → 재구축 없이 점진 확장

---

## 3. 디렉토리 구조

```
ljk_facade_platform/                  # repo root
├── README.md
├── LICENSE
├── pyproject.toml                    # Python 패키지 메타데이터
├── .gitignore
├── .github/workflows/                # CI (테스트 자동화, 추후)
│
├── core/                             # 순수 도메인 로직
│   ├── __init__.py
│   │
│   ├── shared/                       # 공통 타입, 유틸 (모든 core가 의존)
│   │   ├── __init__.py
│   │   ├── types.py                  # dataclass 정의 (Result, Instance 등)
│   │   ├── validation.py             # 입력 검증 헬퍼
│   │   ├── logging.py                # 통일된 로깅
│   │   └── constants.py              # 허용오차, 기본값
│   │
│   ├── geometry/                     # [Phase 1] 곡면, 그리드, 투영
│   │   ├── __init__.py
│   │   ├── grid.py
│   │   ├── projection.py
│   │   ├── optimization.py
│   │   ├── extension.py
│   │   ├── transformation.py
│   │   ├── panel.py                  # (Phase 1 후반: 패널 분할)
│   │   └── adaptive_mold.py          # facade
│   │
│   ├── fabrication/                  # [Phase 2a]
│   │   ├── __init__.py
│   │   ├── profile_bending.py
│   │   ├── pipe_laser.py
│   │   └── howick.py
│   │
│   ├── survey/                       # [Phase 2b]
│   │   ├── __init__.py
│   │   ├── total_station.py
│   │   ├── scan_registration.py
│   │   └── deviation_check.py
│   │
│   ├── ifc/                          # [Phase 3]
│   │   ├── __init__.py
│   │   └── asset.py
│   │
│   └── management/                   # [Phase 3]
│       ├── __init__.py
│       ├── order.py
│       ├── production.py
│       ├── logistics.py
│       └── field.py
│
├── gh_components/                    # Grasshopper Python 어댑터 (Track 1 클라이언트 #1)
│   ├── adaptive_mold_v1.py
│   └── ...
│
├── api/                              # REST 서버 + 외부 시스템 연동 ★
│   ├── __init__.py
│   ├── server.py                     # FastAPI 진입점 (Rhino plugin이 호스팅)
│   ├── schemas/                      # Pydantic 모델 (Track 1/2 공유 contract)
│   │   ├── __init__.py
│   │   ├── geometry.py               # AdaptiveMoldRequest/Result 등
│   │   ├── fabrication.py
│   │   └── ...
│   ├── routers/                      # endpoint 그룹별
│   │   ├── geometry.py               # /api/geometry/adaptive-mold 등
│   │   ├── fabrication.py
│   │   └── ...
│   ├── ai_assistant.py               # Claude / ChatGPT API wrapper
│   ├── total_station_driver.py       # 하드웨어 연동 (Phase 2b)
│   └── ...
│
├── dashboard/                        # Track 1 대시보드 (REST 클라이언트) ★
│   ├── README.md
│   ├── package.json                  # (UI 기술 미정 — Rhino 8 WebView / 브라우저 / Electron)
│   ├── src/
│   │   ├── views/                    # 프로젝트 보드, 컴포넌트 작업, AI 채팅, ...
│   │   ├── api_client/               # REST 호출 wrapper
│   │   └── ...
│   └── ...
│
├── tests/                            # pytest
│   ├── conftest.py
│   ├── geometry/
│   ├── fabrication/
│   ├── api/                          # REST endpoint 테스트
│   └── ...
│
├── examples/
│   ├── gh_files/                     # *.gh 데모 파일
│   └── notebooks/                    # 알고리즘 검증용
│
└── docs/
    ├── architecture.md
    ├── components/                   # 각 컴포넌트 사용 문서
    └── adr/                          # Architecture Decision Records
```

---

## 4. Core 모듈 별 책임

| 모듈 | 책임 | 의존성 |
|---|---|---|
| `core/shared` | 공통 타입, 검증, 로깅, 상수 | (외부 없음) |
| `core/geometry` | 그리드, 곡면 처리, 최적화, 변환 | shared, RhinoCommon |
| `core/fabrication` | 패브리케이션 장비 G-code/도면 생성 | shared, geometry |
| `core/survey` | 측량 데이터 처리, 역설계, 정합성 | shared, geometry, numpy |
| `core/ifc` | IFC 변환, 디지털 에셋 관리 | shared, geometry, fabrication, ifcopenshell |
| `core/management` | 발주, 제작, 운반, 현장 운영 | shared (외부 DB?) |
| **`api/server`** ★ | **REST API 서버 (Track 1/2 contract)** | **core 전체, FastAPI, Pydantic** |
| **`api/schemas`** ★ | **REST 요청/응답 모델 (Pydantic)** | **(외부 없음 — 순수 데이터 정의)** |
| `api/ai_assistant` | AI API 호출 wrapper (Claude/ChatGPT) | shared, anthropic, openai |
| `api/total_station_driver` | 토탈스테이션 하드웨어 | (제조사 SDK) |
| **`dashboard/`** ★ | **Track 1 대시보드 (REST 클라이언트)** | **REST API 만 (core 직접 import 안 함)** |

---

## 5. 명명 규칙

- **GH 컴포넌트 이름**: `{Domain}{Name}V{Major}` — 예: `AdaptiveMold v1`, `PanelSplit v1`
- **Python 모듈/파일**: snake_case (예: `adaptive_mold.py`)
- **클래스**: PascalCase (예: `AdaptiveMoldResult`)
- **함수/변수**: snake_case
- **상수**: UPPER_SNAKE_CASE

---

## 6. 코딩 표준

- **PEP 8** 준수
- **타입 힌트** 필수 (모든 public 함수)
- **Docstring**: Google style (Args / Returns / Raises)
- **단위**: 항상 mm. 다른 단위 사용 시 변수명에 명시 (`length_m`)
- **좌표계**: 항상 `base_plane` 기준에서 시작, world 변환 시 명시
- **상수**: 매직 넘버 금지 → `core/shared/constants.py` 또는 함수 시그니처
- **None 체크**: 모든 RhinoCommon 반환값 검사 (이건 silent failure 방지의 핵심)
- **에러 처리**:
  - 예측 가능한 실패 → Result 패턴 (dataclass에 success/message)
  - 예측 불가 → 예외, `gh_components`에서 catch → `gh.AddRuntimeMessage`

---

## 7. 테스트 전략

- **단위 테스트**: `core/`의 모든 public 함수, pytest 사용
- **통합 테스트**: `gh_components/`는 실제 Rhino 환경에서 수동 검증
- **회귀 테스트**: 알려진 입출력 쌍 저장, CI에서 자동
- **목표 커버리지**: `core/` 80% 이상

---

## 8. 의존성 관리

```toml
# pyproject.toml
[project]
name = "ljk-facade-platform"
version = "0.1.0"
requires-python = ">=3.9"  # Rhino 8 호환

dependencies = [
    # core/는 외부 의존성 최소화
]

[project.optional-dependencies]
api = ["anthropic>=0.30", "requests"]
survey = ["numpy", "open3d"]
ifc = ["ifcopenshell"]
dev = ["pytest", "pytest-cov", "black", "ruff", "mypy"]
```

---

## 9. Git 전략

- **main**: 안정 릴리스, 태그된 버전만
- **develop**: 통합 브랜치
- **feature/<name>**: 기능 개발 (예: `feature/adaptive-mold-v1`)
- **hotfix/<name>**: 긴급 수정

**커밋 메시지** (Conventional Commits):
```
feat(geometry): adaptive_mold v1 클램핑 추가
fix(survey): 토탈스테이션 좌표 변환 부호 오류
docs: README 설치 가이드 추가
```

**버전**: SemVer (v0.1.0)

---

## 10. 로드맵 (듀얼 트랙)

### Track 1: 가치 검증 (Rhino 내부 도구)

| Phase | 기간 | 산출물 |
|---|---|---|
| **Phase 1.1** | 1–2개월 | `core/geometry` + `core/shared` + `gh_components/adaptive_mold_v1` |
| **Phase 1.2** | +1개월 | `core/geometry/panel_split` |
| **Phase 1.3** | +1개월 | 첫 dashboard (REST 클라이언트, 핵심 화면만) |

### Track 2: 디지털트윈 뼈대 (Track 1과 평행)

| Phase | 기간 | 산출물 |
|---|---|---|
| **Phase 2a** | 2–4개월 | `api/server` (FastAPI) + `api/schemas` (Pydantic 공유 모델) |
| **Phase 2b** | 2–4개월 | `core/fabrication` (profile_bending → pipe_laser → howick) |
| **Phase 2c** | 3–5개월 | `core/survey` (total_station + scan_registration) |
| **Phase 3** | 5–9개월 | `core/ifc`, `api/ai_assistant` (Claude/ChatGPT 통합) |
| **Phase 4** | 9–18개월 | `core/management`, 실시간 push (WebSocket/SSE), AI 에이전트, Yak/food4Rhino 배포, 외부 회사 라이센싱 |

> **두 트랙이 만나는 지점**: `api/server` + `api/schemas`. Phase 2a가 끝나면 Track 1 도구도 REST를 거쳐 동작하도록 점진 이전.

---

## 11. AI 통합 전략

REST API가 백본이므로, AI 통합도 자연스럽게 REST 위에서 이루어진다.

### Phase 3 (임베디드형 AI)
각 컴포넌트가 `api/ai_assistant`를 통해 Claude/ChatGPT 호출.
```python
# 예: core/geometry/adaptive_mold.py 내부 (필요시)
from api.ai_assistant import suggest_panel_split

if user_wants_ai_help:
    suggestion = suggest_panel_split(positioned_srf, constraints)
```

대시보드의 AI 채팅도 같은 `api/ai_assistant`를 호출.

### Phase 4 (에이전트형 AI)
외부 에이전트(Claude Code 등)가 우리 시스템을 **도구로 호출**.

옵션:
- **MCP 서버로 우리 REST API를 노출** — Claude/ChatGPT 등이 우리 endpoint를 표준 MCP 도구로 사용
- 또는 OpenAPI/Tool spec로 노출 — Function calling 형식

→ **REST API + Pydantic schema가 이미 깔려 있으므로 추가 작업 최소화**. core/adapter 분리 + REST 백본의 자산화 지점.

```
Claude / ChatGPT / 자체 에이전트
        │
        │  MCP / Function calling
        ▼
   api/server (REST)
        │
        ▼
       core/
```

---

## 12. 컴포넌트별 지시서 일람

### Core (도메인 로직)

| # | 파일명 | 상태 |
|---|---|---|
| 00 | `00_platform_overview.md` (이 문서) | ✅ |
| 01 | `01_core_geometry_adaptive_mold_v1.md` | ✅ |
| 02 | `02_core_fabrication.md` (profile_bending + pipe_laser + howick) | ✅ |
| 03 | `03_core_geometry_panel_split.md` | 대기 |
| 04 | `04_core_survey.md` (total_station + scan_registration) | 대기 |
| 05 | `05_core_ifc.md` | 대기 |
| 06 | `06_core_management.md` | 대기 |

### UI/API 트랙 (Track 1/2 백본) ★

| # | 파일명 | 상태 |
|---|---|---|
| 10 | `10_api_rest_server.md` (FastAPI + Rhino plugin hosting) | 대기 |
| 11 | `11_api_schemas.md` (Pydantic 공유 모델 = 두 트랙 contract) | 대기 |
| 12 | `12_dashboard_v1.md` (REST 클라이언트) | 대기 |
| 13 | `13_api_ai_assistant.md` (Claude/ChatGPT wrapper) | 대기 |

### 네이티브 플러그인 트랙

| # | 파일명 | 상태 |
|---|---|---|
| 20 | `20_gha_csharp_port.md` (adaptive_mold A~D → C# `.gha`) | 진행 |

§2.1의 "어댑터만 교체"를 실행하는 트랙. `Core`는 RhinoCommon만 참조하고 Grasshopper를 참조하지 않는다.

각 지시서는 본 마스터 문서의 원칙을 따른다.

### 작업 우선순위 (현재)

```
[지금]
  └─ 01 adaptive_mold_v1 ← ★ GH 컴포넌트 개발 시작

[다음 1–2주]
  ├─ core/shared/types.py 완성 (PanelMetadata, FabricabilityCheck, ...)
  └─ 11 api_schemas 초안 (Pydantic 모델 = core dataclass와 1:1 매핑)
       → 이게 정해지면 Track 1/2 양쪽이 동시에 진행 가능

[Phase 1.2~1.3]
  ├─ 10 api_rest_server (FastAPI in Rhino plugin)
  └─ 12 dashboard_v1 (첫 화면들)
```


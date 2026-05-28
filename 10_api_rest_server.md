# 10. api/server — REST API Server 작업지시서 (outline)

> 마스터 문서: `00_platform_overview.md` 참조
> **현재 outline 수준**. 상세 구현 지시는 **Phase 2a 진입 시점**에 확정.
> 그러나 **Pydantic schema (11번 문서)는 GH 컴포넌트 개발과 평행해서 정의되어야 함** — 그게 두 트랙의 contract이기 때문.

---

## 1. 컨텍스트

`api/server`는 Track 1(Rhino 내부 대시보드)과 Track 2(디지털트윈 플랫폼)의 **공통 백본**.

- Rhino plugin 안에서 호스팅 (Python 프로세스 내 FastAPI 서버 실행)
- `core/` 모듈의 함수를 HTTP endpoint로 노출
- 모든 클라이언트가 이 endpoint를 호출 (GH, 대시보드, AutoCAD plugin, AI 에이전트 등)

---

## 2. 책임

- `core/` 함수 호출을 HTTP REST endpoint로 wrapping
- 요청/응답을 Pydantic schema로 검증 (`api/schemas/`)
- 동시 요청 처리 (Rhino single-threaded 특성 고려 → 큐 또는 async)
- 에러를 HTTP 상태코드로 매핑 (4xx/5xx)
- 로깅, 인증 (Phase 4)

---

## 3. 기술 선택

- **FastAPI** (Python, async 지원, Pydantic 통합, OpenAPI 자동 생성)
- Pydantic v2
- Uvicorn (ASGI 서버) — Rhino plugin 안에서 백그라운드 thread로 기동
- 포트: localhost:8000 (디폴트)

---

## 4. 디렉토리 구조

```
api/
├── server.py                 # FastAPI app + uvicorn 부트스트랩
├── lifecycle.py              # Rhino plugin lifecycle hook (start/stop)
├── schemas/                  # Pydantic 모델 → 11번 문서 참조
│   ├── geometry.py
│   ├── fabrication.py
│   └── ...
├── routers/
│   ├── geometry.py           # /api/geometry/adaptive-mold 등
│   ├── fabrication.py        # /api/fabrication/howick 등
│   ├── survey.py
│   ├── ifc.py
│   └── management.py
├── middleware/
│   ├── logging.py
│   └── error_handler.py
└── ai_assistant.py           # AI 호출 wrapper (13번 문서 참조)
```

---

## 5. 핵심 endpoint 예시 (initial)

| Method | Path | Body / Query | Handler |
|---|---|---|---|
| POST | `/api/geometry/adaptive-mold` | `AdaptiveMoldRequest` | `core.geometry.adaptive_mold.run` |
| POST | `/api/fabrication/howick` | `HowickRequest` | `core.fabrication.howick.facade.run` |
| GET | `/api/projects` | — | (Phase 2 이후) |
| POST | `/api/ai/chat` | `AIChatRequest` | `api.ai_assistant.chat` |
| GET | `/api/health` | — | 상태 체크 |

OpenAPI 스펙은 FastAPI가 자동 생성 (`/docs`).

---

## 6. Rhino plugin 안에서 호스팅하는 방식

```python
# rhino_plugin/main.py (의사코드)
import threading
import uvicorn
from api.server import app

class RhinoPluginEntry:
    def __init__(self):
        self.server_thread = None
        self.server = None
    
    def on_load(self):
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(target=self.server.run, daemon=True)
        self.server_thread.start()
    
    def on_unload(self):
        if self.server:
            self.server.should_exit = True
```

> **주의**: RhinoCommon 객체는 메인 스레드에서 다뤄야 안전. 동시 요청은 큐로 직렬화하거나 Rhino main thread로 marshalling 필요. Phase 2a 진입 시 정밀 설계.

---

## 7. core ↔ REST 사이의 변환

`core/`는 RhinoCommon 객체(Brep, Point3d 등)를 직접 다루지만, REST는 JSON만 받음. 변환 레이어 필요:

| core 타입 | REST 타입 (JSON) |
|---|---|
| `Point3d` | `{"x": float, "y": float, "z": float}` |
| `Plane` | `{"origin": Point3d, "xaxis": Vector3d, "yaxis": Vector3d}` |
| `Brep` | base64-encoded 3dm 또는 GLTF (구현 결정 필요) |
| `Curve` | sample points 또는 NURBS 파라미터 |
| `Transform` | 4×4 matrix |

이 변환은 `api/schemas/`에서 Pydantic validator + converter로 처리. **11번 문서가 핵심**.

---

## 8. Definition of Done (Phase 2a 종료 시)

- [ ] FastAPI 서버가 Rhino plugin 안에서 정상 기동
- [ ] `/api/geometry/adaptive-mold` 첫 endpoint 동작
- [ ] OpenAPI 문서 자동 생성 (`/docs`)
- [ ] `gh_components/adaptive_mold_v1`이 REST 경유 호출로 옮겨질 수 있는 경로 확보
- [ ] 대시보드 (Track 1)이 REST 호출로 동일 결과 받음
- [ ] core 함수 ↔ Pydantic schema 변환 레이어 정립

---

## 9. 현재 시점 결정 필요 사항

- **Brep 직렬화 방법**: base64 3dm vs glTF vs sample mesh
- **동시 요청 처리**: 단일 큐 vs Rhino main-thread marshalling
- **인증/권한**: Phase 1은 localhost만, Phase 4에서 토큰 기반
- **State 저장**: in-memory only vs SQLite vs 외부 DB

---

## 10. 11번 문서(api/schemas)와의 관계

`api/server`는 **endpoint 라우팅과 호출 메커니즘**만 다루고, **데이터 모델은 11번 문서**가 전담.

→ **11번 문서를 먼저 (또는 평행해서) 만들어야 한다.** 이게 두 트랙의 진짜 contract이기 때문.

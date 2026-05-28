# 12. dashboard v1 — Track 1 대시보드 작업지시서 (outline)

> 마스터 문서: `00_platform_overview.md` 참조
> **현재 outline 수준**. 상세 구현은 **Phase 1.3 진입 시점**(adaptive_mold v1 + REST 서버 동작 이후)에 확정.

---

## 1. 컨텍스트

Track 1의 가시적 산출물. B(스튜디오 직원) / C(외부 회사) 사용자가 GH 캔버스 없이 도구를 사용하게 해주는 첫 UI.

- REST API 클라이언트 (`api/server`를 호출)
- core/를 직접 import하지 않음 (분리 유지)
- Phase 1에서는 핵심 화면만, 점진적으로 디지털트윈 화면들로 확장

---

## 2. 책임

- B/C 사용자가 곡면 패널 + adaptive mold + 기타 컴포넌트를 시각적으로 조작
- AI 채팅 (사이드바)
- 작업 결과 표시 (시각화 + 통계)
- 프로젝트 단위로 작업 관리

---

## 3. UI 기술 스택 (결정 필요)

후보:

| 옵션 | 장점 | 단점 |
|---|---|---|
| **(A) Rhino 8 WebView panel** (HTML/CSS/JS in Rhino dockable panel) | Rhino 안에 통합, 웹 기술, AI 보조 개발 친화 | Rhino 8 의존, 브라우저 외부 못 씀 |
| **(B) 브라우저 (localhost:8000)** | 어디서든 접근, 모바일/태블릿 가능 | Rhino 창과 분리 |
| **(C) Electron 데스크톱 앱** | 독립 앱 느낌, 배포 polished | 무거움, Rhino와 더 분리됨 |
| **(D) Rhino 8 WebView + 동일 코드를 브라우저에서도** | 둘 다 지원 | 약간의 추가 작업 |

> 권장: **(D)** — 같은 React/Vue/Svelte 앱을 Rhino 8 WebView 패널과 브라우저 양쪽에서 띄움. 모두 REST 호출이므로 클라이언트 코드는 동일.

---

## 4. 첫 버전(v1) 화면

| 화면 | 우선순위 | 내용 |
|---|---|---|
| **프로젝트 보드** | P1 | 진행 중·완료 패널 리스트, 상태 칩 |
| **AdaptiveMold 작업 화면** | P1 | 목표곡면 업로드 → 파라미터 슬라이더 → 결과 미리보기(3D viewer) + fabricability 결과 |
| **AI 채팅 (사이드바)** | P1 | 화면 어디서든 호출 가능 |
| **자료 라이브러리** | P2 | 3D 모델·도면·머신 파일 |
| **Fabrication 작업** | P2 | Howick·profile_bending 입력/출력 |
| **공장 모니터링** | P3 (Phase 4) | 디지털트윈 view (장비 상태, 작업 큐) |

P1만 v1, P2부터는 후속 release.

---

## 5. 디렉토리 구조

```
dashboard/
├── README.md
├── package.json
├── vite.config.ts            # 또는 webpack
├── public/
├── src/
│   ├── main.tsx              # 진입점
│   ├── views/
│   │   ├── ProjectBoard.tsx
│   │   ├── AdaptiveMoldView.tsx
│   │   ├── AIChatSidebar.tsx
│   │   └── ...
│   ├── components/           # 재사용 컴포넌트
│   │   ├── ParameterSlider.tsx
│   │   ├── ThreeViewer.tsx   # three.js 기반 3D viewer
│   │   ├── FabricabilityBadge.tsx
│   │   └── ...
│   ├── api_client/           # REST 호출 wrapper
│   │   ├── client.ts
│   │   ├── geometry.ts       # adaptive_mold 등
│   │   └── ai.ts
│   ├── stores/               # 상태 관리 (Zustand/Pinia/...)
│   └── utils/
├── tests/
└── dist/                     # 빌드 산출물 (gitignore)
```

---

## 6. 3D 뷰어

대시보드에서 곡면·액추에이터·patel을 보려면 3D 뷰어 필요. 옵션:

- **three.js** — 가장 보편, AI 보조 개발 강함
- **babylon.js** — 더 부유한 기능
- **rhino3dm.js** — Rhino 네이티브 3dm 파일 직접 표시 가능 ★

→ 권장: **three.js + rhino3dm.js 조합**. REST API에서 받은 3dm 파일을 rhino3dm.js로 파싱 후 three.js에 렌더.

---

## 7. AI 채팅 통합

```
[Dashboard]
   │
   │ 사용자: "이 곡면으로 adaptive mold 돌려서 결과 보여줘"
   ▼
[REST: POST /api/ai/chat]
   │
   ▼
[api/ai_assistant] — Claude/ChatGPT 호출
   │
   │ AI가 tool calling으로 우리 REST endpoint 호출
   ▼
[REST: POST /api/geometry/adaptive-mold]
   │
   ▼
[core/geometry/adaptive_mold.run()]
   │
   ▼ (결과)
[Dashboard 화면 자동 업데이트 — manual refresh로 OK]
```

→ AI가 도구로 우리 REST를 호출하는 게 자연스럽게 작동 (Phase 4의 에이전트 비전과 직결).

---

## 8. Definition of Done (v1)

- [ ] P1 화면 3개 동작 (ProjectBoard, AdaptiveMold, AIChat)
- [ ] REST API와 통신 (10번 문서 endpoint 호출)
- [ ] 3D 뷰어로 positioned_srf + actuator 시각화
- [ ] fabricability 결과를 시각적으로 표시 (badge, violation 목록)
- [ ] AI 채팅에서 우리 시스템을 도구로 호출 가능
- [ ] Rhino 8 WebView 패널에서 동작 + 브라우저에서도 동작
- [ ] README + 스크린샷

---

## 9. 결정 필요 사항 (Phase 1.3 진입 시)

- UI framework: React / Vue / Svelte / SolidJS
- 상태 관리: Zustand / Pinia / Redux
- 빌드 도구: Vite (권장)
- 디자인 시스템: Tailwind / Mantine / shadcn / 자체
- 인증: Phase 1은 unrestricted localhost, Phase 4에 토큰 기반
- 영속성: Phase 1은 in-memory (새로고침 시 손실 가능), 추후 백엔드에 저장

---

## 10. 우선순위

```
[지금]
   01 adaptive_mold_v1 GH 컴포넌트 개발

[GH 컴포넌트 완성 후]
   11 api_schemas (Pydantic schema 정의)
   10 api_rest_server (FastAPI + Rhino plugin)

[REST 동작 후]
   12 dashboard v1 (이 문서)
```

대시보드는 backend가 정해진 후에 만드는 게 효율적. 지금은 GH 컴포넌트에 집중.

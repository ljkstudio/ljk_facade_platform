---
id: J-003
milestone: M1+
date: 2026-08-11
project: ljk_facade_platform
tags: [phase-b, rotation, rhino-mcp, ironpython, grasshopper, automation]
---

# J-003 · Phase B 회전 결함 + Rhino MCP 연결

> **Phase B의 회전이 기울기를 없애는 대신 정확히 2배로 키우고 있었다.** 진단·수정·검증 완료.
> 그리고 Rhino MCP를 붙여 개발 왕복을 없앴다 — 붙이는 데 함정이 넷이었고 전부 "연결됨으로 보이는데 안 되는" 종류였다.

---

## TRAP-01 회전 부호 — 그리고 부호만 뒤집으면 안 되는 이유 ★★

- **증상:** 10도 기울어진 평면에서 36개 중 18개가 stroke 한계에 걸림. 문서상 의도는 "정렬 후 높이 균일화"인데 정반대.

- **원인:** `optimization.py`의 회전이 `-rot_angle`을 쓴다. 벡터 `a`를 `b`로 돌리려면 축 `a×b` 둘레로 **`+각도`** 만큼 돌려야 한다.

  **더 중요한 두 번째 원인:** `Plane.FitPlaneToPoints`는 **법선 방향(부호)을 보장하지 않는다.** 실측에서 fit 법선이 −Z를 향해 `rot_angle`이 실제 기울기가 아니라 `180 − 기울기`로 나왔다.

  | 입력 기울기 | 계산된 회전각 | 잔여(수정 전) |
  |---|---|---|
  | 5° | **175°** | 10° |
  | 10° | **170°** | 20° |
  | 20° | **160°** | 40° |

  **부호만 뒤집는 수정은 법선이 −Z로 나올 때만 우연히 맞는다.** 다른 입력에서 +Z로 나오면 그때 다시 깨진다.

- **해결:** fit 법선을 **+Z 반구로 정규화**한 뒤 `+rot_angle` 적용. 그러면 회전각이 실제 기울기(5/10/20°)로 나오고 법선 방향과 무관하게 성립한다.

- **재발 조건:** `FitPlaneToPoints`·`ClosestPoint`처럼 **방향을 보장하지 않는 API의 법선을 그대로 회전에 쓸 때.** 법선을 얻으면 기준 방향에 맞춰 정규화하는 것을 기본 동작으로 삼을 것.

- **왜 오래 숨었나:** 대칭 패널(평면·단곡·안장·돔)은 best-fit 평면이 이미 수평이라 `rot_axis` 길이가 0이 되어 **회전 코드를 아예 안 밟는다.** 기울어진 입력만이 이 경로를 지난다. 픽스처 8개 중 T2 하나만 값이 바뀐 것이 그 증거다.

---

## TRAP-02 `rhinomcp`이 `mcp 2.0.0`을 물어온다

- **증상:** `claude mcp list`가 `Failed to connect — Connection closed`. 그 이상 정보 없음.
- **원인:** `rhinomcp 0.3.2`가 `mcp` SDK를 버전 제한 없이 의존한다. `uvx`가 최신 `mcp 2.0.0`을 받아오는데 `mcp.server.fastmcp`는 **1.x에만 있다.**
- **해결:** `uvx --with "mcp<2" rhinomcp`.
- **재발 조건:** MCP 서버가 SDK를 느슨하게 의존하고 SDK가 메이저 업을 했을 때. **`Connection closed`만으로는 절대 못 찾는다 — 서버를 손으로 한 번 실행해야 진짜 traceback이 보인다.**

## TRAP-03 진단 목적 수동 실행이 브리지를 망가뜨린다

- **증상:** 등록은 `Connected`인데 모든 호출이 타임아웃.
- **원인:** TRAP-02를 진단하느라 `uvx rhinomcp`을 **손으로 두 번** 실행했다. 그 연결들이 종료되며 Rhino 브리지 쪽에 **`CLOSE_WAIT` 소켓이 남았다.** rhinomcp README는 "한 번에 서버 하나만"이라고 경고한다.
- **해결:** `Get-NetTCPConnection -LocalPort 1999`로 소켓 상태 확인 → `mcpstop` / `mcpstart`.
- **재발 조건:** 단일 연결만 허용하는 MCP 서버를 진단 목적으로 수동 실행할 때.

## TRAP-04 브리지를 재시작하면 MCP 서버가 재연결하지 않는다

- **증상:** `mcpstop`/`mcpstart` 후에도 계속 타임아웃.
- **원인:** rhinomcp 서버는 **기동 시 한 번 연결하고 그 연결을 유지**한다(`Created new persistent connection`). 브리지가 죽으면 복구를 시도하지 않는다.
- **해결:** **순서가 있다 — 브리지가 먼저, MCP 서버가 나중.** 브리지를 재시작했으면 클라이언트도 재연결(`/mcp`)해야 한다.
- **재발 조건:** 상시. Rhino를 껐다 켜거나 `mcpstart`를 다시 할 때마다.

---

## TRAP-05 GhPython 파라미터에 타입 힌트가 없으면 Guid가 들어온다 ★

- **증상:** `target_srf is invalid.` / `Solution exception: expected Plane, got Guid`
- **원인:** `Param_ScriptVariable`의 기본 힌트가 **`GhDocGuidHint`** 다. Rhino 문서 객체가 지오메트리가 아니라 `Guid`로 넘어온다. 살아 있는 컴포넌트를 검사해보니 **입력 11개 전부** 그 상태였다.
- **해결:** `Grasshopper.Kernel.Parameters.Hints`의 힌트를 명시.
  `GH_BrepHint`, `GH_PlaneHint`, `GH_DoubleHint_CS`, `GH_BooleanHint_CS`, `GH_StringHint_CS`
- **재발 조건:** GhPython 컴포넌트를 **코드로 생성할 때마다.** UI로 만들면 사용자가 힌트를 고르지만 스크립트로 만들면 기본값이 남는다.

## TRAP-06 IronPython 2.7의 비ASCII 처리 두 곳

- **증상 A:** `EncoderFallbackException: 'ascii' codec can't encode character '을'` — 한글을 `print`할 때. 브리지의 stdout이 ascii다.
- **증상 B:** `UnicodeEncodeError` in `json/encoder.py` `py_encode_basestring_ascii` — **unicode로 올려도 실패한다.** IronPython의 stdlib 복사본이 CPython과 달리 무조건 `.decode('utf-8')`을 건다.
- **해결:** A는 stdout을 버리고 로그를 파일로. B는 **JSON에 들어가는 문자열을 ASCII로.** 픽스처의 `note`를 영문으로 바꿨다 — 우회가 아니라 원인 제거.
- **재발 조건:** GhPython/브리지(IronPython 2.7)에서 한글을 출력하거나 JSON으로 쓸 때. **ScriptEditor의 CPython 3에서는 안 난다** — 그래서 엔진에 따라 증상이 갈린다.

---

## DECISION-01 Phase B 회전 방식 확정

- **선택:** fit 법선 +Z 정규화 + `+rot_angle`. `rotation_mode` 전환 스위치는 제거하고 하나만 남김.
- **근거:** 네 갈래가 전부 일치했다.
  1. **수치** — 입력 5/10/20° → 잔여 10/20/40°(수정 전), 0(수정 후)
  2. **의도** — 문서의 "높이 균일화"가 수정안에서만 실현
  3. **형상** — 뷰포트 캡처에서 초록(수정) 핀 상단이 완전 수평, 빨강(기존)은 목표보다 더 가파름
  4. **라이브 GH** — `panel_tilt10`에서 36핀 전부 200.0mm, 클램핑 0, `tilt=10.0deg` 정확 인식
- **기각한 대안:** **부호만 뒤집기** — 법선이 −Z로 나오는 지금 입력에서만 맞는다(TRAP-01).
- **뒤집을 조건:** 없음. 다만 `_measure_distances`가 `DistanceTo`(항상 양수)를 쓰는 **부호 소실**은 별개로 남아 있다(미해결 참조).

## DECISION-02 MCP 서버 대신 브리지에 TCP 직결

- **선택:** `execute_rhinoscript_python_code` 등을 MCP 도구가 아니라 **포트 1999에 직접 JSON**을 보내 호출.
- **근거:** MCP 서버 계층이 TRAP-03/04로 타임아웃인데, **브리지 자체는 정상**임을 직접 프로브로 확인했다. 재시작 왕복을 더 돌리는 것보다 우회가 빨랐다.
- **기각한 대안:** Claude Code 재시작 반복 — 이미 여러 번 했고 매번 사람 손이 든다.
- **뒤집을 조건:** MCP 계층이 안정되면 도구 쪽이 낫다(이미지 반환 등 편의 기능이 있음).

---

## FACT-01 Rhino/GH 자동화 가능 범위 (전부 실제 시험)

| 기능 | 결과 |
|---|---|
| GH 캔버스 객체 열거 | ✅ |
| 컴포넌트 코드 교체 (`comp.Code`) | ✅ |
| 타입 힌트 변경 | ✅ 11개 |
| 컴포넌트 생성 / 삭제 | ✅ |
| 배선 연결 / 해제 (`AddSource`) | ✅ |
| 슬라이더 값 변경 | ✅ |
| 솔루션 재계산 (`ExpireSolution`+`NewSolution`) | ✅ |
| 계산된 출력값 읽기 (`VolatileData`) | ✅ |
| `.gh` 저장 (`GH_DocumentIO.SaveQuiet`) | ✅ |
| Rhino 뷰포트 캡처 (`ViewCapture`) | ✅ |
| **GH 캔버스 이미지 캡처** | ❌ `GenerateHiResImage` 시그니처 미해결 |

- **유효 범위:** Rhino 8.33 + rhinomcp 브리지. 캔버스 배치는 눈으로 못 보므로 사람 확인이 필요하다.

## FACT-02 픽스처 재생성 — 수정이 T2만 건드렸다

| case | 이전 clamp/ext | 이후 clamp/ext |
|---|---|---|
| T2_tilted | **18 / 6** | **0 / 0** |
| 나머지 7개 | 변화 없음 | 변화 없음 |

T2 핀 높이 폭 `214.4 → 0.0`, 가지 `{ray-/panel:30, ray-/ext:6} → {ray+/panel:36}`.
**좋은 수정의 모양이다** — 깨진 것만 고치고 나머지를 건드리지 않았다.

## FACT-03 브리지는 IronPython 2.7

- **측정값:** `print('Rhino', ...)` 출력이 튜플로 나옴 → Python 2 문법. `json`·`open`·stdout 모두 2.7 동작.
- **유효 범위:** rhinomcp 브리지 및 GhPython(`ZuiPythonComponent`). **ScriptEditor의 `#! python 3`은 CPython 3.** 같은 코드가 엔진에 따라 다르게 죽는다(TRAP-06).

---

## PROCEDURE-01 브리지 TCP로 Rhino/GH 조작

- **목적:** MCP 도구 없이 Rhino와 Grasshopper를 스크립트로 조작한다.
- **단계:**
  1. Rhino에서 `mcpstart` (포트 1999 리스닝 확인: `Get-NetTCPConnection -LocalPort 1999`)
  2. 소켓 하나를 열고 `{"type":"execute_rhinoscript_python_code","params":{"code":"..."}}` 전송
  3. **연결 하나로 여러 명령 처리** — 매번 새로 열면 `CLOSE_WAIT`가 쌓인다
  4. 한글 출력 금지(TRAP-06) — 결과는 파일로 남기고 밖에서 읽는다
  5. Grasshopper는 `Grasshopper.Instances.ActiveCanvas.Document`로 접근
- **자동화 후보:** **예.** `scratchpad/rhino_cli.py`가 그 최소 구현이다. 저장소로 승격할 가치가 있다.

---

## 미해결

- **부호 소실.** `_measure_distances`·`_ray_cast_height`가 `DistanceTo`(항상 양수), `_closest_point_height`가 `abs()`를 쓴다. **곡면이 그리드 아래에 있어도 양의 높이가 나온다.** 회전을 고치니 T2에서는 안 드러나지만 구조적 위험은 남아 있다.
- **`closest`·`default` 폴백 가지 미커버** (J-002에서 이월). 픽스처 8개가 여전히 그 둘을 안 탄다.
- **T3 hemisphere `clamp=20/36`** — 반지름 400 구가 stroke를 넘는 물리적 사실인지, 아니면 또 다른 결함인지 미판정.
- **GH 캔버스 이미지 캡처** — `GH_ImageSettings` 시그니처 미해결.
- **엔진 차이** — 픽스처를 IronPython 2.7로 뽑았다. CPython 3 결과와 동일한지 미검증.

---

## 승격 후보

| 항목 | 이유 |
|---|---|
| **TRAP-01 법선 방향 미보장** | RhinoCommon 일반. "방향 보장 안 되는 API의 법선은 정규화하고 쓴다" |
| **TRAP-05 GhPython 타입 힌트** | GhPython을 코드로 생성하면 무조건 만난다 |
| **TRAP-02·03·04 MCP 연결 3종** | 다른 PC·다른 프로젝트에서 Rhino MCP 붙일 때 그대로 재발 |
| **PROCEDURE-01 + `rhino_cli.py`** | Rhino 자동화의 최소 골격 |
| TRAP-06 IronPython 비ASCII | Rhino에서 한글 쓰는 모든 스크립트에 해당 |

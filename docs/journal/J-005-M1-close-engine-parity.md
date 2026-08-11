---
id: J-005
milestone: M1 (마감)
date: 2026-08-12
project: ljk_facade_platform
tags: [fixtures, ironpython, cpython, determinism, runscript, bridge, obsolete]
---

# J-005 · M1 마감 — 엔진 동등성과 절차 자동화

> **정답지는 엔진에 의존하지 않는다.** IronPython 2.7로 뽑은 픽스처와 CPython 3로 재생성한
> 픽스처가 8케이스 전부 값이 동일했다 — 부동소수 한 자리도 안 틀렸다.
> J-003의 마지막 미검증 항목이 닫혔고, 픽스처 재생성에서 GUI 조작이 사라졌다.

---

## FACT-01 픽스처 값은 파이썬 엔진과 무관하다 ★★

- **측정값:** 커밋본(IronPython 2.7 산출) vs 방금 재생성본(CPython 3 산출) —
  `pin_heights`·`clamp_flags`·`extension_flags`·`branch_taken`·`pin_tops`·`grid_pts`,
  **8케이스 6배열 전부 완전 일치.** 허용오차를 쓰지 않은 `==` 비교다.
- **측정 방법:** `git show HEAD:<path>`와 작업트리 파일을 각각 파싱해 값 비교.
  **바이트 비교가 아니라 값 비교여야 한다** — FACT-02 때문에 바이트로는 전부 다르게 나온다.
- **유효 범위:** Rhino 8.33, 같은 PC. 두 엔진 모두 기하 연산을 **같은 RhinoCommon(.NET)** 에
  넘기므로 엔진이 값에 개입할 여지가 없다는 해석과 일치한다. 다른 Rhino 버전은 미검증.
- **닫힌 항목:** J-003 미해결 "엔진 차이 — CPython 3 결과와 동일한지 미검증".

## FACT-02 차이는 직렬화 형태뿐이고, 그게 정답지 품질을 좌우한다 ★

- **측정값:** T1 파일 `8213B → 7836B`.

  | | 키 순서 | 후행 공백 줄 |
  |---|---|---|
  | IronPython 2.7 | `note, meta, expected, input, case, summary` (**무작위**) | **377** |
  | CPython 3 | `case, note, input, expected, summary, meta` (삽입 순서) | 0 |

- **원인:** IronPython 2.7의 dict에는 순서가 없고, Python 2의 `json.dumps(indent=2)`는
  항목 구분자 `", "` 를 **줄 끝에 남긴다.**
- **영향:** 값이 100% 같은데 `git diff`가 **4,759줄** 뜬다. 정답지는 diff가 읽혀야 쓸모가 있다.

## FACT-03 `GhPython Script`는 obsolete지만 IronPython 2.7 엔진은 아니다 ★

- **측정값:** `Grasshopper.Instances.ComponentServer.ObjectProxies` 2,319개 중 스크립트 계열:

  | 컴포넌트 | `Obsolete` | `exposure` | library |
  |---|---|---|---|
  | `GhPython Script` | **True** | hidden | `00000000-…` |
  | `GhPython Script (Legacy)` | **True** | hidden | `00000000-…` |
  | `C# Script` | **True** | hidden | `df133822-…` |
  | `VB Script (Legacy)` | **True** | hidden | `df133822-…` |
  | `Script` | False | **primary** | `066d0a87-…` |
  | `Python 3 Script` | False | secondary | `066d0a87-…` |
  | **`IronPython 2 Script`** | **False** | secondary | `066d0a87-…` |
  | `C# Script` | False | secondary | `066d0a87-…` |

- **해석:** 캔버스의 `OLD` 태그는 **`Obsolete=True`인 컴포넌트 클래스**에 붙는다.
  Rhino 8이 스크립트 컴포넌트를 새 라이브러리(`066d0a87`)로 통합하면서 구형 클래스를 폐기했고,
  전부 `exposure=hidden`이라 팔레트에서 사라져 **기존 정의를 열 때만** 보인다.
  **엔진 폐기가 아니다** — 같은 IronPython 2.7을 돌리는 `IronPython 2 Script`가 `Obsolete=False`다.
- **이 프로젝트에의 함의:** `gh_components/`가 구형 GhPython 클래스에 얹혀 있다.
  `.gha` 포팅은 이 문제를 통째로 없애고, Python으로 남길 Phase E는 새 `Script` 계열로 옮기면 태그가 사라진다.
  **미검증:** 옮겼을 때 `Param_ScriptVariable` 힌트 지정 방식이 같은지 확인하지 않았다.
- **측정 방법:** 브리지에서 프록시 열거, 이름에 `python`/`script`/`c#`/`vb`가 든 것만 출력.

---

## TRAP-01 `/runscript` 명령줄 자동 실행은 따옴표를 빼도 여전히 안 된다

*(J-002 TRAP-04 후속 — 그때 제시한 "경로에 공백이 없으면 따옴표를 빼고 시도할 것"을 실행한 결과)*

- **증상:** Rhino는 정상 기동하는데 **스크립트가 돌지 않는다.** 로그 파일 미생성,
  오류 대화상자도 없음. J-002처럼 "`.py`를 문서로 열려는" 오류조차 안 난다 — **조용한 무반응.**
- **시도한 형태:** 경로에 공백이 없고 내부 따옴표도 없앴다.
  ```
  Rhino.exe /netcore "/runscript=_-RunPythonScript C:\...\dump_fixtures.py _Enter"
  ```
  180초 대기 후에도 무반응. 창 열거로 확인 — `Responding=True`, 보이는 대화상자 없음, 메인 창만 존재.
- **해결:** 우회. **브리지 안에서** 같은 명령을 태우면 정상 완주한다.
  ```python
  Rhino.RhinoApp.RunScript('_-RunPythonScript "<path>"', True)   # → True
  ```
- **재발 조건:** Rhino를 명령줄로 배치 실행하려 할 때. **원인 미확정** — `/runscript` 파싱 문제인지
  `RunPythonScript`의 인자 처리 문제인지 구분하지 못했다. 다만 **Rhino 안에서는 같은 명령이 돌므로
  문제는 명령줄 계층에 있다**는 것까지는 좁혀졌다.

## TRAP-02 IronPython에서 `io.open(...).write(...)`는 close 없이 빈 파일을 남긴다 ★

- **증상:** 브리지로 진단 결과를 파일에 쓰게 했더니 **파일은 생기는데 0바이트.**
  결과를 못 읽어 "명령이 실행되지 않았나" 하고 엉뚱한 곳을 봤다. 실제로는 실행됐다.
- **원인:** CPython은 참조 카운팅으로 임시 파일 객체가 즉시 소멸·flush되지만,
  **IronPython은 .NET GC라 결정적 소멸이 없다.** 한 줄짜리 `io.open(...).write(...)` 관용구가
  CPython에서만 통한다.
- **해결:** `try/finally`로 명시적 `close()`.
- **재발 조건:** 브리지(IronPython)에서 파일로 결과를 남길 때. **CPython 습관을 그대로 옮길 때마다.**
  [[J-002]] TRAP-03(cp949)과 같은 계열 — *밖에서 되던 파일 쓰기가 안에서는 다르게 깨진다.*

---

## DECISION-01 정답지는 CPython 3 산출물을 정본으로 한다

- **선택:** 픽스처를 CPython 3 형식으로 재생성해 커밋하고, 생성 경로도 CPython 3로 고정한다
  (`dump_via_bridge.py`가 `_-RunPythonScript`로 태워 `#! python 3` shebang을 살린다).
- **근거:** 값이 동일함을 확인했으므로(FACT-01) 형태 정규화에 **판정 위험이 없다.**
  반면 키 순서 없는 산출물은 재생성마다 diff가 요동쳐 **M3 대조에서 신호를 잃는다.**
- **기각한 대안:**
  - **구본 유지** — 값은 맞지만 후행 공백 377줄에 키 순서가 매번 달라 diff가 무의미해진다.
  - **`sort_keys=True`로 강제 정렬** — 순서는 안정되지만 `case → note → input → expected`의
    읽기 순서가 알파벳순으로 흐트러진다. 삽입 순서가 이미 결정적이라 얻을 것이 없다.
  - **브리지에서 바로 `exec`(IronPython)** — 절차가 한 단계 짧아지지만 FACT-02의 문제를 매번 재생산한다.
- **뒤집을 조건:** `dump_fixtures.py`가 CPython 3에서만 되는 API를 쓰게 되어 GhPython 경로와 갈라질 때.
  그때는 산출물을 엔진별로 따로 두고 **값 대조만** 유지한다.

---

## PROCEDURE-01 픽스처 재생성 — GUI 조작 없이 *(J-002 PROCEDURE-01 대체)*

- **목적:** Python 파이프라인이 바뀌었을 때 정답지를 다시 뽑는다.
- **단계:**
  1. Rhino 8 실행 (`/netcore`)
  2. 명령창에 `mcpstart` — 포트 1999. **유일하게 남은 수동 단계**
  3. `python adaptive_mold/tools/dump_via_bridge.py`
  4. 출력 끝의 `전 케이스 재현 확인` 확인 — 하나라도 재현 실패면 **거기서 멈춘다**
  5. `git diff plugin/fixtures/` 로 값 변화를 설명할 수 있는지 확인
- **자동화 후보:** 2번만 남았다. 이번에는 `WScript.Shell.AppActivate` + `SendKeys`로 창에 직접
  `mcpstart`를 넣어 성공했으나 **1회뿐이라 미검증으로 둔다** — 재현 확인 후 스크립트에 넣을 것.

---

## 미해결

**이월**

- **부호 소실** — `DistanceTo`/`abs()`로 항상 양수. 곡면이 그리드 아래여도 양의 높이가 나온다.
- **`closest`·`default` 폴백 가지 미커버** — 픽스처 8개가 여전히 그 둘을 안 탄다. M3 대조의 명시된 한계.
- **T3 hemisphere `clamp=20/36`** — 반지름 400 구가 stroke를 넘는 물리적 사실인지 미판정.
- **GH 캔버스 이미지 캡처** — `GH_ImageSettings` 시그니처 미해결.

**신규**

- **`T5_deep_clamp`가 클램핑을 검증하지 않는다.** 핀 높이 36개가 **전부 `100.0`**
  = `(min_height+max_height)/2`, `clamp=0`, `ext=0`.
  `max_height=200`으로 줄여도 **Phase B가 곡면을 stroke 중앙으로 옮기므로** 클램프가 발생하지 않는다.
  이름과 동작이 어긋나고, 현재 **클램핑을 실제로 태우는 케이스는 T3 하나뿐**이다.
  → 케이스를 고칠지(예: Phase B를 우회하는 입력) 이름을 바꿀지 결정 필요.
- **TRAP-01 원인 미확정.**
- **`SendKeys`로 `mcpstart` 넣기 재현성 미확인.**

---

## 승격 후보

| 항목 | 이유 |
|---|---|
| **TRAP-02 IronPython 파일 close** | 브리지·GhPython을 쓰는 모든 저장소에 해당. CPython 관용구가 조용히 깨지는 대표 사례 |
| **FACT-01 엔진 무관 값 동등성** | RhinoCommon을 호출하는 스크립트는 엔진이 값에 개입하지 않는다 — 골든 테스트 설계 일반 |
| **FACT-02 정답지는 결정적 직렬화가 필요** | 골든 파일 일반 원칙. 언어·프로젝트 무관 |
| **FACT-03 `OLD` 태그 = 클래스 폐기, 엔진 아님** | Rhino 8에서 GhPython을 쓰는 모든 저장소가 만나는 오해 |
| TRAP-01 `/runscript` | **원인 확정 후** 승격. 지금은 "안 된다"까지만 확인됨 |

---
id: J-016
milestone: M2b
date: 2026-08-15
project: ljk_facade_platform
tags: [csharp, port, rhinocommon, fixtures, nunit, ironpython]
---

# J-016 · M2b · Phase A~D 를 `AdaptiveMold.Core` 로 옮기다

> 값·플래그·가지·메시지까지 파이썬과 같아졌다. 그런데 **정답지가 덮는 것이 생각보다 좁다** — 폴백 7가지 중 4가지, Phase B 7가지 중 1가지, Phase C 3가지 중 1가지만 실제로 태워 봤다. 나머지는 "옮겼다"이지 "맞다"가 아니다.

---

## TRAP-01 C# 테스트가 Rhino 세션당 한 번만 돌았다

- **증상:** 같은 Rhino 세션에서 두 번째 `run_csharp_tests.py` 가 죽는다.
  ```
  System.IO.FileLoadException: Assembly with same name is already loaded
     at System.Runtime.Loader.AssemblyLoadContext.LoadFromAssemblyPath(String assemblyPath)
     at System.Reflection.Assembly.LoadFrom(String assemblyFile)
  ```
  첫 실행은 멀쩡하다. 그래서 "빌드가 깨졌나"를 먼저 의심하게 된다.
- **원인:** `Assembly.LoadFrom` 은 **기본 ALC** 에 넣는데 거기엔 지난 실행의 동명
  어셈블리가 이미 있다. .NET Framework 는 경로가 다르면 허용했지만 .NET Core
  로더는 거부한다. 러너가 임시 폴더로 **복사본을 만들어** 태우는 것은
  *원본 파일 잠금*을 푸는 장치이지 이름 충돌과는 무관하다 — 그 주석을 믿고
  "복사하니까 괜찮을 것"이라고 넘겼던 것이 오진의 출발이었다.
- **해결:** 실행마다 새 `AssemblyLoadContext` 를 만들고 **우리 어셈블리만**
  (`AdaptiveMold.Core`·`nunit.framework`·`nunitlite`·`AdaptiveMold.Tests`)
  거기에 `LoadFromAssemblyPath` 로 직접 올린다. RhinoCommon 은 **올리지 않는다** —
  기본 ALC 의 것(Rhino 가 이미 로드한 것)으로 떨어져야 `Point3d` 같은 타입이
  같아진다. ALC 가 자기 목록을 먼저 보므로 테스트 어셈블리는 여기 올린 새 Core 에
  붙는다(기본 ALC 에 남아 있는 낡은 Core 가 아니라). 같은 세션 연속 3회로 확인.
- **재발 조건:** **Rhino 8 netcore 안에서 `Assembly.LoadFrom` 으로 같은 어셈블리를
  두 번 이상 올리려는 모든 코드.** 고쳐-빌드-재실행을 반복하는 도구가 전부 해당한다.
  없으면 태스크마다 Rhino 재시작 + 사람이 `mcpstart` 를 다시 쳐야 한다.

---

## TRAP-02 게이트 도구가 출력 한 줄 때문에 죽었다 (cp949)

- **증상:** T9 픽스처를 추가하자 `check_fixture_invariance.py` 가
  `UnicodeEncodeError: 'cp949' codec can't encode character '—'` 로 죽었다.
  검사 로직은 멀쩡한데 **결과를 못 본다.** `--save` 는 그 줄을 안 지나가므로
  성공한다 — 그래서 "검사는 통과했는데 왜 죽지"로 보인다.
- **원인:** Windows 한국어 로캘의 콘솔 기본 인코딩이 cp949 이고, 그 코드페이지에
  em dash(U+2014)가 없다. 한글은 되는데 em dash 만 안 된다. 이 줄은 **새 픽스처가
  생겼을 때만** 실행되는 `[NEW]` 경로라 Task 1 에서 도구를 만들 때는 안 걸렸다.
- **해결:** `sys.stdout.reconfigure(encoding="utf-8")` — `dump_via_bridge.py` 가
  이미 같은 처리를 하고 있었다. 픽스처를 읽어 출력하는 일회성 `python -c` 도
  같은 이유로 죽으므로 `PYTHONIOENCODING=utf-8` 을 붙인다.
- **재발 조건:** 이 PC에서 **한국어 본문에 `—`·`·`·`…` 같은 문자를 섞어 print 하는
  모든 파이썬 스크립트.** 자주 안 타는 분기에 있으면 한참 뒤에 터진다.

---

## DECISION-01 중간 산출물 지문을 정본으로 올렸다

- **선택:** `positioned_fingerprint`·`extended_fingerprint`(bbox·area·차수·CV 개수)를
  픽스처 `expected` 에 넣고 회귀 대조 항목으로 삼았다.
- **근거:** 스펙 §5.5 는 이것을 "개발 중 임시 덤프"로 규정했다. 뒤집은 이유는
  **비용 대비 얻는 것**이다 — 비용은 M2a 의 `geometry_fingerprint` 재사용 한 번,
  얻는 것은 Phase B·C 를 각각 독립으로 판정하는 능력. 없으면 Phase D 대조가
  깨졌을 때 B·C·D 중 어디가 문제인지 이분할 수 없다. 실제로 Phase B(Task 9)가
  한 번에 통과한 것을 **Phase D 를 짜기 전에** 알 수 있었다.
- **기각한 대안:** (a) 스펙대로 D 를 먼저 대조하고 B·C 는 임시 구현으로 채우기 —
  임시 구현이 틀리면 D 의 대조가 거짓으로 깨진다. (b) 중간 Brep 을 통째로
  직렬화 — 파일이 커지고 diff 가 안 읽힌다.
- **뒤집을 조건:** 지문이 케이스를 구별하지 못하게 되면. 실측으로 확인했다 —
  9케이스 중 T1(flat z=200)과 T6(flat z=150)의 `positioned` 지문만 같은데,
  이는 Phase B 가 둘 다 stroke 중앙(z=200)으로 옮기기 때문이다.
  **지문의 한계가 아니라 계산의 성질이다** (T6 는 dz=50 이라 평행이동을 빠뜨린
  구현이면 T6 에서 깨진다).

---

## DECISION-02 `NaN`·`Infinity` 는 파이썬과 다르게 막는다

- **선택:** `Validation.PositiveOrDefault`/`NonNegativeOrDefault` 가 `NaN`·`Infinity` 를
  기본값으로 되돌린다. **M2b 에서 "똑같다"를 의도적으로 어긴 유일한 지점이다.**
- **근거:** 파이썬은 `float('nan') <= 0` 이 `False` 라 통과시킨다. 그 값이
  Phase A 로 흘러가면 전 핀이 `NaN` 이 되고, 캔버스에는 아무 경고도 안 뜬다.
- **기각한 대안:** 파이썬을 따라 통과시키기 — 대조는 완벽해지지만 GH 사용자가
  숫자 슬라이더 대신 식을 물렸을 때 조용히 전부 깨진다. 어차피 **어느 픽스처도
  NaN 을 넣지 않아 대조에 영향이 없다.**
- **뒤집을 조건:** 파이썬 쪽에도 같은 방어를 넣으면 이탈이 아니게 된다. M3 에서
  파이썬을 참조 구현으로만 남길 때 정리할 것.

---

## DECISION-03 `PlaneFitResult.Failure` 는 `fit_failed` 로 보낸다 (계획 초안과 다름)

- **선택:** `fitRc != Success` 를 **전부** 평행이동 가지(`fit_failed`)로 보냈다.
  `fit_none` 상수는 남기되 C# 에서 도달 불가로 표시했다.
- **근거:** 파이썬은 `fit_result[0] == Success` 하나로만 갈린다 — `Failure` 든
  `Inconclusive` 든 똑같이 복제 + 평행이동이다. 계획 초안은 `Failure` 를
  `fit_none`(복제만, **평행이동 없음**)으로 보냈는데, 그러면 파이썬이 옮기는
  곡면을 C# 은 안 옮긴다. 성공 기준이 "똑같다"이므로 파이썬을 따랐다.
  파이썬의 `fit_none`(반환이 `None` 이거나 짧은 튜플)은 C# 시그니처
  (`PlaneFitResult` + `out Plane`)에 대응물이 없다.
- **기각한 대안:** 계획 초안대로 두기 — T1~T9 이 이 가지를 안 타므로
  **대조로는 절대 안 잡힌다.** 그래서 더 위험하다.
- **뒤집을 조건:** `Inconclusive` 와 `Failure` 를 달리 다뤄야 할 실제 사례가 나오면.
  그때는 파이썬을 먼저 고치고 픽스처를 다시 뽑는다.

---

## DECISION-04 메시지는 Phase 모듈이 만든다

- **선택:** `Optimization.Run`/`Extension.Run` 에 선택적 메시지 목록 인자를 붙였다
  (`IList<MoldMessage> messages = null`). 다중 face 경고도 `MoldSolver` 가 아니라
  `Extension.Run` 안에 뒀다.
- **근거:** 계획의 `MoldSolver` 는 메시지를 자기 안에서만 올렸는데, 그러면 Phase B
  '정렬 완료'·Phase C '확장 완료' Remark 가 통째로 빠져 **메시지 개수가 파이썬보다
  2개 적다.** 파이썬의 `component=None` 과 같은 자리를 만든 것이고, Core 5대 규약
  (GH 미참조)은 그대로다. 다중 face 경고를 밖으로 빼면 메시지 **순서**가 달라진다 —
  대조는 순서까지 본다.
- **기각한 대안:** `MoldSolver` 가 반환된 `branch`·`info` 로 메시지를 재구성하기 —
  `no_points` 가지의 유효점 개수처럼 반환값에 없는 수치가 있어서 성립하지 않는다.
- **뒤집을 조건:** Core 가 메시지를 아예 안 만들고 어댑터가 전부 만들게 하려면.
  그러면 파이썬 대조를 어댑터 계층에서 해야 하는데 거기는 GH 가 필요하다.

---

## FACT-01 폴백 가지 커버리지 — 4/7

- **측정값:** T1~T9 `summary.branch_counts` 합집합
  `{ray+/panel: 348, ray+/ext: 35, tangent: 24, ray-/panel: 2}` → **4/7**.
  미커버 3: `ray-/ext`, `closest`, `default`. (T9 이전에는 3/7)
- **측정 방법:** `plugin/fixtures/T*.json` 의 `summary.branch_counts` 를 합산.
- **유효 범위:** 이 픽스처 집합 한정. 완료조건 4는 **커버된 4가지에 한해** 성립한다.

## FACT-02 Phase B·C 가지 커버리지 — 1/7, 1/3

- **측정값:** 9케이스 **전부** `opt_branch=full`, `ext_branch=surface_extend`.
  Phase B 7가지 중 1, Phase C 3가지 중 1.
- **측정 방법:** 픽스처 `expected.opt_branch`/`ext_branch`.
- **유효 범위:** 이 픽스처 집합 한정. 정상 경로만 검증됐다는 뜻이다.

## FACT-03 T9 를 켜는 데 필요한 진폭은 1200 이었다

- **측정값:** 안장면 진폭 **600 은 `ray-` 를 못 켠다.** 그리드가 덮는
  u,v ∈ [-500,500] 구간에서 z 최저가 50mm 라 곡면이 그리드 위에 머문다.
  **1200 에서 켜졌다** — z 최저 -100, Phase B 가 |거리| 평균(211.1)으로
  dz=-11.1 을 더 내려 -111 이 된다. 결과: `ray-/panel` 2 + `ray+/panel` 34,
  클램프 2(높은 두 모서리가 400 에 걸린다).
- **측정 방법:** 진폭 600 으로 한 번, 1200 으로 한 번 `dump_via_bridge.py`.
- **유효 범위:** `spacing=200`, `width=length=1000`, `size=2000`, `z_base=200` 조합 한정.

## FACT-04 T8 C# 실측 — 중앙값 18.6 ms

- **측정값:** `17.7301 / 18.0351 / 18.5826 / 18.6105 / 20.3125` ms, 중앙값 **18.6 ms**.
  워밍업 1회 후 5회 측정. 게이트 500 ms. 파이썬 실측은 25~49 ms 였다.
- **측정 방법:** `MoldSolverTests.T8_is_under_500ms_median`, Rhino 8.33 안 NUnitLite.
- **유효 범위:** 이 PC / Debug 빌드 / 121핀. **Release 는 안 재봤다.**

## FACT-05 허용오차는 조정하지 않았다

- **측정값:** 핀 높이·pin_tops·지문 `1e-6`, 플래그·가지·메시지는 **정확 일치**.
  9케이스 전부 첫 시도에 통과 — 허용오차를 키운 곳이 없다.
- **측정 방법:** C# 테스트 97개 전부 통과 (`run_csharp_tests.py`).
- **유효 범위:** Rhino 8.33.26188.13001, net7.0-windows, RhinoCommon 8.0.23304.9001.

## FACT-06 메시지 정답지가 덮는 것은 4종뿐이다

- **측정값:** 픽스처 `expected.messages` 에 나타나는 메시지 4종 —
  Phase B 정렬 완료(R) / Phase C 확장 완료(R) / 계산 완료(R) / 클램핑(W, T3·T9 만).
  **Task 4 에서 새로 넣은 4개 중 3개(다중 face·spacing 나머지·compute 꺼짐)는
  한 케이스도 안 태운다** — spacing 이 전 케이스에서 몰드 크기를 정확히 나누고,
  곡면이 전부 단일 face 이며, `compute=True` 로만 돈다. 오류 경로 메시지도 전부 미커버.
- **측정 방법:** 9개 픽스처의 `expected.messages` 나열.
- **유효 범위:** 이 픽스처 집합 한정.

---

## PROCEDURE-01 파이썬을 고칠 때마다 도는 게이트

- **목적:** "진단·메시지를 늘렸지만 계산은 안 건드렸다"를 증명한다.
- **단계:**
  1. 파이썬 수정 (계산 코드는 손대지 않는다)
  2. Rhino 8 + `mcpstart` → `python adaptive_mold/tools/dump_via_bridge.py`
  3. `python adaptive_mold/tools/check_fixture_invariance.py`
     → `[ADDED]` 목록이 **의도한 키뿐**이고 `[PASS]` 인지 본다
  4. 맞으면 `--save` 로 기준 갱신 → 커밋
- **자동화 후보:** **예.** M2b 에서 4번 돌았고 매번 같았다. 3~4단계를 묶으면
  "확인 후 갱신"이 자동이 되어 위험하므로, **묶는다면 `[ADDED]` 를 사람에게
  보여주고 멈추는 형태**여야 한다.

## PROCEDURE-02 Core 모듈 하나를 옮기는 사이클

- **목적:** 포팅한 모듈이 파이썬과 같음을 모듈 단위로 확정한다.
- **단계:**
  1. 픽스처를 도는 대조 테스트를 **먼저** 쓴다
  2. `dotnet build AdaptiveMold.Tests/AdaptiveMold.Tests.csproj`
     → `CS0246: 형식을 찾을 수 없습니다` 를 **눈으로 본다** (테스트가 실제로
     새 타입을 참조하는지 확인하는 단계다)
  3. 구현
  4. `dotnet build LjksAdaptiveMold.sln` **성공을 눈으로 본 뒤**
     `python adaptive_mold/tools/run_csharp_tests.py`
  5. 커밋
- **자동화 후보:** 아니오. 2단계의 "실패를 본다"가 사람의 판단이고,
  4단계의 빌드-먼저 규칙은 이미 러너가 낡음 감지로 막고 있다.

---

## 미해결

- **폴백 가지 3개(`ray-/ext`·`closest`·`default`)가 여전히 미커버.** `closest` 와
  `default` 는 앞 단계가 전부 실패해야 도달하는 자리라 정상 입력으로는 태우기
  어렵다. 태울 케이스를 억지로 만드는 것이 값어치가 있는지 M3 에서 판단할 것.
- **Phase B 6가지·Phase C 2가지 미커버.** 전부 실패 경로다.
- **`Optimization.BranchFitNone` 은 C# 에서 도달 불가.** 상수만 남아 있다.
- **`info` 문자열은 대조하지 않는다.** 파이썬 `{:.0f}` 는 짝수 반올림,
  .NET `F0` 은 away-from-zero 라 `.5` 경계에서 갈린다.
- **`{:g}` 서식 차이는 미검증.** 파이썬 `%g` 는 1e6 부터 지수 표기로 넘어가고
  .NET `G` 는 그보다 훨씬 늦다. 해당 메시지(격자점 부족·spacing 나머지)가
  미커버라 실제로 갈리는지 확인 못 했다.
- **Phase E(housing/rod/top)는 범위 밖.** `pin_tops` 는 housing 높이 0 기준이다
  (파이썬 `get_housing_height(None) == 0.0` 이라 값은 같다).
- **Release 빌드 성능 미측정.**

---

## 승격 후보

- **TRAP-01** — Rhino netcore 안에서 어셈블리를 반복 로드하는 문제. Rhino 안에서
  C# 을 테스트하는 모든 프로젝트에 그대로 해당한다.
- **TRAP-02** — 이 PC 한국어 로캘 + 파이썬 콘솔 출력. 저장소를 가리지 않는다.

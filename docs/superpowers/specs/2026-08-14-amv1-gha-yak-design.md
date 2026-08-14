# AMv1 — `.gha` 포팅과 사내 패키지 배포 설계

- 날짜: 2026-08-14 (개정 1 — 팀 리뷰 반영)
- 브랜치: `feature/gha-port` (worktree `../26_AdaptiveMold_amv1`)
- 선행 문서: [`20_gha_csharp_port.md`](../../../20_gha_csharp_port.md) — 이 문서는 그 지시서의 **M2·M3 실행 설계**이며, 아래 §10 에 고치는 곳을 모아 두었습니다.

---

## 1. 목적

핀 몰드 역산기(Phase A~D)를 GhPython 에서 C# `.gha` 로 옮기고, **Rhino 패키지 매니저에서 설치되는 사내 패키지**로 배포한다.

성공 기준은 지시서 §1 과 같다 — **"더 좋아졌다"가 아니라 "똑같다"**. 계산은 건드리지 않는다.

### 왜 배포가 지금 문제인가

컴포넌트 7개가 전부 **저장소 경로를 `platform_path` 입력으로 요구**한다 (`gh_components/gh_scripts/AMv1_Inspect.py:58` 이 그 값을 `sys.path` 에 넣는다). 남의 PC 에는 그 경로가 없으므로 **현재 형태로는 배포가 불가능하다.** 배포 가능성은 `.gha` 포팅의 부산물이 아니라 목적이다.

> **정직하게 적는다 — 이 슬라이스만으로는 `platform_path` 가 사라지지 않는다.** A~D 를 `.gha` 로 옮겨도 나머지 6개 컴포넌트와 `AMv1 Inspect` 의 표시·파생 부분은 여전히 파이썬을 부른다. 그것을 걷어내는 것은 **M4**(§6)이고, 이번 슬라이스는 그 기반공사다.

### 이 슬라이스가 끝나면 무엇이 달라지는가

- Rhino 패키지 매니저에서 `ljks-adaptive-mold` 를 설치하면 GH 캔버스에 **`AMv1 Pins`** 가 나온다 — 경로 설정 없이.
- 동봉 예제로 **같은 곡면을 `AMv1 Pins`(C#)와 `AMv1 Inspect`(파이썬)에 동시에 물려 핀 높이가 일치하는지** 눈으로 볼 수 있다. 새 컴포넌트는 잎 노드가 아니라 **회귀 검증 도구**로 먼저 쓰인다.
- 클램핑·미덮힘이 일어나면 **캔버스에 경고가 뜬다** (지금은 조용하다 — §3.6).

---

## 2. 범위

| 포함 | 제외 |
|---|---|
| Phase A 그리드 (`grid.py`) | **Phase E 3D 모델 변형** (`transformation.py`) |
| Phase B 곡면 정렬 (`optimization.py`) | REST 브리지·대시보드 sync |
| Phase C 곡면 확장 (`extension.py`) | 로봇·툴패스·간섭·재생 계열(`robot*.py`, `toolpath.py`, `collision.py`, `mechanics.py`, `base_search.py`, `playback.py`) |
| Phase D 높이 산출·클램핑 (`projection.py`) | 표시·파생(deck·envelope·wires·sheet·deviation) |
| 공용 유틸 중 A~D 가 쓰는 것 (`utils.py`) | 공개 배포(food4Rhino·공개 Yak 서버) |
| **Yak 패키징 + 사내 폴더 소스 배포** | Rhino 명령(`.rhp`) 형태의 제품 |
| **런타임 메시지 정비 + 신규 4개 (파이썬 동반)** | |
| **도움말 — 툴팁·예제·매뉴얼** | |
| **픽스처 T9 추가** (`ray-` 가지 커버) | |

포팅 대상 규모(실측): `grid.py` 102 · `optimization.py` 201 · `extension.py` 154 · `projection.py` 176 · `utils.py` 159 · `adaptive_mold_v1.py` 249 = **1,041 줄**.

---

## 3. 구조

지시서 §6 의 배치를 따른다. `pyproject.toml` 이 `core/` 를 파이썬 패키지로 잡고 있으므로 C# 은 최상위 `plugin/` 에 둔다.

```
plugin/
├── LjksAdaptiveMold.sln
├── AdaptiveMold.Core/           # 순수 C#. Grasshopper·RhinoDoc 미참조
│   ├── Grid.cs
│   ├── Optimization.cs
│   ├── Extension.cs
│   ├── Projection.cs
│   ├── MoldSolver.cs            # run_adaptive_mold 의 계약 (아래)
│   └── MoldResult.cs
├── AdaptiveMold.GH/             # .gha — 얇은 어댑터
│   ├── AMv1PinsComponent.cs
│   └── AdaptiveMoldInfo.cs
├── AdaptiveMold.Tests/          # 골든 픽스처 대조
├── package/                     # Yak 매니페스트 (M3 이후)
└── fixtures/*.json              # T1~T9
```

### 3.1 Core 의 규약

1. **Grasshopper 를 참조하지 않는다.** 테스트가 GH 없이 돌고, 나중에 Rhino 명령·REST 서버가 같은 코어를 재사용한다 (00번 문서 §2.1).
2. **`RhinoDoc` 을 참조하지 않는다. `RhinoDoc.ActiveDoc` 은 특히 금지.** 헤드리스에서 null 이고, 테스트 호스트가 `CRhinoDoc_Delete` 에서 `AccessViolationException` 으로 죽는 것이 McNeel YouTrack **RH-86783**(2025-03 접수, 미해결)이다.
3. **`IGH_DataAccess` 를 참조하지 않는다.** 공식 문서가 명시한 몇 안 되는 스레드 안전성 진술이 이것이다 — *"Independent tasks should not be directly accessing `IGH_DataAccess`, as that interface is not thread safe."*
4. **RhinoCommon 기하 연산은 UI 스레드에서만 호출한다.** 근거는 §3.3. 나중에 누가 "`Parallel.For` 하나면 되는데"라고 할 때 이 줄이 답이 된다.
5. **메시지를 던지지 않고 `MoldResult` 에 모아서 돌려준다** (§3.6). 이것은 대조 가능성 때문에 고른 것인데, **비동기가 요구하는 규약과 정확히 같다** — 워커 스레드에서 `AddRuntimeMessage` 를 부르는 것은 안전하지 않고 유일한 해법이 "결과 객체에 버퍼링했다가 set-data 패스에서 방출"이다. 설계가 우연히 비동기 준비를 마쳐 놓았다.

### 3.2 모듈 경계

**파이썬 5모듈 + 파이프라인 1개**를 1:1 로 유지한다. 합치거나 나누면 대조가 어려워진다. C# 관례상 이름만 바꾼다(`compute_grid_counts` → `Grid.ComputeCounts`).

**`MoldSolver.cs` 가 하나 늘어난 이유** — `run_adaptive_mold` 는 단계 조립이 아니라 **계약을 갖고 있다**:

| 계약 | 위치 |
|---|---|
| 입력 정규화 (음수·0·파싱실패를 조용히 기본값으로) | `utils.py:52-77` |
| `min_height >= max_height` → Error 후 빈 결과 반환 | `adaptive_mold_v1.py:113-116` |
| `compute=false` → 빈 리스트 6개 + 안내 문자열 | `:99-101` |
| `pin_tops` 산식 | `:178-185` |
| 리포트 문자열 | `_build_report`, `:197-223` |

이것들이 어댑터로 흩어지면 **대조가 불가능해진다.** 따라서 `MoldSolver` 의 범위는 **`run_adaptive_mold` 에서 Phase E 를 뺀 것**이고, `ghpython_run` 의 튜플 래핑만 어댑터로 간다.

> `MoldResult` 는 파이썬 `AdaptiveMoldResult`(`adaptive_mold_v1.py:48-65`)와 1:1 이 **아니다.** 후자는 `positioned_srf`·`extended_srf`·`housings`·`rods`·`tops` 를 더 들고 있다. C# 은 **중간 Brep 을 붙들지 않는다** — 이것이 이 설계의 메모리 대책이다(§3.4).

### 3.3 스레딩 — 병렬화도 비동기도 하지 않는다

**결정: A~D Core 는 단일 스레드 순차 실행. 비동기 컴포넌트를 만들지 않는다.**

**근거 1 — 성능 문제가 존재하지 않는다 (실측, 2026-08-14).** 파이썬 A~D 를 Rhino 8.33 안에서 CPython 3 로 워밍업 1회 + 측정 3회:

| 케이스 | 핀 | ms (3회) |
|---|---|---|
| T1 flat | 36 | 6.6 / 6.7 / 4.6 |
| T3 hemisphere | 36 | 16.3 / 19.4 / 14.3 |
| **T8 large_grid** | **121** | **24.7 / 42.9 / 48.7** |

완료조건에 적혀 있던 "3초"의 **60분의 1**이다. 파이썬 인터프리터와 핀별 interop 마샬링이 포함된 값이므로 C# 은 더 빨라야 한다.

**근거 2 — 스레드 안전성 보장이 없고, 실패하면 프로세스가 죽는다.** McNeel 공식 문서에 멀티스레딩 가이드가 없다(관련 URL 두 개가 404). `Brep.ClosestPoint`·`Intersection.RayShoot`·`Surface.Extend`·`Plane.FitPlaneToPoints` 어느 것에도 스레드 안전성 진술이 없다. 반면 McNeel 직원(Keyu Gan)이 **`Brep.Split` 은 "스레드 안전하지 않을 수 있다"** 고 명시했고, 실패 모드가 `AccessViolationException` — **catch 되지 않고 Rhino 가 죽는다.** 그 사례는 **Release 빌드에서만** 재현됐고(Debug 검증은 아무것도 증명하지 못한다), `DuplicateBrep()` 후에도 죽은 보고가 있다.

**그리고 우리 코드가 정확히 그 패턴이다** — Phase D 가 핀마다 공유 `positioned_brep` 에 `ClosestPoint` 를 치고(T3 에서 24회), Phase B 는 공유 Brep 에 `RayShoot` 를 반복한다.

> **부동소수 논거는 주 근거로 쓰지 않는다.** `optimization.py:132-136` 의 누산 평균은 리덕션이라 순서가 바뀌면 클램프 경계에서 불리언이 뒤집힐 수 있지만, **그 논거는 Phase D 의 핀별 map 에는 걸리지 않는다.** 그것만 근거로 두면 "Phase D 만 병렬화하면 되잖아"에 반박당하고 결론까지 무너진다.

**`GH_TaskCapableComponent` 는 이 목적에 맞는 도구가 아니다.** ⑴ `GetSolveResults` 는 *"Call this method to **await** the associated task"* 이고 `SolveInstance` 안 — 즉 **UI 스레드가 그대로 대기**한다. 얼음은 옮겨질 뿐 사라지지 않는다. ⑵ 병렬 단위가 `SolveInstance` 호출 횟수인데(Baer) 우리는 곡면 하나·**1회**다. 태스크 하나면 오버헤드만 붙는다. **반복 병렬화 장치이지 비동기 장치가 아니다.**

UI 를 실제로 살리는 유일한 알려진 기법은 Speckle 의 `GH_AsyncComponent`(솔루션을 끝낸 뒤 워커 완료 시 `InvokeOnUiThread` 로 재트리거)인데, 저자 본인의 경고가 *"99% of the times this won't explode in your face. It still might though!"* 이다. **50 ms 계산에 치를 값이 아니다.**

**대신 지금 하는 것:** `info` 출력에 **경과 ms** 를 싣는다. 게이트가 아니라 매 솔루션이 스스로 회귀를 보고하게 한다.

**뒤집을 조건 (순서를 지킬 것):** 한 솔루션이 **500 ms 를 넘으면** → ⑴ 프로파일해서 병목이 정말 기하 호출인지 확인 → ⑵ McNeel 에 해당 메서드들의 스레드 안전성을 **직접 질의**(포럼 아카이브 추론보다 싸고 확실하다) → ⑶ 그다음에 설계. 도구는 `GH_AsyncComponent` 계열.

> 이 프로젝트가 겪은 "Rhino 20분 얼음"(J-011 TRAP-01)의 원인은 **베이스 탐색**(후보 60 × 타겟 1,175, 후보당 1.7~50초)이었지 A~D 가 아니다. 얼음을 실제로 없애야 하는 곳은 그쪽이며, 이 설계의 범위 밖이다.

### 3.4 컴포넌트를 쪼개지 않는다

**결정: A~D 를 캔버스에서 여러 컴포넌트로 나누지 않는다.** `AMv1 Pins` 하나가 파이프라인 전체를 돈다.

- **근거 1 — 이 저장소의 규칙.** `J-012` DECISION-01: **경계는 바뀌는 이유로 긋는다.** A~D 는 전부 같은 이유(역산 알고리즘)로 바뀐다.
- **근거 2 — 정답지가 없는 경계가 공개 API 가 된다.** Phase D 는 `positioned_srf`·`extended_srf`·`extension_method` 셋을 동시에 받는다(`projection.py:33-35, 77`). 쪼개면 중간 Brep 2개와 문자열 1개를 캔버스에 노출해야 하는데, 그 중간 산출물은 픽스처가 담지 않는 **유일한 지점**이다(§5.1).
- **실제 경계는 다른 데 있다** — **역산(A~D) vs 표시·파생**(deck·envelope·wires·sheet·deviation). 이 둘은 다른 이유로 바뀐다. 이번 슬라이스는 역산만 가져가고, 그 경계는 M4 에서 갈라진다.

**"재사용 가능한 단위"는 `Core` 클래스 분할로 답한다** — `Grid`·`Optimization`·`Extension`·`Projection` 이 각각 public API 를 갖고 독립적으로 호출·테스트된다.

**메모리는 애초에 쟁점이 아니다 (실측).** 중간 산출물을 `GeometryBase.ToJSON` 으로 쟀다 — T3(36핀) `positioned_srf` 3,783 B · `extended_srf` 7,751 B · `grid_pts` 864 B, T8(121핀) 각각 4,187 / 4,635 / 2,904 B. **한 솔루션의 중간 상태 전체가 약 13 KB** 다. 쪼개서 GH 가 전부 캔버스에 유지해도 인스턴스 100개에 1.5 MB. 핀이 수백 개가 돼도 늘어나는 것은 `grid_pts` 수 KB 뿐이고 곡면 크기는 핀 수와 무관하다. → **"메모리 관리를 위해 나눈다"는 동기는 기각된다.**

그래도 `MoldResult` 는 **중간 Brep 을 붙들지 않는다** — 필요 없는 것을 들고 있을 이유가 없고, 파이썬 `AdaptiveMoldResult` 와 달라지는 지점이므로 명시해 둔다.

> **분할이 실제로 깨뜨리는 것 — 이게 결정적이다.** `projection.calculate_heights` 가 `if extended_brep is not None and extension_method != EXTENSION_METHOD_TANGENT:` 로 분기한다. **Phase C 가 "`Surface.Extend` 였나 tangent 폴백이었나"를 Phase D 의 가지 선택에 실어 보낸다.** C·D 를 분리하면 이 문자열이 캔버스 와이어가 되고, 사용자가 다른 Brep 을 물리거나 method 를 안 물리는 순간 **완료조건 4(폴백 가지 일치)가 컴포넌트 수준에서 검증 불가능해진다.** 두 Brep + 한 문자열이 반드시 짝으로 다녀야 하는데 캔버스는 그 짝을 강제할 수 없다.

**타입은 기본 GH 타입으로 충분하다** — `positioned_srf`·`extended_srf` 는 둘 다 `Brep`(`extend_surface` 가 `ToBrep()` 한다) → `Param_Brep`. 커스텀 `GH_Goo` 가 필요해지는 유일한 지점은 파라미터 묶음인데, 쪼개지 않으면 그 문제 자체가 없다.

### 3.5 컴포넌트 인터페이스

이름은 **`AMv1 Pins`** — 기존 7개가 전부 `AMv1 *` 이고 툴팁 레지스트리(`gh_components/param_docs.py`)의 키도 그 형식이다.

| 입력 (8) | 출력 (8) |
|---|---|
| `target_srf`, `base_plane`, `width`, `length`, `spacing`, `max_height`, `min_height`, `compute` | `pin_heights`, `pin_tops`, `grid_pts`, `clamp_flags`, `extension_flags`, `info`, **`nx`**, **`ny`** |

**`nx`·`ny` 를 추가한 이유:** 하류가 `int(width // spacing) + 1` 로 재유도하고 있는데(`AMv1_Inspect.py:322-323`) 그 재구현이 `grid.py:35-38` 의 `nx<2 → 2` 클램프를 빠뜨렸다. 출력으로 내면 중복과 불일치가 동시에 사라진다.

**인덱싱은 `idx = j * nx + i` 를 그대로 유지한다.** 여기서 순서가 바뀌면 픽스처 대조가 전부 무의미해진다.

**`pin_tops` 계약:** `grid_pt + base_plane.ZAxis * h` — **housing 높이 0 기준.** 파이썬은 `transformation.get_housing_height(housing_model)` 를 더하는데(`adaptive_mold_v1.py:178-185`) 그 모듈은 이 슬라이스의 범위 밖이다. 픽스처는 housing 없이 뽑혀(`hh=0`) 대조는 통과하지만, **housing 모델을 물린 사용자에게는 두 컴포넌트의 값이 달라진다.** 입력을 9개로 늘리지 않고 계약으로 못박고 매뉴얼에 적는다.

**입력 정규화:** `utils.py:52-77` 은 음수·0·파싱 실패를 **조용히 기본값으로 되돌린다**(width=-5 → 1000). 이 동작을 `MoldSolver` 안에서 재현한다. GH 파라미터 선언의 기본값은 `utils.py` 와 **같은 수치**로 둔다 — GH 기본값만 주고 정규화를 생략하면 -5 가 그대로 들어와 동작이 갈린다.

**`compute=false` 계약:** 빈 리스트 8개 + 안내 문자열. 출력을 세팅하지 않으면 null 이 흘러 하류가 달라진다.

### 3.6 오류 처리와 런타임 메시지

`Core` 는 GH 를 모르므로 메시지를 **던지지 않고 `MoldResult` 에 모아서 돌려준다.** 어댑터가 그것을 GH 런타임 메시지로 번역한다. 등급(Error/Warning/Remark)은 파이썬과 같은 자리에서 같게 올린다.

**규약: 모든 메시지는 `[무엇이] · [결과가 어떻게 됐는지] · [다음에 무엇을]`.**

기존 10개 중 4개가 이 규약에 미달이라 재작성한다(`target_srf is invalid.`, `Surface optimization failed.`, `Not enough in-bounds points`, `Surface extension: could not extract surface`). `Surface.Extend() failed, using tangent fallback` 은 **Remark 로 강등** — 흔하게 뜨는 Warning 은 사용자에게 경고 무시를 학습시킨다.

**신규 4개를 넣는다.** 지금 A~D 전 범위에 **클램핑 경고가 한 줄도 없다** — 픽스처 실측으로 반구(T3)에서 핀의 **56%(20/36)가 클램핑되는데 캔버스는 초록**이다.

| 등급 | 내용 | 근거 |
|---|---|---|
| Warning | 핀 N/M 개가 행정 한계에 걸렸다 → 그 지점은 목표를 재현 못 한다 → `clamp_flags` 확인, `max_height` 조정 또는 곡면 완만화 | 경고 부재 |
| Warning | `target_srf` 의 face 가 N 개다 → Phase C 는 첫 face 만 쓴다 → 단일 face 로 합칠 것 | `utils.py:136` 검사·경고 없음 |
| Remark | `spacing` 이 `width` 를 나누지 못한다 → X 방향 900mm 까지만 덮는다 | `grid.py:32` |
| Remark | `compute` 가 꺼져 있다 → Boolean Toggle 을 True 로 | 지금 `info` 문자열에만 있음 |

> **"똑같다"를 지키는 방법:** 신규 4개를 **파이썬에 먼저 넣고 픽스처를 재생성해 `expected` 배열 6개가 한 글자도 안 바뀌는 것을 확인**한다. 그것이 "계산을 건드리지 않았다"의 증명이다. 파이썬에 안 넣으면 등급 대조 자체가 성립하지 않는다.

**언어:** 컴포넌트 이름·파라미터 이름은 **영어 유지**(파라미터 이름은 픽스처 JSON 키·C# 프로퍼티·문서에 동시에 나타난다 — 번역하면 대조 지점이 하나 늘고 픽스처가 무의미해진다). 툴팁·매뉴얼·런타임 메시지는 **한국어**. 지금 메시지가 영어 9 : 한국어 1 로 섞여 있으므로 한국어로 통일하되, **파라미터명·수치·API 이름은 원문 그대로** 둔다 — 사용자가 화면에서 찾을 문자열과 같아야 한다.

### 3.7 데이터 흐름

```
target_srf, base_plane, width, length, spacing
      │
      ├─ A  Grid.Build          → gridPts (nx*ny)
      ├─ B  Optimization        → positionedSrf   (평면피팅 정렬)
      ├─ C  Extension           → extendedSrf     (경계 밖 확장)
      └─ D  Projection          → heights, clampFlags, extensionFlags, branchTaken
                                   min_height / max_height 로 클램핑
      ↓
   MoldResult (중간 Brep 미보유)  →  어댑터가 출력 8개로 편다
```

**진단 출력을 셋으로 늘린다.** 지금 `branch_taken` 은 Phase D 만 덮는다. Phase B 에는 5갈래(`optimization.py:44-45, 49-62, 66-68, 77-84, 104`), Phase C 에는 3갈래(`extension.py:38-42, 54-58, 60-65`)가 있고 **T1~T9 는 전부 정상 경로만 탄다.** 이 선택은 `opt_info`/`ext_method` 문자열로만 새어나가는데 둘 다 픽스처 밖이다. → `MoldResult` 에 `optBranch`·`extBranch` 를 추가하고 **파이썬에도 같은 진단을 넣는다.** 알고리즘 변경이 아니라 진단 추가이며, `J-002` DECISION-02 의 선택적 출력 패턴이 선례다.

---

## 4. 도움말 — 무엇이 어디에 사는가

### 4.1 정본은 `docs/params.ko.json` 하나

지금 툴팁 정본은 `gh_components/param_docs.py` 이고 **153개**(입력 94 / 출력 59)가 들어 있다. 품질이 높다 — 타입 설명이 아니라 함정·실측치·다음 행동이 들어 있다. 버릴 자산이 아니다.

문제는 **파이썬 모듈이라 C# 이 못 읽는다**는 것뿐이다. 이미 `apply_param_docs.py:113-114` 가 JSON 으로 덤프하고 있으므로, **형식 변환이 아니라 정본의 위치를 한 칸 내리는 일**이다.

```
docs/params.ko.json          ← 정본
   ├─ C# 빌드가 EmbeddedResource 로 읽어 pManager.Add*Parameter 설명에 주입
   ├─ 매뉴얼 파라미터 표를 생성
   └─ apply_param_docs.py 가 GhPython 7개용으로 계속 소비
```

- **기각 — C# 소스에 직접 쓴다:** 매뉴얼과 GhPython 이 못 읽어 정본이 둘이 된다. 두 컴포넌트가 캔버스에 공존하므로 사용자 눈에 나란히 보인다.
- **뒤집을 조건:** GhPython 계열이 전부 `.gha` 로 넘어가면 소비자가 사라지고, 그때는 C# 소스가 정본이어도 된다.

**`.gha` 가 없애는 것:** `.gh` 저장 후 재시작 시 설명 소실(실측 81/85, 커밋 `b0ee4a0`)과 코드 push 시 설명 소실(`apply_param_docs.py:17-21`). C# 은 설명이 어셈블리에 컴파일되므로 둘 다 사라진다. → `apply_param_docs.py` 는 GhPython 7개 컴포넌트용으로만 남는다.

**커버리지 실측:** 입력 8개는 **전부 재사용 가능**(단 `target_srf` 의 GhPython 전용 문장은 삭제). 출력은 `pin_tops` 만 거의 그대로, `info` 는 내용이 달라 재작성, **`pin_heights`·`grid_pts`·`clamp_flags`·`extension_flags` 4개는 문안이 저장소 어디에도 없다** → 신규 집필. `nx`·`ny` 도 신규.

### 4.2 계층

| 계층 | 내용 | 사는 곳 |
|---|---|---|
| 파라미터 툴팁 | 첫 줄은 단독 성립(무엇+단위+기본값), 함정은 아래 줄. 평문(마크다운 금지) | `params.ko.json` → C# |
| 컴포넌트 설명 | 4단계 요약 + 단위 + 인덱싱 규약 + "플래그가 켜진 핀은 계산은 됐지만 믿을 수 없다" | C# 생성자 |
| 우클릭 메뉴 | `예제 파일 열기` · `매뉴얼 열기` · `진단 텍스트 복사` | `AppendAdditionalComponentMenuItems`. **경로는 `Grasshopper.Instances.ComponentServer.FindAssembly(id).Location` 으로 얻는다 — `Assembly.Location` 은 금지** (COFF 메모리 로딩이 켜진 사용자에게는 빈 문자열이라, 어떤 PC 에서는 되고 어떤 PC 에서는 안 되는 재현 불가 버그가 된다) |
| 예제 `.gh` 4개 | 아래 | 패키지 `examples/` |
| 매뉴얼 | 정본 저장소 `docs/manual/`(md), 배포본은 패키지 안 html. **사내 위키는 링크만** — 위키는 버전이 없어 설치본과 어긋나면 없느니만 못하다 | 둘 다 |
| 런타임 메시지 | §3.6 | 코드 |

**예제 4개는 골든 픽스처와 같은 입력으로 만든다** — 장식이 아니라 검사 대상이 된다(§5.4).

| 파일 | 픽스처 | 무엇을 |
|---|---|---|
| `01_hello.gh` | T1 | 기준선. **`base_plane` 을 `(-500,-500)` 으로 옮긴 상태로 저장** — 원점이 몰드 모서리라는 함정을 첫 화면에서 막는다 |
| `02_coverage.gh` | T4 | `extension_flags` 가 0 → 전부 True 로 바뀌는 것 |
| `03_clamping.gh` | T3 | `clamp_flags` 20/36. **`max_height` 슬라이더를 붙여** 값을 올리면 여유가 생기는 게 아니라 곡면이 올라간다는 것을 만지게 한다 |
| `05_parity.gh` | T3 | **`AMv1 Pins`(C#)와 `AMv1 Inspect`(파이썬)에 같은 곡면을 물려 핀 높이 일치를 눈으로 확인** |

### 4.3 사용자가 실제로 막히는 곳 (코드 확인됨)

매뉴얼과 툴팁의 예산을 여기에 몰아넣는다.

| # | 함정 | 근거 |
|---|---|---|
| T-1 | `base_plane` 을 비우면 그리드가 원점을 **중심이 아니라 모서리**로 잡는다 → 원점 중심 곡면은 1/4만 겹치는데 경고가 없다 | `grid.py:67-72` |
| T-2 | `max_height` 는 클램프 한계가 아니라 **곡면을 어디 놓을지 정하는 값** — 평균을 `(min+max)/2` 로 옮긴 뒤 계산이 시작된다. 키우면 곡면이 통째로 올라간다 | `optimization.py:130-138` |
| T-3 | 클램핑이 나도 화면에 아무 표시가 없다 | §3.6 |
| T-4 | 곡면이 그리드를 안 덮어도 **폴백 4단이라 절대 실패하지 않는다** — 빗나간 핀에 `(min+max)/2` 가 들어가 다른 핀과 똑같아 보인다 | `projection.py:62-99` |
| T-5 | 폴리서피스를 물리면 Phase C 가 첫 face 만 본다(경고 없음). Phase B·D 는 Brep 전체를 쓰므로 결과가 반쯤 섞인다 | `utils.py:136-137` |
| T-6 | `spacing` 이 `width` 를 안 나누면 남는 폭에 핀이 없다 | `grid.py:32` |
| T-7 | 높이에 부호가 없다 — 곡면이 그리드 아래여도 양수 | `projection.py:135,140,157` |

T-1·T-6 은 툴팁으로 끝난다. **T-2·T-3·T-7 은 툴팁으로 안 된다** — 알고리즘을 알아도 코드를 안 읽으면 모르는 것들이고, 실제로 이 팀 자신이 `T5_deep_clamp` 라는 이름으로 한 번 속았다. 경고 메시지와 `03_clamping.gh` 슬라이더로 전달한다.

### 4.4 자동 검사

도움말이 코드와 어긋나면 없느니만 못하다. 이미 어긋난 증거가 셋 있다 — `gh_components/README.md:26` "125개"(실제 153) · `adaptive_mold/README.md:118` 이 없는 폴더를 가리킴 · 매뉴얼 3종이 전부 "코드를 붙여넣고 `sys.path.insert`"로 시작(`.gha` 사용자에게는 거짓).

| # | 검사 |
|---|---|
| 1 | 컴포넌트 `Params.Input/Output` 이름 집합 ↔ `params.ko.json` 키 집합 **양방향** 대조. 지금 `apply_param_docs.py` 의 브리지는 한쪽만 본다(`BRIDGE_CODE:99-100`) — 그것도 고친다 |
| 2 | `Description == NickName` 이면 미작성으로 판정 (`build_gh_components.py:258` 이 그렇게 채운다) |
| 3 | 매뉴얼 파라미터 표는 생성 후 `git diff --exit-code` |
| 4 | 예제 `.gh` 의 핀 개수·클램핑 수·확장영역 수를 픽스처 `summary` 와 대조 — 예제가 낡으면 테스트가 깨진다 |
| 5 | 문서에 숫자를 손으로 적지 않는다 (생성하거나 안 적는다) |

**자동화 불가:** 툴팁 문장이 옳은지는 기계가 못 본다. 대신 **툴팁이 주장하는 실측치는 저널 링크를 달고, 링크 없는 수치는 쓰지 않는다.**

---

## 5. 테스트 전략

### 5.1 정답지와 그 한계

`plugin/fixtures/T1~T8.json`(M1 확정, 커밋됨) + **T9 신규**. 구조는 `case`/`note`/`input`/`expected`/`summary`/`meta` 이고 `expected` 에 핀별 배열 6개가 있다 — `pin_heights`·`clamp_flags`·`extension_flags`·`branch_taken`·`pin_tops`·`grid_pts`.

| 항목 | 허용 |
|---|---|
| `pin_heights` · `pin_tops` · `grid_pts` | 1e-6 mm 에서 시작, 실측 후 조정 |
| `clamp_flags` · `extension_flags` | **정확히 일치** |
| `branch_taken` · `optBranch` · `extBranch` | **정확히 일치** |
| `info` | **대조하지 않는다** (아래) |

**`info` 를 제외하는 이유:** 파이썬 `{:.0f}` 는 짝수 반올림(banker's), .NET `F0` 은 away-from-zero 계열이라 `.5` 경계에서 갈린다. 출력에 넣어두고 검증이 침묵하는 것이 최악이므로 **"대조 대상 아님"을 명시**한다.

**폴백 가지 커버리지는 3/7 이다 — 5/7 이 아니다.** 커밋된 픽스처 8개의 `summary.branch_counts` 를 전수 확인한 결과 실제 등장하는 가지는 `ray+/panel`(314) · `ray+/ext`(35) · `tangent`(24) **셋뿐**이다. 미커버는 `ray-/panel` · `ray-/ext` · `closest` · `default` **넷**. 지시서 §5 의 "5/7" 은 **J-003 이 Phase B 회전 결함을 고치기 전의 값**이고(그 수정으로 T2 가 `ray-` 를 안 타게 됐다) 표가 갱신되지 않았다.

→ **T9 를 추가한다.** Phase B 가 평균을 stroke 중앙에 맞춰도 가장자리가 그리드 아래로 내려가는 **진폭 큰 곡면(깊은 안장형)** 이 필요하다. 옛 T2 입력으로는 복구되지 않는다 — 그 가지를 태운 원인이 고쳐진 결함이었기 때문이다.
→ **T9 로도 `ray-` 가 안 켜지면 완료조건 4를 "커버된 가지에 한해 일치"로 낮춰 적는다.** 되지도 않는 조건을 걸어두는 것이 더 나쁘다.

**나머지 한계는 이번에 없애지 않는다** (기준이 "옳음"이 아니라 "같음"이므로): `T5_deep_clamp` 가 실제로는 클램핑을 안 하는 것(클램핑은 T3 뿐), 높이 부호 소실, `closest`·`default` 미커버.

### 5.2 먼저 입력이 같아야 한다

**픽스처의 `input` 은 지오메트리가 아니라 생성 스펙이다** — `{"kind":"hemisphere","radius":400.0,...}`. 지오메트리를 만드는 것은 `adaptive_mold/tools/dump_fixtures.py:89-137` 이고, 거기에 픽스처에 안 적힌 상수가 박혀 있다(반구 중심 `(500,500)`, interval `±size/2`, rotated plane 원점 `(500,300,100)` + x축 `(1,1,0)` 등).

C# 테스트는 이 빌더를 재구현해야 하는데, 어긋나면 **Core 가 옳아도 대조가 깨지고**, 우연히 상쇄되면 **틀린 채로 통과한다.**

→ **M2a 의 첫 작업 — `TestSurfaceBuilder`.** `dump_fixtures.build_surface`/`build_plane` 을 1:1 로 포팅한 C# 클래스를 만들고, 파이썬 픽스처에 케이스별 **지오메트리 지문**(bbox·면적·제어점 수·degree)을 추가해 빌더가 그것을 먼저 통과해야 한다. 어느 러너를 쓰든 필요하므로 추가 비용이 아니지만, **`Grid` 포팅보다 먼저 세워야 한다** — 입력 동일성이 증명되기 전의 출력 대조는 전부 무의미하다.

### 5.3 메시지도 정답지에 넣는다

지금 픽스처는 `component=None` 으로 뽑혀(`dump_fixtures.py:251-260`) **메시지가 한 줄도 들어 있지 않다.** "Core 테스트가 경고까지 검증할 수 있다"는 구조상 가능하다는 뜻이지 정답지가 있다는 뜻이 아니다.

→ 가짜 component 로 수집해 `expected.messages: [[level, text], …]` 를 픽스처에 추가한다. §3.6 의 신규 4개가 여기서 검증된다.

### 5.4 러너 — 반나절 타임박스, 그다음 `.rhp`

**1순위 `Rhino.Testing`** (McNeel, MIT, `github.com/mcneel/Rhino.Testing`). 확인된 요건:

| 항목 | 사실 |
|---|---|
| 버전 | **38개 전부 `-beta`.** 안정 릴리스 없음. Rhino 8 계열은 `8.0.28-beta`(2025-05-12) 이후 **동결** |
| Rhino 설치 | **필수** (Rhino 8+) |
| 라이선스 | **필수** — 실체가 Rhino.Inside + NUnit 접착제라 헤드리스여도 같은 라이선스 코드를 탄다 |
| 프레임워크 | **NUnit 전용** (`[RhinoTestFixture]`, NUnit ≥3.14). xUnit·MSTest 없음 |
| 설정 | `{AssemblyName}.Configs.xml` — 우리는 `LoadGrasshopper=false`, `CreateRhinoView=false` 로 충분 |
| 플랫폼 | Windows **x64 전용** |

**기대되는 실패를 미리 적어 둔다:** McNeel 공식 템플릿(`CSRhinoTest`) 자체가 `Rhino.Testing 8.0.23-beta` + `net7.0-windows` + `Microsoft.NET.Test.Sdk 17.13.0` 을 물리는데 이것이 **보고된 깨진 조합**이다(*"Microsoft.NET.Test.Sdk doesn't support net7.0-windows"*, 미해결). **우리 타겟이 `net7.0-windows` 확정이므로 정면으로 부딪힌다.** 또 `RhinoDoc.ActiveDoc` 접근은 테스트 호스트를 죽인다(RH-86783, 미해결) — §3.1 규약 2가 그것을 막는다.

→ **반나절 타임박스.** 안 서면 즉시 폴백.

**폴백 `.rhp` + NUnitLite — 선례가 있다.** (앞서 "선례 없음"으로 적었던 것은 틀렸다.) `JoinCAD/RhinoNUnitTestRunner`(약 150줄), `MingboPeng/RhinoUnitTest`, `structurecraft/nunittestrunner` 가 있고 McNeel 자신도 미공개 `RhinoNUnit` 명령을 갖고 있다(Rhino 8 `PluginManager` 에서 "NUnit" 검색으로 30초에 확인 — **미검증**). 핵심은 세 줄이다:

```csharp
var assembly = typeof(AdaptiveMold.Tests.FixtureTests).Assembly;
new AutoRun(assembly).Execute(new string[]{ }, new RhinoConsoleTextWriter(), null);
```

NUnitLite `AutoRun` 은 **같은 AppDomain 에서 돈다** — `Rhino.Testing` 문제의 상당수가 테스트 탐색기가 만드는 자식 AppDomain 에서 오므로 이 경로가 원인을 구조적으로 회피한다. 그리고 `Rhino.Testing` 은 Rhino 안에서 도는 것을 이미 감지·지원하므로(`s_inRhino`) **테스트 어셈블리 하나가 두 호스트를 모두 섬긴다 — 폴백으로 가도 테스트 코드를 버리지 않는다.**

| 산출물 | 내용 |
|---|---|
| 프로젝트 | `AdaptiveMold.TestHost`(`.rhp`, `net7.0-windows`) — **`.gha` 와 다른 출력 폴더에 둔다.** 같은 폴더면 `yak spec` 이 `.rhp` 를 검사해 배포 태그와 `secret`(플러그인 GUID)이 엉킨다 |
| 명령 | `AmV1RunFixtures` — 인자: 픽스처 폴더, 출력 JSON 경로 |
| 기동 | `mcpstart` 후 브리지로 `RhinoApp.RunScript("_AmV1RunFixtures …")`. **`Rhino.exe /runscript=` 로 밖에서 태우는 것은 여전히 안 된다**(J-005 TRAP-01) |

**Core 를 RhinoCommon 없이 테스트하는 길은 없다.** 알고리즘 본체가 `RayShoot`·`ClosestPoint`·`Surface.Extend`·`FitPlaneToPoints` — 전부 네이티브 openNURBS 호출이다. 순수 관리 코드로 남는 것은 `Grid` 산술과 `_clamp_height` 뿐이고, 그것만 갈라내려 구조를 흔들 값이 없다.

**CI 에 올리지 않는다.** GitHub-hosted `windows-latest` 는 Windows Server 라 Rhino.Inside 가 `RHINO_TOKEN` 을 요구하는데, 그 토큰은 코어시간 과금이고 McNeel 이 **상용 라이선스와 비호환**이라고 명시했다. 더 나쁜 것은 **실패가 조용하다는 것** — 실제 초록 런에서 Rhino 미설치로 `[RhinoTestFixture]` 들이 discovery 단계에서 사라졌는데 로그는 `Total tests: 21, Passed: 21` 이었다. 언젠가 올린다면 **기대 테스트 개수 단언이 필수**다. 우리는 사내 저장소이고 대조는 사람이 돌리는 게이트이므로 CI 가 필요 없다.

### 5.5 단계별로 픽스처가 덮는 것

| 단계 | 대조 |
|---|---|
| A `Grid` | **직접 된다** — `expected.grid_pts` |
| B `Optimization` · C `Extension` | **중간 산출물이 픽스처에 없다.** 최종 출력으로만 간접 검증되므로, 포팅 중에는 파이썬과 같은 중간값이 나오는지 임시 덤프로 대조한다 (개발 중 수단이지 회귀 테스트가 아니다) |
| D `Projection` | **직접 된다** — 배열 5개 |

### 5.6 TDD 순서

Core 모듈마다 **픽스처에서 뽑은 케이스로 실패하는 테스트를 먼저 쓰고** 포팅한다. 순서는 §5.2 의 지문 검사 → A → D → B → C (대조 가능한 것부터).

---

## 6. 배포 설계 — 서버를 만들지 않는다

### 6.1 실측 (이 PC 에서 직접 확인)

- `yak.exe` **0.15.2 (0.15.9684.24078), Rhino 8.33.26188.13001** — `C:\Program Files\Rhino 8\System\yak.exe`
- `yak push` · `search` · `install` 이 `-s, --source URL` 을 받는다 (기본 `https://yak.rhino3d.com/`)
- `yak build` 옵션은 `--platform win|mac|any` 와 `--version` 뿐 — **Rhino 버전 태그는 어셈블리에서 유도된다**(`rh8_0-win` 꼴). 손으로 `rh8-win` 을 적는 것이 아니다
- `yak cache` 는 도움말에 안 보이지만 실재한다

### 6.2 문서 (실측 아님 — 인용)

- Rhino 쪽 소스 등록은 **Options > Advanced 의 `Rhino.Options.PackageManager.Sources`**, 세미콜론 구분
- **커스텀 저장소는 `.yak` 파일이 든 폴더일 뿐이다.** `Directory.EnumerateFiles` 가 받는 것(일반 경로·매핑 드라이브·UNC·마운트 공유)이면 된다
- Rhino 8.15+ 는 `yak cache` 인덱스로 느린 네트워크를 덮는다

### 6.3 결정

**자체 Yak 서버를 구현하지 않는다.** 서버 API 스펙이 공개돼 있지 않아 비싸고, 폴더 소스로 같은 목적이 달성된다.

- **채택:** `.yak` 을 work.ljks.io 에 두고, 각 PC 는 **로컬 폴더 하나**(`%LOCALAPPDATA%\LJKS\packages`)를 소스로 등록한다. 인터넷 너머에서 되고 공유·방화벽 설정이 필요 없다.
- **기각 1 — 사내 NAS UNC 직접:** 동기화가 없어 단순하지만 사무실 밖에서 안 된다. 나중에 소스 문자열 하나 추가로 병행 가능.
- **기각 2 — 자체 yak 서버:** 위 근거.
- **뒤집을 조건:** 사외 공개가 필요해지면 같은 `.yak` 을 공개 서버로 `push` 만 하면 된다. 산출물은 바뀌지 않는다.

**미검증:** 정적 HTTPS 폴더를 소스 URL 로 직접 물릴 수 있는지 — 문서의 URL 예시는 진짜 API 를 쓰는 공식 서버다. **이 설계는 URL 소스에 기대지 않는다.**

### 6.4 패키지

| 항목 | 값 |
|---|---|
| id | `ljks-adaptive-mold` (글자·숫자·하이픈·언더스코어만. **최초 업로드의 대소문자가 영구 고정**) |
| 배포 태그 | `rh<major>_<minor>-<platform>` — **참조한 `Grasshopper.dll`/`RhinoCommon.dll` 버전에서 유도된다.** `--platform` 만 재정의 가능하고 Rhino 버전 반쪽은 불가(McNeel 미구현 티켓 RH-80951). 공식 우회는 **파일명 개명**. M2a-0 에서 실제 산출 파일명 확인 |
| 매니페스트 필수 | `name` · `version` · `authors` · `description`. 권장 `url` · `keywords`(**검색 대상**) · `icon`(PNG/JPEG 64×64). `icon_url` 은 폐기됨 |
| 내용물 | `AdaptiveMold.GH.gha` · `AdaptiveMold.Core.dll` · `examples/*.gh` · `docs/manual.html` · 아이콘 — **`.gha`·`manifest.yml` 은 최상위 필수**, 나머지 하위 폴더는 보존된다 |
| 타겟 | `net7.0-windows` (지시서 §3.1) |

버전은 **어셈블리 버전 하나를 정본**으로 삼고 매니페스트가 `$version` 치환으로 따라간다.

**빌드 설정:** `<CopyLocalLockFileAssemblies>true</CopyLocalLockFileAssemblies>` 를 넣는다. 없으면 NuGet DLL 이 출력에 복사되지 않아 **의존성 빠진 `.gha` 가 패키징된다.** `Core.dll` 은 프로젝트 참조라 지금은 복사되지만 NuGet 의존성이 하나라도 늘면 즉시 걸린다. (Rhino 8 은 플러그인별 `AssemblyLoadContext` 격리를 하지 않으므로 — RH-80178 미해결 — **흔한 이름의 서드파티 DLL 을 끌어들이지 않는다.**)

**설치 경로 (실측):** `%APPDATA%\McNeel\Rhinoceros\packages\8.0\<PackageName>\<version>\`

**운영 함정 셋:**
1. **`yak cache` 는 자동 갱신되지 않는다.** 인덱스가 있으면 그것이 정본이므로 **낡은 인덱스가 새 패키지를 감춘다.** 배포 폴더에 `.yak` 을 올릴 때마다 `yak cache` 재실행을 **배포 스크립트에 넣는다.**
2. **구버전 폴더가 남는다 (실측: 이 PC 의 `OpenNest` 에 2.93 과 2.94 공존).** McNeel 이 Rhino 8 자동업데이트의 의도치 않은 결과로 인정했고(RH-85306, 8 SR23 수정), 증상은 **DLL 이 무작위로 옛 버전에 바인딩되는 것**이다. → **완료조건 6의 설치·제거·재설치 검증은 UI 가 아니라 디스크에서 한다.**
3. **자동 업데이트가 기본 켜짐이라 다운그레이드를 되돌린다.** 끄기: `Rhino.Options.PackageManager.CheckForUpdates` = false.

**예제·매뉴얼은 패키지에 넣을 수 있지만 Rhino 는 아무것도 렌더링하지 않는다** — 패키지 매니저는 매니페스트 메타데이터만 보여준다. 사용자는 설치 폴더를 못 찾으므로 **우클릭 메뉴가 유일한 실용 경로**이고, 경로는 `ComponentServer.FindAssembly(id).Location` 으로 얻는다(§4.2).

> **부수 이점 — Mark-of-the-Web.** 패키지 매니저는 프로그램적으로 압축을 풀어 설치본에 `Zone.Identifier` 가 붙지 않는다(실측: 이 PC 의 yak 설치 `.gha` 전부 없음). 반면 사용자가 `.zip` 을 브라우저로 받아 손으로 풀면 차단이 상속된다. **채택안이 이 문제를 자동으로 피한다** — 수동 배포로 되돌리자는 제안이 나오면 이 줄이 근거다.

> **M2a-0 에서 확인할 것:** 로컬 폴더 소스로 설치하면 **매니페스트 필드가 UI 에 비어 보인다는 보고**가 있다(McNeel 미응답, **미검증**). "패키지가 뜬다"만 보지 말고 필드가 채워지는지도 본다. 비어도 설치는 되므로 **실패 판정하지 말고 기록만** 한다.

---

## 7. 작업 순서

| | 내용 | 끝났다고 말할 수 있는 조건 |
|---|---|---|
| **M2a-0** | 스크래치 `.gha`(M0 산출물) + 빈 매니페스트로 **사내 폴더 소스 인식만** 스모크. 저장소 무변경. 배포 태그 실제 파일명 확인 | 로컬 폴더를 소스로 등록하니 패키지 매니저에 뜨고 설치된다 |
| **M2a** | `plugin/` 솔루션 골격 + 빈 컴포넌트(툴팁 1·우클릭 1) + **`TestSurfaceBuilder` + 픽스처 지문** + 러너 확정(반나절 타임박스 → `.rhp` 폴백) | 컴포넌트가 뜨고 툴팁이 보이고, **C# 이 만든 지오메트리가 파이썬 지문과 일치**하며, 러너가 픽스처 하나를 끝까지 돌린다. **F1 도움말이 서드파티 컴포넌트에서 무엇을 보여주는지 확정**(현재 미확인) |
| **M2b** | 파이썬 선반영(신규 메시지 4 · `optBranch`/`extBranch` · T9) → 픽스처 재생성 → **`expected` 6배열 불변 확인** → Core 포팅 A→D→B→C | 각 모듈이 파이썬과 같은 값을 낸다 |
| **M3** | 어댑터 배선 + T1~T9 대조 + 툴팁·메시지·예제 4개·매뉴얼 + 자동검사 5개 | §8 완료조건 |
| **M4** *(다음 슬라이스)* | `AMv1 Inspect` 의 A~D 호출을 `.gha` 로 교체 → **`platform_path` 제거**. 역산/표시 경계 확정 | 이 문서 밖 |

**패키징 파이프라인(매니페스트·릴리스 절차)은 M3 뒤로.** M0 의 논리는 "뒤에 오는 전부가 이 위에 선다"였는데 패키징은 그 성질이 아니다 — `.gha` 가 나온 뒤의 `yak spec/build` 는 되돌리기 쉽고, 실패해도 Core 포팅이 무효가 되지 않는다. 진짜로 조기에 확인할 미지수는 **폴더 소스 인식 하나**이고 그것이 M2a-0 이다.

각 마일스톤 종료 **즉시** `docs/journal/J-014…` 부터 저널을 남긴다. 형식은 `docs/journal/README.md`.

**`.gitignore` 에 C# 규칙(`bin/`·`obj/`·`*.yak`)을 M2a 에서 추가한다** — 지금은 파이썬 기준이라 빌드 산출물이 그대로 커밋된다.

---

## 8. 완료 조건

1. `dotnet build` 로 `.gha` 가 나오고 Rhino 8 GH 캔버스에 `AMv1 Pins` 가 뜬다
2. Visual Studio 에서 중단점이 걸린다
3. 골든 픽스처 T1~T9 를 허용오차 안에서 재현하고, **플래그는 정확히 일치**한다
4. **폴백 가지 선택이 파이썬과 핀별로 일치**한다 — *커버된 가지에 한해* (§5.1)
5. **T8 중앙값 ≤ 500 ms** — 워밍업 1회 + 측정 5회 이상, **중앙값**(평균·최솟값 아님). 그리고 `info` 가 경과 ms 를 보고한다
6. **저장소를 체크아웃하지 않은 계정/PC**(최소한 빌드 폴더 삭제 + `RHINO_PACKAGE_DIRS` 해제 상태)에서 사내 소스로 설치·제거·재설치가 된다. **검증은 UI 가 아니라 `%APPDATA%\McNeel\Rhinoceros\packages\8.0\ljks-adaptive-mold\` 디스크에서** — 구버전 폴더가 남는 인정된 회귀가 있다(§6.4)
7. 도움말 자동검사 5개 통과
8. **처음 보는 사람이 예제를 열어 자기 곡면으로 바꾸고, 클램핑이 났을 때 그 사실을 화면에서 알아챈다.** 이진 판정이 아니므로 **한 사람에게 시켜 보고 어디서 멈췄는지를 저널에 적는 것**으로 대신한다

**3·4 가 실패하면 "거의 다 된 것"이 아니라 "아직 포팅이 안 된 것"이다.**

---

## 9. 리스크

| # | 리스크 | 대응 |
|---|---|---|
| 1 | `Rhino.Testing` 이 beta 이고 셋업 미검증 | M2a 에서 스모크. 폴백 in-Rhino 러너를 **산출물로** 만든다(§5.4) |
| 2 | 부동소수 차이로 픽스처 불일치 | 허용오차 조정. **플래그·가지는 예외 없음** |
| 3 | 사내 폴더 소스가 예상과 다르게 동작 | M2a-0 에서 저장소 건드리지 않고 먼저 확인 |
| 4 | 사람이 `AMv1 Pins`(C#)와 `AMv1 Inspect`(파이썬)를 혼동 | 이름·Description·예제 `05_parity.gh`. *GUID 충돌은 일어나지 않는다 — GhPython 컴포넌트는 전부 같은 클래스 GUID 를 공유한다* |
| 5 | 두 세션이 같은 Rhino 인스턴스를 쓴다 | Rhino 를 태우는 단계 전에 상대 세션 확인 |
| 6 | 파이썬 선반영(§3.6·§3.7)이 계산을 건드림 | 픽스처 재생성 후 `expected` 6배열 불변을 **먼저** 확인. 바뀌면 거기서 멈춘다 |

---

## 10. 지시서(`20_gha_csharp_port.md`)에서 고치는 곳

| § | 고침 |
|---|---|
| §2 범위 | `Yak 패키징·배포` 를 제외 → 포함. 출력 6 → 8(`nx`·`ny`) |
| §5 M1 한계표 | 폴백 가지 **5/7 → 3/7**. 미커버는 `ray-/panel`·`ray-/ext`·`closest`·`default` |
| §6 파일 목록 | `MoldSolver.cs` 추가 (근거는 §3.2) |
| §7 리스크 4 | GUID 충돌은 성립하지 않음 — 실제 위험은 사람의 혼동 |
| §8-5 | 성능 기준 "3초 이내" → **T8 중앙값 ≤ 500 ms**. 파이썬 실측이 25~49 ms 이므로 3초는 60배 회귀도 통과시킨다. **"파이썬 대비 ≤2배"도 쓰지 않는다** — 측정 잡음 자체가 2배(24.7↔48.7)이고, 분모에 파이썬 인터프리터·interop 이 섞여 있어 C# 이 정상이면 더 빨라야 하므로 천장이 무의미하다. 파이썬 실측표는 저널에 참고로만 남긴다 |
| 컴포넌트 이름 | `AdaptiveMold Pins` → `AMv1 Pins` |

---

## 11. 이 문서 밖의 일

- **M4** — `AMv1 Inspect` 를 `.gha` 위에 얹어 `platform_path` 제거 (§7)
- Phase E(3D 모델 변형) 포팅 → GhPython 완전 대체
- 로봇·툴패스·간섭·재생 계열의 C# 이전
- GhPython 7개의 툴팁을 같은 정본으로 이관
- REST 브리지·대시보드 sync 를 `.gha` 에서 직접
- 공개 배포(공개 Yak 서버·food4Rhino)와 메시지 리소스 분리(다국어)
- 픽스처 나머지 한계 해소 (`closest`·`default` 커버, 진짜 클램핑 케이스, 부호)
- `core/geometry` 구조 불일치 정리 (지시서 §6 미결)
- **베이스 탐색의 UI 얼음**(J-011 TRAP-01) — 실제로 얼리는 것은 이쪽이다

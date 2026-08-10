---
id: J-002
milestone: M1
date: 2026-08-11
project: ljk_facade_platform
tags: [rhino8, python, rayshoot, fixtures, encoding, module-cache]
---

# J-002 · M1 · 골든 픽스처 추출

> **가장 큰 발견: `RayShoot` 결함으로 이 파이프라인은 지금까지 한 번도 정상 완주한 적이 없다.**
> C# 코드를 한 줄도 쓰기 전에 포팅이 값을 했다. 계획서 §7 리스크 2가 실현됐고, 예상보다 넓었다
> (Phase D뿐 아니라 Phase B에도 같은 결함이 복제돼 있었다).
> 픽스처 8개 확보. 세션을 넘어선 재현성까지 확인.

---

## TRAP-01 `RayShoot`는 파라미터가 아니라 교점을 반환한다 ★★

- **증상:** 레이가 곡면에 맞는 즉시 죽는다.
  ```
  TypeError: Rhino.Geometry.Point3d value cannot be converted to System.Double
  in method Rhino.Geometry.Point3d PointAt(Double)
  ```
  Phase B(`optimization.py`)의 첫 그리드 포인트에서 터져 파이프라인이 시작조차 못 했다.

- **원인:** `Intersection.RayShoot(Ray3d, IEnumerable<GeometryBase>, int)`는 **교점 `Point3d[]`** 를 반환한다. 구현은 이를 곡선 파라미터로 착각해 `Ray3d.PointAt(double)`에 넘겼다.
  ```python
  t_pos = rgi.Intersection.RayShoot(ray_pos, [brep], 1)
  hit_pt = ray_pos.PointAt(t_pos[0])          # ← 점을 파라미터로 취급
  ```
  **API 모호성이 아니다.** 사양서 `01_core_geometry_adaptive_mold_v1.md:190-193`이 처음부터 올바른 형태를 명시하고 있었다.
  ```python
  hits = rg.Intersect.Intersection.RayShoot(ray, [target], 1)
  if not hits or len(hits) == 0: return None
  d = pt.DistanceTo(hits[0])                  # ← hits[0]을 점으로 바로 씀
  ```
  **구현이 자기 사양서를 어겼다.**

- **해결:** `PointAt`을 걷어내고 `pt.DistanceTo(hits[0])`로. 4곳 — `optimization.py::_ray_cast_distance` 2곳, `projection.py::_ray_cast_height` 2곳.

- **재발 조건:** RhinoCommon의 반환 타입을 이름만 보고 추정할 때. **`t`, `param` 같은 변수명을 쓰는 순간 이미 가정이 들어간 것.**
  이 결함이 오래 숨은 이유가 중요하다 — **레이가 빗나가면 `None`이 반환돼 "곡면 밖"으로 조용히 처리된다.** 맞을 때만 터지므로, 곡면이 그리드를 안 덮는 배치에서는 아무 일도 없는 것처럼 보인다.

---

## TRAP-02 Rhino의 Python 모듈 캐시는 프로세스 수명을 따른다 ★

- **증상:** `src/`의 소스를 고쳤는데 재실행해도 옛 동작 그대로. 같은 줄에서 같은 오류.
- **원인:** Rhino의 Python 인터프리터가 `sys.modules`를 **Rhino 프로세스가 살아 있는 동안** 유지한다. ScriptEditor를 닫았다 열어도 인터프리터 상태는 프로세스에 묶여 있어 지워지지 않는다.
- **해결:** 두 가지. **Rhino 완전 재시작**(확실), 또는 스크립트가 직접 캐시를 비우기.
  ```python
  # 이름으로 지우면 stdlib의 동명 모듈(utils 등)까지 날아간다.
  # __file__ 경로가 SRC_DIR 아래인 것만 지울 것.
  for name in list(sys.modules):
      path = getattr(sys.modules.get(name), "__file__", None)
      if path and normcase(normpath(path)).startswith(src_norm):
          del sys.modules[name]
  ```
- **재발 조건:** **Rhino 안에서 개발 중인 Python 모듈을 수정할 때마다.** sketch2cad, howick GH 어댑터에서도 그대로 만난다.

---

## TRAP-03 `open(..., "w")`가 한국어 Windows에서 cp949로 잡힌다

- **증상:** `UnicodeEncodeError: 'cp949' codec can't encode character '—'`. em dash(`—`)가 든 로그를 쓰다 죽었다. 파이프라인은 다 돌고 **맨 마지막 로그 기록에서만** 터져서, 정작 픽스처 8개는 이미 정상 기록돼 있었다.
- **원인:** Python의 `open()` 기본 인코딩이 로캘을 따른다. 한국어 Windows는 cp949.
- **해결:** `open(path, "w", encoding="utf-8")`. **예외 처리 안의 로그 쓰기도 같이 고칠 것** — 거기서 또 터지면 원인이 가려진다.
- **재발 조건:** 이 PC에서 파일을 쓰는 모든 Python 코드. `json.dump`는 기본이 `ensure_ascii=True`라 살아남지만 의존하지 말 것.

---

## TRAP-04 `/runscript=`에 따옴표 박힌 경로를 넣으면 인자가 쪼개진다

- **증상:** `Rhino.exe /netcore "/runscript=_-RunPythonScript \"<path>\" _Enter"` 로 띄우니 **Rhino가 `.py`를 열려고 하다 "지원하지 않는 파일 형식" 오류.**
- **원인:** 내부 따옴표 때문에 경로가 별개 argv로 떨어져 나가, Rhino가 그것을 "열어야 할 문서"로 받았다.
- **해결:** 이번엔 우회했다 — ScriptEditor에서 수동 실행. **자동 실행 형태는 미검증.**
- **재발 조건:** Rhino를 명령줄로 자동화할 때. 경로에 공백이 없으면 따옴표를 빼고 시도할 것.

---

## DECISION-01 `RayShoot` 결함은 박제가 아니라 수정한다

- **선택:** M1의 원칙("현재 동작을 있는 그대로 박제")을 이 건에 한해 적용하지 않고 수정했다.
- **근거:** **박제할 동작이 없다.** 코드가 예외로 죽으므로 픽스처를 뽑을 수 없고, 포팅 대상 자체가 성립하지 않는다. 그리고 사양서가 올바른 형태를 명시하고 있어 "무엇이 맞는가"에 판단 여지가 없었다.
- **기각한 대안:**
  - **원본 그대로 두고 픽스처 못 뽑음** — M1·M2가 통째로 막힌다.
  - **C# 쪽에서만 올바르게 구현** — Python과 대조가 불가능해져 포팅 검증이라는 목적이 사라진다.
- **뒤집을 조건:** 없음. 다만 **이 수정으로 Python의 출력이 과거와 달라졌다**는 점은 기억할 것 — 과거 출력은 "예외"였으므로 회귀는 아니다.

---

## DECISION-02 진단은 반환 타입 변경이 아니라 선택적 출력 파라미터로

- **선택:** `calculate_heights(..., branch_out=None)`. 리스트를 넘기면 채우고, 안 넘기면 아무 일도 안 한다.
- **근거:** `calculate_heights`는 4곳에서 호출된다(본체 1 + `test_projection.py` 3). 3-튜플을 4-튜플로 바꾸면 기존 테스트가 전부 깨진다. **진단 추가가 기존 코드를 깨뜨리면 안 된다.**
- **기각한 대안:**
  - **4-튜플 반환** — 호출부 4곳 수정 필요. 진단 하나 넣자고 공개 시그니처를 바꿀 이유가 없다.
  - **모듈 전역에 마지막 실행 진단 저장** — 전역 상태. 재진입·동시성에 취약하고 추적이 어렵다.
- **뒤집을 조건:** 진단이 기본 동작이 되어야 할 때(예: GH 출력에 상시 노출).

---

## DECISION-03 픽스처에 지오메트리 대신 생성 파라미터를 기록

- **선택:** `{"kind": "hemisphere", "radius": 400.0, "center_z": 0.0}` 형태로 저장. C# 쪽이 같은 RhinoCommon 호출로 재구성한다.
- **근거:** Brep 직렬화는 무겁고 버전에 취약하다. 테스트 곡면이 전부 `PlaneSurface`/`Sphere` 같은 단순 프리미티브라 파라미터만으로 정확히 재현된다.
- **기각한 대안:** **3dm/JSON으로 Brep 직렬화** — 파일이 커지고, Rhino 버전이 바뀌면 재현성을 장담할 수 없다.
- **뒤집을 조건:** 실제 프로젝트 곡면(임의 NURBS)으로 픽스처를 만들 때. 그때는 `.3dm` 첨부가 불가피하다.

---

## FACT-01 이 파이프라인은 한 번도 정상 완주한 적이 없다 ★

- **측정값:** 수정 전 T1(가장 단순한 평면)조차 Phase B 첫 그리드 포인트에서 `TypeError`. 수정 후 8/8 완주.
- **측정 방법:** `dump_fixtures.py`를 Rhino 8.33 CPython 3에서 실행.
- **유효 범위:** `adaptive_mold/src` 현재 상태. `adaptive_mold/tests/`도 같은 경로를 타므로 **그 테스트들 역시 실제로 통과한 적이 없다**고 보는 것이 타당하다(미검증 — 실행 이력이 없어 확인 불가).

## FACT-02 폴백 가지 커버리지 — 7개 중 5개

- **측정값:**

  | 케이스 | 핀 | clamp | ext | 탄 가지 |
  |---|---|---|---|---|
  | T1_flat_parallel | 36 | 0 | 0 | `ray+/panel`=36 |
  | T2_tilted | 36 | **18** | 6 | `ray-/panel`=30, `ray-/ext`=6 |
  | T3_hemisphere | 36 | **20** | 24 | `tangent`=24, `ray+/panel`=12 |
  | T4_small_surface | 36 | 0 | 32 | `ray+/panel`=4, `ray+/ext`=32 |
  | T5_deep_clamp | 36 | 0 | 0 | `ray+/panel`=36 |
  | T6_flat_150 | 36 | 0 | 0 | `ray+/panel`=36 |
  | T7_rotated_base_plane | 36 | 0 | 3 | `ray+/panel`=33, `ray+/ext`=3 |
  | T8_large_grid | 121 | 0 | 0 | `ray+/panel`=121 |

- **커버 안 된 가지: `closest`, `default`.** T1~T8로는 한 번도 안 탄다.
- **유효 범위:** **이 픽스처는 그 두 가지에 대해 아무것도 보증하지 못한다.** C# 포팅본이 거기서 갈라져도 못 잡는다. M3 대조 시 한계로 명시할 것.

## FACT-03 세션을 넘어선 재현성 확인

- **측정값:** 8개 픽스처 파일 크기가 **Rhino 재시작 전후 실행에서 바이트 단위로 동일.** 추가로 스크립트가 각 케이스를 2회 실행해 `pin_heights`·`clamp_flags`·`extension_flags`·`branch_taken`을 대조, 전부 일치할 때만 기록했다.
- **측정 방법:** 크기 비교 + 스크립트 내장 2회 대조.
- **유효 범위:** Rhino 8.33, 같은 PC. 다른 PC·다른 Rhino 버전에서의 재현성은 미검증.

## FACT-04 T2에서 절반이 클램핑 — 의도와 어긋남

- **측정값:** T2(10° 기울어진 평면) `clamp=18/36`. 30개 핀이 **아래 방향 레이**(`ray-/panel`)로 높이를 구했다 — 최적화 후 곡면이 그리드 평면 아래로 내려갔다는 뜻.
- **측정 방법:** 픽스처 `summary.branch_counts` 및 `clamped`.
- **유효 범위:** 문서상 T2의 의도는 "optimization 후 높이 균일화"인데 결과가 정반대다. **정상인지 결함인지 미판정 — 도메인 판단 필요.**

  기존 테스트가 이를 통과시키는 이유도 확인됐다:
  ```python
  def test_T2_tilted():
      assert len(r.pin_heights) == 36        # 개수만
      assert r.positioned_srf is not None    # None 아님만
  ```
  **높이를 아무것도 검증하지 않는다.** 계획서 §4의 "기존 테스트는 정답지가 될 수 없다"가 실물로 확인됐다.

  관련 관찰: `_ray_cast_height`는 `pt.DistanceTo(...)`로 **항상 양수**를 돌려준다. `_closest_point_height`도 `abs()`를 쓴다. **부호가 설계상 버려지므로 곡면이 그리드 아래에 있어도 양의 높이가 나온다.**

---

## PROCEDURE-01 픽스처 재생성

- **목적:** Python 파이프라인이 바뀌었을 때 정답지를 다시 뽑는다.
- **단계:**
  1. Rhino 8 실행 (`/netcore`)
  2. `ScriptEditor` → `adaptive_mold/tools/dump_fixtures.py` 열기 → Run
  3. 출력 첫머리의 `모듈 캐시 비움:` 목록에 수정한 모듈이 있는지 확인
  4. `전 케이스 재현 확인` 메시지 확인 — 하나라도 재현 실패면 **거기서 멈춘다**
  5. `git diff plugin/fixtures/` 로 값이 왜 바뀌었는지 설명 가능한지 확인
- **자동화 후보:** **부분적.** 2번이 GUI 조작이라 남는다. TRAP-04의 `/runscript` 자동 실행이 풀리면 전 구간 자동화 가능.

---

## 미해결

- **T2의 clamp=18이 정상인가** (FACT-04). 도메인 판단 대기. **정상이면 픽스처 확정하고 M2로, 이상하면 Phase B를 먼저 본다.**
- **`closest`·`default` 가지 미커버** (FACT-02). 두 가지를 타는 케이스를 추가할지, 한계로 두고 갈지.
- 기존 `adaptive_mold/tests/`가 실제로 실행된 적 있는지 — 확인 불가.
- TRAP-04 `/runscript` 자동 실행 — 미검증.

---

## 승격 후보

| 항목 | 이유 |
|---|---|
| **TRAP-02 Rhino 모듈 캐시** | Rhino에서 Python 개발하면 무조건 만난다. sketch2cad·howick에 즉시 적용 |
| **TRAP-01 `RayShoot` 반환 타입** | RhinoCommon 일반. "반환 타입을 이름으로 추정하지 말 것"이라는 더 넓은 교훈 포함 |
| **TRAP-03 cp949 인코딩** | 이 PC의 모든 Python 파일 쓰기에 해당. Rhino와 무관하게 일반적 |
| DECISION-03 픽스처에 생성 파라미터 | 지오메트리 골든 테스트 일반 패턴 |
| TRAP-04 `/runscript` 따옴표 | 검증되면 승격 |

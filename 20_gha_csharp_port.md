# 20. Adaptive Mold — C# `.gha` 플러그인 포팅 지시서

> 20번대 = **네이티브 플러그인 트랙**. 00번 마스터 문서 §2.1 "Core/Adapter 분리"의 예고편 —
> *"나중에 .gha (C#) 컴파일이 필요해지면 `core/`는 그대로 두고 어댑터만 교체"* — 를 실행하는 문서입니다.

---

## 1. 목적

지금 역산기는 **GhPython 컴포넌트**로 돌아갑니다. 알고리즘은 완성됐지만 전달 방식에 한계가 있습니다.

| 지금 (GhPython) | `.gha` 이후 |
|---|---|
| `sys.path.insert(r"C:\...")` 절대경로 하드코딩 | 없음 |
| 컴포넌트에 코드 붙여넣기, 파일 동기화 수동 | 설치 한 번 |
| 남에게 주려면 저장소 통째 + 경로 설정 | `.gha` 파일 하나 |
| 디버거 못 붙임 — `print`로 추적 | Visual Studio 중단점 |
| 입출력 11개를 GH에서 수동 배선 | 코드에 선언 |

**이 포팅의 목적은 알고리즘 개선이 아닙니다.** 같은 결과를 배포 가능한 형태로 옮기는 것이고, 따라서 성공 기준은 "더 좋아졌다"가 아니라 **"똑같다"** 입니다.

---

## 2. 범위

**Phase A~D만.** 곡면과 파라미터를 받아 **핀 높이까지** 산출합니다.

| 포함 | 제외 |
|---|---|
| A 그리드 생성 (`grid.py`) | **E 3D 모델 변형** (`transformation.py`) |
| B 곡면 정렬 (`optimization.py`) | REST 브리지 연동 |
| C 곡면 확장 (`extension.py`) | 대시보드 sync |
| D 높이 산출·클램핑 (`projection.py`) | Yak 패키징·배포 |

Phase E(housing/rod/top 배치)는 **당분간 GhPython에 남겨둡니다.** Brep 변형과 모델링 규약(원점+Z, `rod_base_length` 스케일)이 얹히면 첫 플러그인에서 통제할 변수가 너무 많아집니다. A~D가 검증되면 E는 코드 추가일 뿐 새로 배울 것이 없습니다.

### 컴포넌트 사양

| 입력 (8) | 출력 (6) |
|---|---|
| `target_srf`, `base_plane`, `width`, `length`, `spacing`, `max_height`, `min_height`, `compute` | `pin_heights`, `pin_tops`, `grid_pts`, `clamp_flags`, `extension_flags`, `info` |

인덱싱은 Python 규약 `idx = j * nx + i`를 **그대로** 유지합니다. 여기서 순서가 바뀌면 이후 모든 대조가 무의미해집니다.

---

## 3. 확정된 환경 (2026-08-10 실측)

| 항목 | 값 |
|---|---|
| Rhino 8 | 8.32.26160.13001 |
| .NET 플레이버 | `System\netcore\RhinoCommon.dll` 존재 → **netcore 경로 사용** |
| 타겟 프레임워크 | **`net7.0-windows`** |
| .NET 런타임 | 7.0.0 설치됨 (Rhino 8이 설치) |
| .NET SDK | **9.0.201 하나뿐** |
| Visual Studio | 2022 Community |
| `Rhino.Templates` | **미설치** → `dotnet new install Rhino.Templates` |

**어셈블리 참조는 NuGet(`RhinoCommon`, `Grasshopper`)으로 합니다.** `C:\Program Files\Rhino 8\...`의 DLL을 직접 파일 참조하지 않습니다 — 절대경로가 프로젝트에 박히면 다른 PC·다른 Rhino 버전에서 그대로 깨집니다. 지금 GhPython이 `sys.path.insert`로 앓고 있는 것과 같은 병입니다.

**개발 루프:** Rhino의 `GrasshopperDeveloperSettings` 명령으로 빌드 출력 폴더를 등록하면 GH가 그 폴더의 `.gha`를 직접 읽습니다. 파일 복사 절차가 없고, VS에서 F5로 Rhino를 띄우면 중단점이 걸립니다.

---

## 4. 선결 문제 — 정답지가 없다

`adaptive_mold/tests/`는 **pytest가 아니라 Rhino 안에서 도는 속성 검사**입니다. 그리고 검사하는 것이 이렇습니다:

```python
assert len(r.pin_heights) == 36     # 개수
assert n_clamp == 0                  # 클램핑 없음
assert len(h_set) <= 2               # "대충 다 같은 높이"
```

**핀 높이의 실제 숫자를 검증하는 곳이 한 군데도 없습니다.** C# 포팅본이 36개를 뱉고 클램핑이 0이면 이 테스트는 전부 통과하는데, 높이가 187.3이든 203.9든 잡아내지 못합니다.

따라서 **포팅보다 먼저 정답지를 만들어야 합니다.** 이 순서를 뒤집으면 "돌아가는 것"과 "맞는 것"을 구별할 수단 없이 포팅하게 됩니다.

### 4.1 골든 픽스처

Python 파이프라인을 Rhino에서 한 번 돌려 출력을 JSON으로 고정합니다.

```
plugin/fixtures/T3_hemisphere.json
{
  "input":  { "surface": "...", "width": 1000, "spacing": 200, ... },
  "pin_heights":     [...],
  "clamp_flags":     [...],
  "extension_flags": [...],
  "branch_taken":    [...]      ← 4.2 참조
}
```

케이스는 기존 T1~T8을 그대로 씁니다 — 평면 / 10° 경사면 / 반구 / 작은 곡면 / 깊은 클램프 / 회전 베이스평면 / 11×11(121핀).

**대조 기준:**

| 항목 | 허용오차 |
|---|---|
| `pin_heights` | 1e-6 mm에서 시작, 실측 후 조정 |
| `clamp_flags` · `extension_flags` | **정확히 일치** |
| `branch_taken` | **정확히 일치** |

불리언이 어긋나면 알고리즘이 다른 가지를 탄 것입니다. **오차 조정으로 덮으면 안 됩니다.**

### 4.2 폴백 가지를 기록해야 하는 이유

Phase D는 높이 하나를 구하는 데 폴백이 4단계입니다:

```
RayShoot(+법선) → 실패 시 RayShoot(-법선)
  → 실패 시 tangent_extrapolate
    → 실패 시 ClosestPoint 투영
      → 그래도 실패 시 (min+max)/2
```

각 단계는 곡면 경계와 tolerance에 따라 갈리는데, **어느 가지를 탔는지가 출력에 남지 않습니다.** C# 포팅본이 다른 가지를 타도 숫자가 비슷하면 모르고 지나갑니다.

그래서 **Python 쪽에 핀별 `branch_taken` 진단 출력을 추가**하고 픽스처에 함께 덤프합니다. 이것 없이는 포팅 검증이 성립하지 않습니다.

---

## 5. 작업 순서

### M0 — 툴체인 스모크테스트

빈 `.gha` 하나를 Rhino 8에 띄웁니다. **저장소는 건드리지 않고 스크래치에서** 합니다.

**진짜 확인할 질문: SDK 9.0.201로 `net7.0`이 빌드되는가.** 참조 팩 복원이 매끄러운지 실측되지 않았습니다. 막히면 .NET 7 SDK 추가 설치 또는 `net7.0;net48` 멀티타겟으로 대응합니다. **환경이 안 되는 걸 나중에 발견하는 것이 가장 비싸므로 이것이 첫 관문입니다.**

- [ ] `dotnet new install Rhino.Templates`
- [ ] 템플릿으로 GH 플러그인 생성 → `dotnet build` 성공
- [ ] `GrasshopperDeveloperSettings`에 출력 폴더 등록 → GH 캔버스에 컴포넌트 등장
- [ ] VS에서 F5 → Rhino 기동 → 중단점 정지 확인

### M1 — 골든 픽스처 추출

- [ ] `projection.py`에 `branch_taken` 진단 출력 추가 (기존 동작 불변)
- [ ] T1~T8을 Rhino에서 실행해 JSON 덤프하는 스크립트 작성
- [ ] `plugin/fixtures/*.json` 커밋
- [ ] 픽스처 재생성이 재현 가능한지 확인 — **두 번 돌려 같은 값이 나와야 함**

재현되지 않으면 그 시점에 멈춥니다. 비결정적 출력은 정답지가 될 수 없습니다.

### M2 — Core 포팅 (A~D)

Python 모듈 경계를 1:1로 유지합니다. 나중에 대조하기 쉽게 하기 위해서입니다.

- [ ] `Grid.cs` ← `grid.py`
- [ ] `Optimization.cs` ← `optimization.py`
- [ ] `Extension.cs` ← `extension.py`
- [ ] `Projection.cs` ← `projection.py` — **가장 위험, 4.2 참조**
- [ ] `MoldResult.cs` — 출력 묶음

### M3 — GH 컴포넌트 + 검증

- [ ] `AdaptiveMoldPinsComponent.cs` (입력 8 / 출력 6)
- [ ] 픽스처 대조 테스트 — T1~T8 전부
- [ ] 성능: 11×11(121핀) 3초 이내 (기존 T8 기준)

---

## 6. 코드 배치

```
plugin/                          # ★ 신규 — C# 전용 최상위
├── AdaptiveMold.Core/           # 순수 C#, Grasshopper 참조 없음
│   ├── Grid.cs
│   ├── Optimization.cs
│   ├── Extension.cs
│   ├── Projection.cs
│   └── MoldResult.cs
├── AdaptiveMold.GH/             # .gha — 얇은 어댑터
│   ├── AdaptiveMoldPinsComponent.cs
│   └── AdaptiveMoldInfo.cs
├── AdaptiveMold.Tests/          # 픽스처 대조
└── fixtures/*.json
```

**`Core`는 Grasshopper를 참조하지 않습니다.** RhinoCommon만 씁니다. 그래야 테스트가 GH 없이 돌고, 나중에 Rhino 명령이나 REST 서버에서 같은 코어를 재사용할 수 있습니다. 00번 문서 §2.1이 요구하는 구조를 그대로 물려받는 것입니다.

**왜 `core/`가 아니라 `plugin/`인가:** `pyproject.toml`이 `include = ["api*", "core*", "gh_components*"]`로 `core/`를 **Python 패키지로 잡고 있습니다.** 여기에 C# 프로젝트를 넣으면 setuptools 패키징이 꼬입니다. 언어가 다르면 최상위를 나누는 편이 낫습니다.

> **미결 사항:** 00번 문서는 `core/geometry/`에 `grid.py`·`projection.py`가 있어야 한다고 하지만, 실제 코드는 `adaptive_mold/src/`에 있고 `core/geometry/`는 docstring만 있는 빈 스텁입니다. 이 불일치는 이 포팅의 범위 밖이지만, **Python 쪽을 정리할지 문서를 현실에 맞출지 언젠가 정해야 합니다.**

---

## 7. 알려진 리스크

| # | 리스크 | 대응 |
|---|---|---|
| 1 | SDK 9로 `net7.0` 빌드 실패 | M0에서 먼저 확인. .NET 7 SDK 설치 또는 멀티타겟 |
| 2 | **`RayShoot` 오버로드 불일치** — 아래 참조 | M2에서 실측 확인 후 보고 |
| 3 | 기하 연산 부동소수 차이로 픽스처 불일치 | 허용오차 조정. 단 **플래그·가지는 예외 없음** |
| 4 | GhPython과 `.gha`가 같은 GH에서 이름 충돌 | 컴포넌트 이름·GUID를 다르게 (`AdaptiveMold Pins`) |

### 리스크 2 상세

`projection.py`의 호출이 이렇습니다:

```python
t_pos = rgi.Intersection.RayShoot(ray_pos, [brep], 1)
hit_pt = ray_pos.PointAt(t_pos[0])       # t_pos[0]을 곡선 파라미터로 취급
```

RhinoCommon의 `RayShoot` 오버로드에 따라 반환이 **파라미터가 아니라 교점(`Point3d`)** 일 수 있습니다. Python은 느슨해서 넘어가지만 **C#은 컴파일 단계에서 걸립니다.**

만약 실제로 그렇다면 **이 폴백 가지는 현재 Python에서 정상 동작하지 않고 있을 가능성**이 있습니다. 즉 포팅이 기존 버그를 찾아내는 셈입니다. 현 시점에서는 **미검증**이며, M2에서 실측으로 확인하고 결과를 이 문서에 반영합니다.

---

## 8. 완료 조건

이 다섯이 전부 참일 때 끝난 것입니다.

1. `dotnet build`로 `.gha`가 나오고 Rhino 8 GH 캔버스에 컴포넌트가 뜬다
2. Visual Studio에서 중단점이 걸린다
3. 골든 픽스처 T1~T8을 허용오차 안에서 재현하고, **플래그는 정확히 일치**한다
4. **폴백 가지 선택이 Python과 핀별로 일치**한다
5. 11×11(121핀)이 3초 이내

**3·4가 실패하면 "거의 다 된 것"이 아니라 "아직 포팅이 안 된 것"입니다.**

---

## 9. 이 문서 밖의 일

다음은 A~D 슬라이스가 끝난 뒤 별도로 다룹니다.

- Phase E(3D 모델 변형) 포팅 → GhPython 완전 대체
- REST 브리지·대시보드 sync를 `.gha`에서 직접
- Yak 패키징, food4Rhino 배포
- Rhino 명령(`.rhp`) 형태 제공
- `core/geometry` 구조 불일치 정리 (§6 미결 사항)

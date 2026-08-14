# AMv1 — `.gha` 포팅과 사내 패키지 배포 설계

- 날짜: 2026-08-14
- 브랜치: `feature/gha-port` (worktree `../26_AdaptiveMold_amv1`)
- 선행 문서: [`20_gha_csharp_port.md`](../../../20_gha_csharp_port.md) — 이 문서는 그 지시서의 **M2·M3 실행 설계**이며, §2·§9 를 한 군데 고칩니다.

---

## 1. 목적

핀 몰드 역산기(Phase A~D)를 GhPython 에서 C# `.gha` 로 옮기고, **Rhino 패키지 매니저에서 설치되는 사내 패키지**로 배포한다.

성공 기준은 지시서 §1 과 같다 — **"더 좋아졌다"가 아니라 "똑같다"**. 알고리즘은 건드리지 않는다.

### 왜 지금 패키징까지 묶는가

지금 컴포넌트는 `sys.path.insert(r"C:\Users\leeja\Documents\dev\26_AdaptiveMold_development")` 로 저장소 절대경로를 물고 있다. 남의 PC 에 그 경로가 없으므로 **현재 형태로는 배포가 불가능하다.** 배포 가능성은 `.gha` 포팅의 부산물이 아니라 그 목적이다.

---

## 2. 범위

| 포함 | 제외 |
|---|---|
| Phase A 그리드 (`grid.py`) | **Phase E 3D 모델 변형** (`transformation.py`) |
| Phase B 곡면 정렬 (`optimization.py`) | REST 브리지·대시보드 sync |
| Phase C 곡면 확장 (`extension.py`) | 로봇·툴패스·간섭·재생 계열(`robot*.py`, `toolpath.py`, `collision.py`, `mechanics.py`, `base_search.py`, `playback.py`) |
| Phase D 높이 산출·클램핑 (`projection.py`) | 공개 배포(food4Rhino·공개 Yak 서버) |
| 공용 유틸 중 A~D 가 쓰는 것 (`utils.py`) | Rhino 명령(`.rhp`) 형태 |
| **Yak 패키징 + 사내 폴더 소스 배포** | |

**지시서 §2 변경:** `Yak 패키징·배포`를 제외 목록에서 **포함으로 옮긴다.** 근거는 §4.

포팅 대상 규모(실측): `grid.py` 102 · `optimization.py` 201 · `extension.py` 154 · `projection.py` 176 · `utils.py` 159 · `adaptive_mold_v1.py` 249 = **1,041 줄**.

---

## 3. 구조

지시서 §6 의 배치를 그대로 따른다. `pyproject.toml` 이 `core/` 를 파이썬 패키지로 잡고 있으므로 C# 은 최상위 `plugin/` 에 둔다.

```
plugin/
├── LjksAdaptiveMold.sln
├── AdaptiveMold.Core/           # 순수 C#. Grasshopper 미참조, RhinoCommon 만
│   ├── Grid.cs
│   ├── Optimization.cs
│   ├── Extension.cs
│   ├── Projection.cs
│   ├── MoldSolver.cs            # adaptive_mold_v1.run_adaptive_mold 에 대응
│   └── MoldResult.cs
├── AdaptiveMold.GH/             # .gha — 얇은 어댑터
│   ├── AdaptiveMoldPinsComponent.cs
│   └── AdaptiveMoldInfo.cs
├── AdaptiveMold.Tests/          # 골든 픽스처 대조
├── package/                     # Yak 매니페스트·빌드 산출물 (§4)
│   └── manifest.yml
└── fixtures/*.json              # 기존 T1~T8 (이미 있음)
```

**경계의 근거:** `Core` 가 Grasshopper 를 참조하지 않으면 ⑴ 테스트가 GH 없이 돌고 ⑵ 나중에 Rhino 명령이나 REST 서버가 같은 코어를 재사용할 수 있다. 00번 문서 §2.1 의 Core/Adapter 분리를 그대로 물려받는다.

**모듈 경계는 파이썬과 1:1 로 유지한다.** 합치거나 나누면 대조가 어려워진다. C# 관례상 이름만 바꾼다(`compute_grid_counts` → `Grid.ComputeCounts`).

> **지시서 §6 에서 하나 늘어난 것:** 지시서의 M2 파일 목록은 5개(`Grid`·`Optimization`·`Extension`·`Projection`·`MoldResult`)인데, `adaptive_mold_v1.run_adaptive_mold` 가 하는 **단계 조립·검증·리포트 생성**이 갈 곳이 없다. 어댑터에 넣으면 `Core` 만으로는 파이프라인을 못 돌려 테스트가 GH 를 필요로 하게 된다. 그래서 `MoldSolver.cs` 를 둔다.

### 인덱싱

`idx = j * nx + i` 를 **그대로** 유지한다. 여기서 순서가 바뀌면 픽스처 대조가 전부 무의미해진다.

### 컴포넌트 인터페이스 (지시서 §2 와 동일)

| 입력 (8) | 출력 (6) |
|---|---|
| `target_srf`, `base_plane`, `width`, `length`, `spacing`, `max_height`, `min_height`, `compute` | `pin_heights`, `pin_tops`, `grid_pts`, `clamp_flags`, `extension_flags`, `info` |

컴포넌트 이름은 `AdaptiveMold Pins`, GUID 는 새로 발급한다 — 기존 GhPython 컴포넌트와 같은 GH 세션에 공존해야 하므로 이름·GUID 가 겹치면 안 된다(지시서 §7 리스크 4).

### 데이터 흐름

```
target_srf, base_plane, width, length, spacing
      │
      ├─ A  Grid.Build          → grid_pts (nx*ny)
      ├─ B  Optimization        → positioned_srf  (평면피팅 정렬)
      ├─ C  Extension           → extended_srf    (경계 밖 확장)
      └─ D  Projection          → heights, clampFlags, extensionFlags, branchTaken
                                   min_height / max_height 로 클램핑
      ↓
   MoldResult  →  GH 어댑터가 출력 6개로 편다
```

`branch_taken` 은 파이썬 쪽에 이미 있는 진단 출력이다(M1 에서 추가됨). **Core 에서도 핀별로 남긴다.** 이것 없이는 폴백 가지 일치를 검증할 수 없다(지시서 §4.2).

### 오류 처리

파이썬은 `component.AddRuntimeMessage` 로 경고를 올린다(`utils.add_warning`). C# 어댑터도 같은 자리에서 같은 등급으로 올린다 — **메시지 등급이 달라지면 사용자가 보는 것이 달라진다.**

`Core` 는 GH 를 모르므로 메시지를 **던지지 않고 `MoldResult` 에 모아서 돌려준다.** 어댑터가 그것을 GH 런타임 메시지로 번역한다. 이 방향이면 Core 테스트가 경고까지 검증할 수 있다.

---

## 4. 배포 설계 — 서버를 만들지 않는다

### 실측 근거

- `yak.exe` 는 이 PC 에 이미 있다: `C:\Program Files\Rhino 8\System\yak.exe` — **Yak 0.15.2 / Rhino 8.33.26188.13001**.
- `yak push` · `search` · `install` 이 전부 `-s, --source URL` 을 받는다 (기본값 `https://yak.rhino3d.com/`).
- Rhino 쪽은 **Options > Advanced 의 `Rhino.Options.PackageManager.Sources`** 에 세미콜론으로 소스를 추가한다.
- 공식 문서: **커스텀 저장소는 `.yak` 파일이 들어 있는 폴더일 뿐이다.** `Directory.EnumerateFiles` 가 받는 것 — 일반 경로·매핑 드라이브·UNC·마운트 공유 — 이면 된다. Rhino 8.15+ 는 `yak cache` 로 인덱스를 만들어 느린 네트워크를 덮는다.

### 결정

**자체 Yak 서버를 구현하지 않는다.** 서버 API 스펙이 공개돼 있지 않아 비싸고, 폴더 소스로 같은 목적이 달성된다.

- **채택:** 배포본 `.yak` 을 work.ljks.io 에 두고, 각 PC 는 **로컬 폴더 하나**(`%LOCALAPPDATA%\LJKS\packages`)를 소스로 등록한다. 설치는 그 폴더로 내려받는 것뿐 — 인터넷 너머에서 되고 공유·방화벽 설정이 필요 없다.
- **기각 1 — 사내 NAS UNC 를 소스로 직접:** 동기화 단계가 없어 더 단순하지만 사무실 밖에서 안 된다. 나중에 사무실 전용으로 쓰고 싶으면 소스 문자열 하나 추가로 병행 가능하다.
- **기각 2 — 자체 yak 서버:** 위 근거.
- **뒤집을 조건:** 사외 공개가 필요해지면 같은 `.yak` 을 공개 서버로 `push` 만 하면 된다. 산출물은 바뀌지 않는다.

**미검증:** 정적 HTTPS 폴더를 소스 URL 로 직접 물릴 수 있는지는 확인되지 않았다(문서의 URL 예시는 진짜 API 를 쓰는 공식 서버다). **이 설계는 URL 소스에 기대지 않는다.**

### 패키지 사양

| 항목 | 값 |
|---|---|
| id | `ljks-adaptive-mold` |
| 배포 태그 | `rh8-win` |
| 내용물 | `AdaptiveMold.GH.gha` + `AdaptiveMold.Core.dll` |
| 타겟 프레임워크 | `net7.0-windows` (지시서 §3.1 — `net8.0` 은 구형 Rhino 8 에서 깨진다) |

버전은 `MoldResult` 가 아니라 **어셈블리 버전 하나를 정본**으로 삼고 매니페스트가 그것을 따라간다. 두 곳에 손으로 적으면 반드시 어긋난다.

---

## 5. 테스트 전략

### 정답지

`plugin/fixtures/T1~T8.json` (M1 에서 확정, 커밋됨). 구조는 `case` / `note` / `input`(surface·base_plane·params) / `expected` / `summary` / `meta` 이고, `expected` 에 핀별 배열 **6개**가 들어 있다 — `pin_heights` · `clamp_flags` · `extension_flags` · `branch_taken` · `pin_tops` · `grid_pts`.

대조 기준은 지시서 §4.1:

| 항목 | 허용 |
|---|---|
| `pin_heights` | 1e-6 mm 에서 시작, 실측 후 조정 |
| `clamp_flags` · `extension_flags` | **정확히 일치** |
| `branch_taken` | **정확히 일치** |

**불리언·가지가 어긋나면 허용오차로 덮지 않는다.** 다른 가지를 탄 것이므로 포팅이 안 된 것이다.

### 러너 — 여기가 실제 미확정이다

RhinoCommon 기하 연산을 Rhino 밖에서 태워야 한다.

- **1순위 `Rhino.Testing` NuGet.** 실재 확인됨 — Rhino 8 계열 최신 **`8.0.28-beta`**. 다만 **모든 공개 버전이 `-beta`** 이고, Rhino 설치·라이선스 요건은 **미검증**이다.
- **폴백:** `rhinomcp` 브리지로 Rhino 안에서 대조를 태우고 결과를 JSON 으로 받는다. 픽스처 생성(`dump_via_bridge.py`)에서 이미 검증된 경로다.

**그래서 M2a 에서 빈 컴포넌트와 함께 러너도 같이 스모크한다.** 알맹이가 든 뒤에 러너가 안 된다는 걸 알면 비싸다.

### TDD 순서

Core 모듈마다 **픽스처에서 뽑은 케이스로 실패하는 테스트를 먼저 쓰고** 포팅한다. 단계별로 픽스처가 무엇을 덮는지가 다르다:

| 단계 | 픽스처 대조 |
|---|---|
| A `Grid` | **직접 된다** — `expected.grid_pts` 가 핀별 좌표를 담고 있다 |
| B `Optimization` · C `Extension` | **중간 산출물(정렬·확장된 곡면)이 픽스처에 없다.** 최종 출력으로만 간접 검증되므로, 포팅 중에는 파이썬과 같은 중간값이 나오는지 임시 덤프로 대조한다 |
| D `Projection` | **직접 된다** — `pin_heights`·`clamp_flags`·`extension_flags`·`branch_taken`·`pin_tops` |

B·C 를 임시 덤프로 확인하는 것은 **개발 중 수단이지 회귀 테스트가 아니다.** 남길 값이 있다고 판단되면 그때 파이썬 쪽 픽스처를 늘린다(§5 마지막 문단의 제약이 그대로 걸린다).

### 픽스처의 알려진 한계 (M1 에서 M3 로 넘어온 것)

| 한계 | 내용 |
|---|---|
| 폴백 가지 5/7 | `closest`·`default` 를 T1~T8 이 한 번도 타지 않는다 — 그 두 가지는 대조로 검증되지 않는다 |
| 클램핑 케이스 1개 | `T5_deep_clamp` 는 실제로 클램핑을 안 한다(Phase B 가 곡면을 stroke 중앙 100.0 으로 옮겨 `clamp=0`). 클램핑을 태우는 것은 T3 뿐 |
| 부호 | 높이가 `DistanceTo`/`abs()` 라 항상 양수. 곡면이 그리드 아래여도 양수 |

**이 한계를 이번 슬라이스에서 없애지 않는다.** 포팅의 성공 기준은 "파이썬과 같다"이지 "옳다"가 아니다. 픽스처를 늘리는 것은 별도 작업이며, 늘리면 파이썬 쪽 정답지부터 다시 뽑아야 한다.

---

## 6. 작업 순서

| | 내용 | 끝났다고 말할 수 있는 조건 |
|---|---|---|
| **M2a** | `plugin/` 솔루션 골격 + 빈 컴포넌트 + Yak 파이프라인 + 테스트 러너 스모크 | 다른(또는 같은) PC 의 패키지 매니저에 `ljks-adaptive-mold` 가 뜨고, 설치하면 GH 캔버스에 컴포넌트가 나온다 |
| **M2b** | Core 포팅 — Grid → Optimization → Extension → Projection → MoldSolver | 각 모듈이 파이썬과 같은 값을 낸다 |
| **M3** | GH 어댑터 배선 + 픽스처 T1~T8 대조 | 지시서 §8 완료조건 5개 |

**M0 이 빈 `.gha` 를 먼저 띄운 것과 같은 논리로 배포 경로를 앞으로 당긴다** — "환경이 안 되는 걸 나중에 발견하는 것이 가장 비싸다"(지시서 §5 M0). 배포 경로도 같은 종류의 리스크(사내 소스 인식·배포 태그·버전 규칙·서명 여부)를 품고 있다.

각 마일스톤 종료 **즉시** `docs/journal/J-014...` 부터 저널을 남긴다. 형식은 `docs/journal/README.md`.

---

## 7. 완료 조건

지시서 §8 의 다섯에 배포 한 줄을 더한다.

1. `dotnet build` 로 `.gha` 가 나오고 Rhino 8 GH 캔버스에 컴포넌트가 뜬다
2. Visual Studio 에서 중단점이 걸린다
3. 골든 픽스처 T1~T8 을 허용오차 안에서 재현하고, **플래그는 정확히 일치**한다
4. **폴백 가지 선택이 파이썬과 핀별로 일치**한다
5. 11×11(121핀)이 3초 이내
6. **사내 소스에서 패키지 매니저로 설치·제거·재설치가 된다** (경로 하드코딩 없이)

**3·4 가 실패하면 "거의 다 된 것"이 아니라 "아직 포팅이 안 된 것"이다.**

---

## 8. 리스크

| # | 리스크 | 대응 |
|---|---|---|
| 1 | `Rhino.Testing` 이 beta 이고 셋업 요건 미검증 | M2a 에서 먼저 스모크. 안 되면 `rhinomcp` 브리지 폴백 |
| 2 | 기하 연산 부동소수 차이로 픽스처 불일치 | 허용오차 조정. 단 **플래그·가지는 예외 없음** |
| 3 | 사내 폴더 소스가 예상과 다르게 동작 | M2a 에서 빈 패키지로 먼저 확인 |
| 4 | GhPython 과 `.gha` 이름 충돌 | 이름 `AdaptiveMold Pins` + 새 GUID |
| 5 | 두 세션이 같은 Rhino 인스턴스를 쓴다 | Rhino 를 태우는 단계 전에 상대 세션 상태 확인 |

---

## 9. 이 문서 밖의 일

- Phase E(3D 모델 변형) 포팅 → GhPython 완전 대체
- 로봇·툴패스·간섭·재생 계열의 C# 이전 (지금은 파이썬이 정본)
- REST 브리지·대시보드 sync 를 `.gha` 에서 직접
- 공개 배포(공개 Yak 서버·food4Rhino)
- 픽스처 한계 3개 해소 (폴백 가지 커버리지·진짜 클램핑 케이스·부호)
- `core/geometry` 구조 불일치 정리 (지시서 §6 미결)

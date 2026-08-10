---
id: J-001
milestone: M0
date: 2026-08-11
project: ljk_facade_platform
tags: [rhino8, gha, dotnet, grasshopper, toolchain, debugging]
---

# J-001 · M0 · 툴체인 스모크테스트

> 빈 `.gha` 하나를 Rhino 8에 띄우고 중단점까지 확인했다. **최대 리스크였던 "SDK 9로 net7.0이 빌드되는가"는 해소.**
> 대신 계획 단계에서 틀리게 적어둔 것 두 가지(개발 루프 방식, 실행 런타임)가 드러났다.

---

## TRAP-01 템플릿이 만든 `launchSettings.json`이 잘못된 JSON

- **증상:** `dotnet new grasshopper`가 생성한 `Properties/launchSettings.json`의 마지막 프로필 뒤에 **후행 쉼표**가 있다. 엄밀히 잘못된 JSON.
  ```jsonc
      }
    },        ← 이 쉼표
  }
  ```
- **원인:** `Rhino.Templates 8.16.2` 템플릿 자체의 결함. 프로필을 조건부로 생성하면서 구분자를 정리하지 않음. 생성 로그에도 `Null object cannot be converted to a value type` 오류가 두 번 찍혔다(생성 자체는 성공).
- **해결:** 쉼표를 지웠다. Visual Studio는 관대해서 이대로도 F5가 돌 수 있지만, JSON을 엄격히 읽는 도구(린터·CI·스크립트)는 걸린다.
- **재발 조건:** **`dotnet new grasshopper`를 실행할 때마다.** 새 Rhino 플러그인 프로젝트를 만들면 매번 확인할 것. 템플릿 버전이 8.16.2보다 올라가면 고쳐졌는지 재확인.

---

## TRAP-02 `SolveInstance`가 비어 있어 중단점을 확인할 수 없음

- **증상:** 템플릿이 생성한 컴포넌트는 `RegisterInputParams` / `RegisterOutputParams` / `SolveInstance`가 전부 빈 몸체다. 중단점을 걸어도 관찰할 값이 없고, 컴포넌트를 캔버스에 놓아도 눈에 보이는 반응이 없어 **로드에 성공했는지 실패했는지 구별이 안 된다.**
- **원인:** 템플릿은 스캐폴딩만 제공. 의도된 동작.
- **해결:** 출력 파라미터 하나와 실행 코드 세 줄을 넣었다.
  ```csharp
  pManager.AddTextParameter("info", "i", "런타임 확인용 문자열", GH_ParamAccess.item);
  // ...
  var runtime = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription;
  var rhino   = Rhino.RhinoApp.Version.ToString();
  DA.SetData(0, $"OK | {runtime} | Rhino {rhino}");
  ```
  이 세 줄이 **로드 확인 · 런타임 확인 · 중단점 대상**을 한꺼번에 해결한다.
- **재발 조건:** 새 GH 프로젝트 스모크테스트마다. **스캐폴딩 직후 이 세 줄을 넣는 것을 절차로 굳힐 것** (PROCEDURE-01).

---

## TRAP-03 중단점을 주석 줄에 걸면 걸리지 않음

- **증상:** `SolveInstance` 첫 줄이 주석이면 거기 건 중단점이 동작하지 않는다.
- **원인:** 중단점은 실행 가능한 IL이 있는 줄에만 걸린다. 주석에는 없다.
- **해결:** 주석 다음의 실제 실행문에 건다.
- **재발 조건:** 일반적. 특히 **"여기에 중단점을 거세요" 같은 안내 주석을 달아두면 오히려 그 줄에 걸게 유도**하는 역효과가 난다. 안내는 주석이 아니라 문서에 쓸 것.

---

## TRAP-04 Rhino 버전이 세션 사이에 바뀐다

- **증상:** 2026-08-10에 `Rhino.exe` ProductVersion이 `8.32.26160.13001`이었는데, 2026-08-11에 `8.33.26188.13001`로 바뀌어 있었다. 계획서에 적어둔 실측값이 하루 만에 낡았다.
- **원인:** Rhino 8 자동 업데이트.
- **해결:** 문서·메모리의 버전 표기를 갱신하고, **측정 날짜를 함께 적도록** 바꿨다.
- **재발 조건:** 상시. **환경 실측값에 유효기간이 있다는 뜻이므로, 버전에 의존하는 판단(TFM 선택, API 가용성)은 재측정 후에 할 것.** 저널 `FACT` 항목에 "유효 범위"를 필수로 둔 이유가 이것.

---

## DECISION-01 타겟은 `net7.0` 유지 (`net8.0` 아님)

- **선택:** `net7.0-windows`.
- **근거:** M0에서 **타겟 TFM과 실행 런타임이 다르다**는 것이 실측으로 드러났다(FACT-04). 플러그인은 자기 런타임을 시작하지 않고 `Rhino.exe /netcore`가 켠 호스트 런타임에 얹히므로, `net7.0` 어셈블리가 .NET 8 호스트에서 그대로 로드된다.

  | 타겟 | Rhino 8.33 (.NET 8 호스트) | 구형 Rhino 8 (.NET 7 호스트) |
  |---|---|---|
  | **`net7.0`** | 로드됨 (확인) | 로드됨 |
  | `net8.0` | 로드됨 | **깨짐** |

- **기각한 대안:**
  - **`net8.0`** — 호스트가 .NET 8이니 맞춰주고 싶어지지만, 구형 Rhino 8(.NET 7 호스트)에서 깨진다. 얻는 것 없이 호환 범위만 줄어든다.
  - **`net48`** — Rhino 8이 받아주지만 별도 AppDomain 하위호환 경로다. 신규 개발이 갈 이유가 없다.
- **뒤집을 조건:** Rhino 9가 .NET 7 어셈블리 로드를 중단하거나, `net8.0`/`net9.0` 전용 API가 꼭 필요해질 때. 그때는 지원할 최소 Rhino 버전을 먼저 정할 것.

---

## DECISION-02 개발 루프는 `RHINO_PACKAGE_DIRS` + `/netcore`

- **선택:** 템플릿이 만드는 `Properties/launchSettings.json` 방식을 그대로 쓴다.
  ```jsonc
  "commandLineArgs": "/netcore /runscript=\"_Grasshopper\"",
  "environmentVariables": { "RHINO_PACKAGE_DIRS": "$(ProjectDir)$(OutputPath)\\" }
  ```
- **근거:** 환경변수가 빌드 출력 폴더를 직접 가리키므로 **파일 복사 절차가 없다.** `/netcore`로 호스트를 강제하고 `/runscript`로 Grasshopper를 자동으로 연다. VS에서 F5 → 중단점 정지까지 실측 확인됨.
- **기각한 대안:** **`GrasshopperDeveloperSettings` 명령으로 폴더 등록** — 계획 단계에서 이 방식으로 적었으나 **틀렸다.** Rhino 안에서 수동 설정이 필요하고, 프로젝트 밖에 상태가 남아 다른 PC에서 재현되지 않는다. `launchSettings.json`은 프로젝트에 같이 커밋된다.
- **뒤집을 조건:** 없음. 다만 **VS 시작 프로필을 `Rhino 8 - netcore`로 골라야 한다** — `netfx`를 고르면 `net48` 어셈블리가 로드돼 검증 대상이 아니게 된다.

---

## FACT-01 `Rhino.Templates` 8.16.2

- **측정값:** `dotnet new install Rhino.Templates` → `8.16.2`. 제공 템플릿: `grasshopper`(Assembly=`.gha`), `ghcomponent`, `gh2`, `rhinocommand`, `rhino`, `rhinoskin`, `rhinotest`, `zooplugin`.
- **측정 방법:** 설치 출력 및 `dotnet new grasshopper --help`.
- **유효 범위:** 2026-08-11 시점 NuGet 최신. 템플릿 결함(TRAP-01)은 이 버전 기준.

## FACT-02 템플릿 기본 설정

- **측정값:** `dotnet new grasshopper -v 8` 생성 `.csproj` —
  `<TargetFrameworks>net7.0-windows;net7.0;net48</TargetFrameworks>`, `<TargetExt>.gha</TargetExt>`, `<EnableDynamicLoading>true</EnableDynamicLoading>`.
  NuGet 참조는 **`Grasshopper 8.0.23304.9001` 하나뿐** — RhinoCommon은 전이 의존으로 딸려온다.
- **측정 방법:** 생성된 `M0Smoke.csproj` 직접 확인.
- **유효 범위:** Rhino.Templates 8.16.2, `-v 8`.

## FACT-03 SDK 9.0.201로 `net7.0` 빌드됨 ★

- **측정값:** **경고 0개 · 오류 0개 · 4.11초.** 세 타겟(`net48`, `net7.0`, `net7.0-windows`) 전부 산출. NuGet 복원 1초. `.gha` 각 6KB, `.pdb` 12KB 생성.
- **측정 방법:** `dotnet build -v minimal`.
- **유효 범위:** SDK 9.0.201. **이 PC에 .NET 7 SDK는 없다** — 참조 팩만 NuGet에서 복원됨.

> **계획서 §7 리스크 1 해소.** .NET 7 SDK 추가 설치도, 멀티타겟 우회도 필요 없다.

## FACT-04 타겟 TFM ≠ 실행 런타임 ★

- **측정값:** `net7.0-windows`로 빌드한 `.gha`가 **.NET 8.0.14**에서 실행됨.
  컴포넌트 출력: `OK | .NET 8.0.14 | Rhino 8.33.26188.13001`
  `.gha`의 `runtimeconfig.json`은 `"tfm": "net7.0"`, `"rollForward": "LatestMinor"`, `Microsoft.NETCore.App 7.0.0` 요구로 적혀 있으나 결정권이 없다.
- **측정 방법:** `RuntimeInformation.FrameworkDescription`을 컴포넌트 출력으로 뽑음.
- **유효 범위:** Rhino 8.33 기준. 플러그인이 호스트 런타임에 얹히는 구조 자체는 일반적.

> **부수 소득 — 로드 경로 확인법:**
> 컴포넌트가 `.NET 8.x`를 보고하면 **netcore**, `.NET Framework 4.8.x`면 **netfx**.
> 의도한 경로로 로드됐는지 확인하는 가장 빠른 방법.

---

## PROCEDURE-01 GH 플러그인 스모크테스트

- **목적:** 새 환경·새 프로젝트에서 "빌드 → 로드 → 디버그"가 끝까지 도는지 최단 경로로 확인.
- **단계:**
  1. `dotnet new install Rhino.Templates`
  2. `dotnet new grasshopper -v 8 --component-class <X> -cat <탭> -sub <패널>`
  3. **`launchSettings.json` 후행 쉼표 제거** (TRAP-01)
  4. **`SolveInstance`에 런타임 보고 3줄 삽입** (TRAP-02)
  5. `dotnet build -f net7.0-windows`
  6. `RHINO_PACKAGE_DIRS`=출력폴더 설정 후 `Rhino.exe /netcore /runscript="_Grasshopper"`
  7. 캔버스에 컴포넌트 배치 → 출력 문자열로 로드 경로 확인
  8. VS에서 프로필 `Rhino 8 - netcore` 선택 → 실행문(주석 아님)에 중단점 → F5
- **자동화 후보:** **예.** 3·4번은 순수 텍스트 조작이고 1·2·5·6번은 명령이다. 전체를 스크립트 하나로 묶을 수 있다. 손으로 두 번 할 일이 아니다.

---

## 미해결

- **멀티타겟 3개를 유지할지, `net7.0-windows`만 남길지.** 템플릿 기본은 3개다. 배포 대상이 Windows Rhino 8뿐이면 `net48`·`net7.0`은 빌드 시간만 쓴다. M2에서 실제 빌드 시간을 보고 정할 것.
- 두 Rhino 프로세스가 같은 `.gha`를 잡을 때 디버거가 못 붙는지 — **미검증.** 경고만 하고 실제로 부딪히지 않았다.

---

## 승격 후보

3개 저장소에서 반복되면 `~/.claude/skills/rhino-plugin/`으로.

| 항목 | 이유 |
|---|---|
| **FACT-04 로드 경로 확인법** | Rhino 8 플러그인이면 무조건 필요. 가장 범용적 |
| **DECISION-01 `net7.0` 채택 근거** | 모든 Rhino 8 `.gha`/`.rhp`에 그대로 적용 |
| **TRAP-01 후행 쉼표** | 템플릿 결함이므로 모든 신규 프로젝트에서 재발 |
| **PROCEDURE-01 스모크테스트** | 그대로 스크립트·템플릿이 됨 |
| TRAP-02 빈 `SolveInstance` | PROCEDURE-01에 흡수 가능 |

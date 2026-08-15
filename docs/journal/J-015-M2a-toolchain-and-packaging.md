---
id: J-015
milestone: M2a
date: 2026-08-15
project: ljk_facade_platform
tags: [gha, csharp, yak, packaging, distribution]
---

# J-015 · M2a · 툴체인·배포경로·러너·지문

> 알고리즘은 한 줄도 옮기지 않았다. 옮길 자리와, 옮긴 것이 맞는지 볼
> 수단을 만든다. 첫 관문인 **배포 경로는 통과했다** — 사내 폴더를
> 패키지 매니저가 소스로 받고, 검색·설치·메타데이터 표시가 모두 된다.
> 대신 사양서에 적어둔 예상 둘이 실측과 달랐다.

> 저널 번호가 J-014 가 아닌 이유: `feature/unfold-v1` 이 같은 날
> `J-014-unfold-blank-v1.md` 를 먼저 썼다. 두 브랜치가 같은
> `docs/journal/` 을 쓰는 동안은 **새 저널 전에 양쪽을 확인해야 한다** —
> `git ls-tree --name-only feature/unfold-v1 docs/journal/`.

---

## FACT-01 사내 폴더 소스는 동작한다 ★★

- **측정값:**
  - `yak search --source "C:\Users\leeja\AppData\Local\LJKS\packages" yaksmoke` → `yaksmoke (0.1.0)`
  - `yak install --source <같은 폴더> yaksmoke` → `Successfully installed`
  - 설치 경로 `%APPDATA%\McNeel\Rhinoceros\packages\8.0\yaksmoke\0.1.0\`
    상위 `yaksmoke\manifest.txt` 의 내용은 활성 버전 문자열 하나(`0.1.0`)
  - **패키지 매니저 UI 에서도 검색되고 `authors: LJK STUDIO` 가 채워져 보인다**
- **측정 방법:** 스크래치에 `dotnet new grasshopper` 로 빈 `.gha` 를 만들어
  `yak spec` → 매니페스트 수기 편집 → `yak build --platform win` →
  폴더에 복사 → CLI 설치. UI 확인은 `Options > Advanced` 의
  `Rhino.Options.PackageManager.Sources` 에 폴더를 세미콜론으로 추가하고
  Rhino 재시작 후 `_PackageManager` 검색.
- **유효 범위:** Rhino 8.33.26188.13001 / yak 0.15.2 / 이 PC.

> **"로컬 소스에서는 이름·버전 외 필드가 전부 빈칸으로 보인다"는 보고는
> 재현되지 않았다.** 사양서 §6.4 에 `미검증`으로 달아둔 항목이고, 이
> 실측으로 해소한다. (보고 자체가 틀렸는지, 특정 버전에서만 나는지는
> 여전히 모른다 — 우리 환경에서는 안 난다는 것만 확인했다.)

## FACT-02 배포 태그의 플랫폼 반쪽은 기본이 `any` 다 ★★

- **측정값:**
  - `yak build` → `yaksmoke-0.1.0-rh8_0-**any**.yak`
  - `yak build --platform win` → `yaksmoke-0.1.0-rh8_0-**win**.yak`
- **측정 방법:** 같은 출력 폴더에서 두 번 실행하고 파일명을 비교.
- **유효 범위:** yak 0.15.2.

**타겟 프레임워크가 `net7.0-windows` 여도 자동으로 `-win` 이 되지 않는다.**
Rhino 버전 반쪽(`rh8_0`)만 어셈블리에서 유도되고 플랫폼은 별개다.
사양서 §6.4 가 `rh8_0-win` 을 예상으로 적어 두었는데, **조건부로만 맞다** —
플래그를 줘야 한다. 빌드 스크립트에 `--platform win` 을 고정한다.

## FACT-03 `yak cache` 는 인자를 받지 않는다 ★

- **측정값:** `yak cache <경로>` → `Usage: yak cache [-h | --help]`.
  `yak help` 목록에도 `cache` 가 없지만 명령 자체는 실재한다.
- **측정 방법:** 직접 실행.
- **유효 범위:** yak 0.15.2.

"배포 폴더를 인자로 주어 인덱스를 만든다"는 이해는 **틀렸다.** 인자가 없고
**Rhino 에 등록된 소스 전체**를 대상으로 돈다. 따라서 **소스 등록이 선행
조건**이고, 배포 스크립트는 "폴더에 복사 → `yak cache`" 순서가 된다.

## FACT-04 구버전 폴더 잔존이 이 PC 에 실재한다 ★★

- **측정값:** `%APPDATA%\McNeel\Rhinoceros\packages\8.0\` 전수 조사 —
  9개 패키지 중 **`OpenNest` 만 `2.93.0.0` 과 `2.94.0.0` 두 버전 폴더 공존.**
  나머지 8개는 하나씩.
- **측정 방법:** 패키지별 하위 폴더 개수를 세는 셸 루프.
- **유효 범위:** 이 PC. McNeel 이 Rhino 8 자동업데이트의 의도치 않은
  결과로 인정한 회귀(RH-85306, 8 SR23 수정)와 일치한다.

**그래서 완료조건 6(설치·제거·재설치)의 검증은 UI 가 아니라 디스크에서
한다.** UI 는 통과해도 디스크는 통과가 아닐 수 있다.

## FACT-05 패키지 구조와 secret ★

- **측정값:** `.yak` 은 zip 이고 내용이 평평하다 —
  `manifest.yml` · `YakSmoke.gha` · `.deps.json` · `.pdb` · `.runtimeconfig.json`.
  그리고 `yak build` 가 **키워드에 `guid:8004b883-100f-49e6-a44a-acbcbe6de45d`
  를 자동으로 추가**한다(= 플러그인 GUID, 누락된 GH 플러그인을 찾을 때의 폴백).
- **측정 방법:** `zipfile` 로 목록 출력, `yak build` 표준출력 확인.
- **유효 범위:** yak 0.15.2 / 단일 TFM 빌드.

---

## TRAP-01 `yak spec` 은 패키지 이름을 `GH_AssemblyInfo.Name` 에서 만든다 ★★

- **증상:** `yak spec` 이 생성한 매니페스트의 이름이 `YakSmoke-Info` 였다.
  프로젝트명(`YakSmoke`)도, csproj 의 `<Title>`(`YakSmoke`)도 아니다.
- **원인:** 템플릿의 `GH_AssemblyInfo` 클래스가 `Name => "YakSmoke Info"` 를
  돌려주고, yak 이 그것을 쓰면서 **공백을 하이픈으로 바꾼다.**
- **해결:** 매니페스트의 `name` 을 손으로 고친다. 사양서가 정한 패키지 id 는
  `ljks-adaptive-mold` 인데 `AdaptiveMoldInfo.Name` 은 `"LJKS AdaptiveMold"`
  이므로(GH 플러그인 목록에 보이는 이름이라 그대로 두어야 한다)
  **`yak spec` 결과를 그대로 쓰면 안 된다.**
- **재발 조건:** `yak spec` 을 돌릴 때마다. 그리고 **최초 업로드의 대소문자가
  영구 고정**되므로 공개 배포로 갈 때 한 번 틀리면 되돌릴 수 없다.
  M3 에서 매니페스트를 만들 때 반드시 확인할 것.

## TRAP-02 템플릿의 후행 쉼표가 세 번째로 재발했다 ★

J-001 TRAP-01 과 같은 것이므로 상세는 반복하지 않는다. 다만 **재발 조건이
확정적**임을 기록한다 — `Rhino.Templates 8.16.2` 로 `dotnet new grasshopper`
를 돌리면 `Properties/launchSettings.json` 마지막 프로필 뒤에 **매번**
후행 쉼표가 붙는다(2026-08-11, 08-15 ×2 관측). 템플릿 버전이 올라가면
고쳐졌는지 재확인.

부수 관측: 이번에는 J-001 이 적어둔 `Null object cannot be converted to a
value type` 생성 로그 오류가 **나오지 않았다.** 후행 쉼표는 그대로였으므로
둘은 별개 증상이다.

## TRAP-03 `Version="8.*"` 하나로 컴포넌트가 조용히 사라진다 ★★★

이 마일스톤에서 가장 비싼 함정이었다. **증상이 완전히 침묵한다.**

- **증상:** `.gha` 가 빌드되고, Rhino 가 어셈블리를 AppDomain 에 로드하고
  (`AppDomain.CurrentDomain.GetAssemblies()` 에 보인다), 타입도 정상 열거되고
  (`AMv1PinsComponent` 존재), 직접 `Activator.CreateInstance` 하면 이름·카테고리·
  한글 툴팁까지 완벽하다. **그런데 GH 라이브러리 목록에 없고 팔레트에도 없다.**
  `ComponentServer.LoadingExceptions` 는 **비어 있고**,
  `FindAssembly(info_guid)` 는 **null**, Rhino 명령 히스토리에도 아무 말이 없다.
- **원인:** csproj 에 `<PackageReference Include="Grasshopper" Version="8.*" />` 라고
  적었더니 NuGet 이 **8.34.26223.11001** 을 끌어왔다. 이 PC 의 Rhino 는
  **8.33.26188.13001** 이다. **자기보다 높은 API 로 빌드된 플러그인**을
  Grasshopper 가 로드는 하되 등록만 거부한다 — **아무 진단도 남기지 않고.**
  - **결정적 증거:** `yak build` 산출 파일명이 `...-rh8_34-win.yak` 이었다.
    배포 태그는 참조한 `Grasshopper.dll` 버전에서 유도되므로, **이 파일명 하나가
    "8.34 로 빌드됐다"를 말하고 있었다.** 버전을 8.0 으로 고정하니 `rh8_0-win`.
- **해결:** `RhinoCommon`·`Grasshopper` 를 **`8.0.23304.9001`(Rhino 8.0 기준선)로
  고정.** 플러그인은 **지원하는 가장 낮은 API 로 빌드**한다. 템플릿 기본값이
  그 버전인 데는 이유가 있었다.
  재빌드 → yak 재패키징 → 설치 → **등록됨**:
  라이브러리 `LJKS AdaptiveMold`, 프록시 `AMv1 Pins` (`LJKS`/`AMv1`, primary).
  캔버스에 놓고 실행한 출력이
  `OK | .NET 8.0.14 | Rhino 8.33.26188.13001 | AdaptiveMold.Core | compute=True`
  — netcore 경로 로드와 `Core.dll` 연결까지 한 줄로 확인된다.
- **재발 조건:** **NuGet 참조에 와일드카드를 쓸 때마다.** 그리고 Rhino 가
  자동 업데이트되므로 **어느 날 갑자기** 재발할 수 있다 — 오늘 8.34 가 최신이면
  8.33 에서 깨지고, 내일 8.35 가 나오면 8.34 에서도 깨진다.
  → `PackagingContractTests` 가 와일드카드와 8.0 이외 핀을 막는다.

**부수 결정 — NU1701 은 덮는다.** `RhinoCommon` 8.0 패키지에는 `net48` 자산만
있어(net7.0 자산은 **8.32 부터**) `net7.0-windows` 프로젝트가 net48 참조
어셈블리로 컴파일된다. 8.32 로 올리면 경고는 사라지지만 패키지가 **Rhino 8.32+
전용**이 된다. 우리가 쓰는 API(`RayShoot`·`ClosestPoint`·`Surface.Extend`·
`FitPlaneToPoints`)는 전부 오래된 안정 API 라 올릴 이유가 없고, 8.0 핀 빌드가
8.33 에서 도는 것은 위에서 실증됐다. **뒤집을 조건:** 8.32+ 에만 있는 API 가
필요해지면.

## TRAP-04 포트가 열린 것은 브리지가 준비된 것이 아니다 ★★

- **증상:** `Test-NetConnection 127.0.0.1 -Port 1999` 가 `True` 인데 모든 브리지
  호출이 `Timeout waiting for Rhino response`. 프로세스는 `Responding=True`.
- **원인 둘:**
  1. **`mcpstart` 를 하지 않아도 포트 1999 는 열린다** — 플러그인이 로드되면서
     리스너를 연다. 실측: 새 Rhino 를 `mcpstart` 없이 띄웠는데 포트가 열려 있었다.
     **즉 포트 개방은 준비 신호가 아니다.**
  2. **Rhino 를 재시작하면 MCP 서버가 재연결하지 않는다**(이미 알려진 함정).
     MCP 계층은 죽은 연결을 붙들고 있고 `claude mcp list` 는 여전히 정상으로 보인다.
- **해결:** 판정은 포트가 아니라 **실제 왕복**으로 한다(한 줄짜리 `print` 를 태워
  본다). MCP 계층이 죽었으면 **TCP 직결**(`adaptive_mold/tools/rhino_cli.py`)로
  우회한다 — 이번 세션의 진단 전부를 이 경로로 했다.
- **재발 조건:** Rhino 를 재시작할 때마다. **Rhino 를 껐다 켜면 MCP 는 못 쓴다고
  가정하고 시작할 것.**

## TRAP-05 `/runscript=` 로는 `mcpstart` 가 안 걸린다 ★

- **증상:** `Rhino.exe /netcore /runscript="_mcpstart"` (따옴표 유무 모두)로 띄워도
  브리지가 응답하지 않는다. 오류 대화상자도 없다.
- **원인:** 미확정. J-005 TRAP-01 이 `_-RunPythonScript` 에 대해 기록한 것과 같은
  증상이고, **범위가 파이썬 스크립트 한정이 아니었다.**
- **해결:** 없다. `mcpstart` 는 사람이 Rhino 명령창에 친다.
- **재발 조건:** 자동화를 시도할 때마다. **여기에 시간을 더 쓰지 말 것.**

## TRAP-06 `/netcore` 로 띄우면 인스턴스가 둘이 될 수 있다 ★

- **증상:** `Start-Process Rhino.exe /netcore …` 후 `Get-Process Rhino` 가 **2개**
  (각 ~800MB, 둘 다 Responding). 포트 1999 를 놓고 경합해 브리지가 먹통.
- **원인:** 미확정 — 런타임 호스트 전환 과정으로 추정(**미검증**).
- **해결:** 띄운 뒤 **프로세스 개수를 세고**, 둘이면 정리하고 하나만 다시 띄운다.
- **재발 조건:** 명령줄로 Rhino 를 띄울 때. 스크립트로 자동화한다면 개수 확인을
  절차에 넣을 것.

---

## DECISION-01 테스트 러너 — `Rhino.Testing` 기각, Rhino 안 NUnitLite 채택 ★★★

- **선택:** 테스트 어셈블리를 **Rhino 안에서** NUnitLite `AutoRun(assembly).Execute(args)`
  로 태우고 결과 XML 을 밖에서 읽는다. 도구는
  `adaptive_mold/tools/run_csharp_tests.py`. **새 프로젝트(`.rhp`)를 만들지 않았다.**

- **근거 (실측 순서대로):**
  1. **Rhino 밖 `dotnet test` 는 메타데이터 테스트만 된다.** csproj 를 읽는 계약
     테스트 9개는 돈다. 그러나 `new Sphere(...).ToBrep()` 하나를 넣으니
     `FileNotFoundException: Could not load file or assembly 'RhinoCommon,
     Version=8.0.23304.9001'`. `ExcludeAssets=runtime` 때문에 출력에 없고,
     넣더라도 네이티브 스택이 필요하다.
  2. **`Rhino.Testing 8.0.28-beta` 는 서지 않는다.** 패키지·`Configs.xml`·
     `[RhinoTestFixture]` 를 다 갖췄는데 **그 테스트가 discovery 에서 사라진다** —
     전체 개수가 10 → 9 로 줄고 러너는 **"통과!"** 라고 보고한다.
     `--list-tests` 로 확인: 목록에 없다.
     원인은 NUnit 버전 불일치로 보였다 — nuspec 이 **NUnit 3.14.0** 을 요구하는데
     우리는 4.2.2 였다. **3.14.0 으로 내려도 여전히 사라졌다.**
     `Rhino.Testing.dll`·`Rhino.Inside.dll` 은 출력에 정상 복사돼 있었다.
  3. **Rhino 안에서는 그냥 된다.** 같은 어셈블리를 Rhino 안에서
     `Assembly.LoadFrom` → `AutoRun(testasm).Execute(["--result=..."])` 로 태우니
     **total=10 passed=10 failed=0**, `Sphere_to_brep_works` 포함 전부 통과.

- **기각한 대안:**
  - **`Rhino.Testing`** — 위 2. 공개 버전 38개가 전부 `-beta` 이고 Rhino 8 계열은
    2025-05 이후 동결이라 고쳐지길 기다릴 수 없다.
  - **`.rhp` 테스트 호스트 프로젝트** — 계획서의 폴백안이었다. **필요 없었다.**
    Rhino 안에서 어셈블리를 직접 로드하면 되므로 프로젝트가 하나 줄고,
    `yak spec` 이 `.rhp` 를 잘못 집는 문제(같은 폴더면 배포 태그·secret 이 엉킨다)도
    원천적으로 사라진다.
  - **CI 에 올리기** — 하지 않는다. 클라우드 러너는 Windows Server 라 Rhino.Inside 가
    유료 토큰을 요구하고 상용 시트와 비호환이다. 무엇보다 **실패가 조용히 초록으로
    남는다.** 대조는 사람이 돌리는 게이트로 둔다.

- **뒤집을 조건:** `Rhino.Testing` 이 안정 릴리스를 내고 discovery 가 고쳐지면.
  그때는 테스트 코드를 그대로 두고 러너만 바꾸면 된다 — **`[RhinoTestFixture]` 를
  쓰지 않았으므로 코드가 어느 쪽에도 묶여 있지 않다.**

- **함정 둘을 도구에 박아 두었다:**
  1. **`AutoGeneratedProgram.Main` 을 부르면 안 된다.** NUnitLite 가 생성한 Main 은
     **호출 어셈블리** 기준으로 테스트를 찾는데, Rhino 안에서는 그것이 Rhino.exe 라
     아무것도 못 찾고 **조용히 끝난다**(결과 XML 도 안 생긴다).
     반드시 `AutoRun(testAssembly)` 생성자에 어셈블리를 명시한다.
  2. **출력 폴더를 그대로 태우면 그 세션 내내 빌드가 막힌다.** `LoadFrom` 이 파일을
     잡고 **Rhino 를 껐다 켜야 놓는다.** 도구가 `bin` 을 임시 폴더로 **복사한 뒤**
     태우는 이유다. → TRAP-07.
  3. `Execute(String[], ExtendedTextWriter, TextReader)` 오버로드는 IronPython 에서
     쓰기 번거롭다. **`Execute(String[])` 만 쓰고 결과는 XML 로 받는다.**

- **`total == 0` 을 실패로 판정한다.** 0개인데 초록인 것이 이 영역의 대표적
  실패 모드이고, 위 2에서 실제로 당했다.

## TRAP-07 잠긴 DLL 과 낡은 DLL — 초록이 두 번 거짓말한다 ★★★

두 개가 겹쳐서 **고치지도 않은 코드가 통과**하는 상황을 만들었다.

- **증상:** 새 테스트 3파일을 추가하고 빌드했더니
  `MSB3021 ... because it is being used by another process` 로 **빌드가 실패**했다.
  그런데 이어서 돌린 테스트는 **10/10 통과**라고 보고했다. 새 테스트는 하나도
  실행되지 않았는데 화면은 완전히 초록이었다.
- **원인 둘:**
  1. **파일 잠금** — 도구를 만들기 **전에** 손으로 `bin\...\AdaptiveMold.Tests.dll` 을
     직접 `LoadFrom` 했다. .NET 은 그 파일을 AppDomain 수명 동안 잡으므로
     **Rhino 세션이 살아 있는 한 재빌드가 막힌다.**
  2. **낡은 산출물** — 빌드가 실패해도 옛 DLL 이 `bin` 에 남아 있고, 러너는 그것을
     태운다. 실패한 빌드가 성공한 테스트로 보인다.
- **해결:**
  - 도구는 **절대 `bin` 을 직접 태우지 않는다.** 임시 폴더로 복사한 뒤 태운다.
    (한 번 손으로 직접 태우면 그 세션은 오염된다 — Rhino 재시작으로만 푼다.)
  - 도구가 **낡음을 감지한다.** `bin` 의 DLL 보다 최근에 수정된 `.cs`·`.csproj` 가
    있으면 실행을 거부한다. 실측으로 `FingerprintTests.cs` 외 2개를 정확히 잡았다.
- **재발 조건:** 진단하다가 손으로 어셈블리를 로드할 때마다. 그리고 **빌드 실패를
  못 보고 지나칠 때마다.**

> **정직하게 적는다 — 나는 이것을 한 번 잘못 검증했다.** 도구를 만든 직후
> "재빌드가 Rhino 재시작 없이 된다"고 확인했는데, 그때는 소스가 안 바뀌어
> **빌드가 no-op 이라 복사가 일어나지 않았다.** 아무것도 증명하지 못한 검증이었다.
> **파일 잠금을 검증하려면 반드시 소스를 바꾼 뒤 빌드해야 한다.**

---

## PROCEDURE-01 사내 배포 (M2a-0 에서 실증한 순서)

- **목적:** `.gha` 를 사내에서 패키지 매니저로 설치 가능하게 만든다.
- **단계:**
  1. `dotnet build -c Release` (단일 TFM `net7.0-windows`)
  2. 출력 폴더에서 `yak spec` → **매니페스트의 `name` 을 손으로 교정**(TRAP-01)
  3. `yak build --platform win` ← 플래그 없으면 `-any` (FACT-02)
  4. `.yak` 을 배포 폴더에 복사
  5. `yak cache` (인자 없음, 소스 등록이 선행 — FACT-03)
  6. 받는 쪽: `Options > Advanced` 의 `Rhino.Options.PackageManager.Sources`
     에 폴더 추가 → **Rhino 재시작** → `_PackageManager`
- **자동화 후보:** **예.** 1~5 는 스크립트 하나로 묶인다. 6은 PC 당 1회.

---

## FACT-07 C# 이 파이썬과 같은 입력 지오메트리를 만든다 ★★★

M2a 의 핵심 판정이다. 이것이 통과하기 전의 출력 대조는 전부 무의미하다.

- **측정값:** 픽스처 8개 × 2(곡면·평면) = **16개 대조 전부 통과.**
  전체 **26/26**(계약 4 + 패키징 5 + 기하 스모크 1 + 지문 16).
  대조 항목은 bbox(6자리) · 면적(1e-6) · face 수 · degree u·v · 제어점 수 u·v,
  평면은 원점·세 축(6자리).
- **측정 방법:** `TestSurfaceBuilder`(파이썬 `build_surface`/`build_plane` 의 C# 1:1
  포팅)가 픽스처의 `input.surface`·`input.base_plane` 스펙으로 지오메트리를 다시
  만들고, `GeometryFingerprint` 가 파이썬과 같은 규칙으로 지문을 계산해
  `input.fingerprint`·`input.plane_fingerprint` 와 대조한다.
  실행은 `python adaptive_mold/tools/run_csharp_tests.py`.
- **유효 범위:** Rhino 8.33 / 현재 8개 케이스. **T9(`ray-` 가지)를 추가하면
  그 케이스의 지문도 같이 검증된다.**

**한 번에 맞았다.** `new Plane(origin, normal)` 이 x축을 어떻게 고르는지 같은 것을
우리가 정하지 않았는데도 일치한다 — 양쪽이 같은 RhinoCommon 생성자를 부르기
때문이다. 어긋났다면 그 자체가 발견이었을 텐데, 그렇지 않았다.

## FACT-06 개발 루프(`RHINO_PACKAGE_DIRS`)와 설치본은 결과가 같다 ★

TRAP-03 을 진단하는 과정에서 얻은 대조군이다.

- **측정값:** 버전 핀을 고치기 **전**에는 `RHINO_PACKAGE_DIRS` 경로에서도
  설치본에서도 등록되지 않았다. 고친 **후**에는 설치본에서 등록됐다.
  같은 세션에 yak 으로 설치한 `YakSmoke`(템플릿 기본 핀 = 8.0)는 **처음부터
  정상 등록**돼 있었다 — 이것이 "어셈블리 자체는 멀쩡한데 우리 것만 안 된다"를
  가리킨 첫 단서였다.
- **측정 방법:** `GH.Folders.AssemblyFolders`(우리 폴더가 목록에 있음을 확인),
  `ComponentServer.Libraries` / `ObjectProxies` / `FindAssembly`,
  `AppDomain.GetAssemblies()`.
- **유효 범위:** Rhino 8.33.

**개발 루프가 고장 난 것이 아니었다.** `RHINO_PACKAGE_DIRS` 는 정상 동작하며
GH 스캔 폴더 목록에 정확히 들어간다. 문제는 전적으로 빌드 버전이었다.

---

## PROCEDURE-02 C# 테스트 돌리기

- **목적:** 픽스처 대조를 포함한 C# 테스트를 실행한다.
- **단계:**
  1. Rhino 8 실행 (`/netcore`)
  2. 명령창에 **`mcpstart`** ← 유일한 수동 단계. `/runscript=` 로는 안 된다(TRAP-05)
  3. `dotnet build plugin/AdaptiveMold.Tests/AdaptiveMold.Tests.csproj` **성공 확인**
  4. `python adaptive_mold/tools/run_csharp_tests.py`
- **자동화 후보:** 2번을 빼고 이미 자동화됨. 2번은 방법이 없다(TRAP-05).
- **주의:** 3번이 실패하면 4번이 **옛 DLL 로 통과를 낸다.** 도구가 낡음을
  감지하지만, 그 앞에 빌드 결과를 눈으로 볼 것(TRAP-07).

## FACT-09 F1 은 죽어 있고 우클릭 `Help` 만 산다 ★★

- **측정값:** 캔버스에 놓인 `AMv1 Pins` 를 선택하고 **F1 → 아무 반응 없음.**
  **우클릭 메뉴의 `Help` 항목은 있다.**
- **측정 방법:** 사용자가 직접 눌러 확인.
- **유효 범위:** Rhino 8.33 / Grasshopper / 서드파티 `.gha` 컴포넌트.

**M3 도움말 설계에 직결된다.** 도움말이 **밀어서 닿지 않고 사용자가 찾아
들어가야** 닿는다는 뜻이므로, **우클릭 메뉴가 유일한 통로**다. 설계 §4.2 가
`예제 파일 열기`·`매뉴얼 열기`를 우클릭에 넣기로 한 것이 맞았고, 이제는
"있으면 좋은 것"이 아니라 **없으면 도움말이 사용자에게 도달하지 않는다.**

**우클릭 `Help` 에는 우리가 쓴 한글 설명이 그대로 나온다** (사용자 확인).
컴포넌트 `Description` 과 파라미터 툴팁에 들이는 공이 헛되지 않는다는 뜻이다 —
`.gha` 로 옮기며 얻은 이득(설명이 어셈블리에 컴파일되어 `.gh` 저장·코드 push 로
소실되지 않는다)이 그대로 값을 한다.

**그러나 채널이 하나뿐이고 그것이 pull 이다.** 사용자가 우클릭해 찾아 들어가야만
읽는다. 그래서 M3 에서:

1. 우클릭 메뉴의 `예제 파일 열기`·`매뉴얼 열기`는 **선택이 아니라 필수**다.
   그것이 없으면 매뉴얼과 예제는 설치 폴더 안에서 아무도 못 찾는다.
2. **런타임 경고가 유일한 push 채널이다.** 문제가 났을 때 사용자 화면으로
   밀어줄 수 있는 것은 그것뿐이다. §3.6 의 신규 경고 4개 —
   특히 **클램핑 경고**(T3 에서 핀의 56%가 클램핑되는데 지금은 캔버스가 초록) —
   의 근거가 여기서 더 강해진다.

## FACT-08 제거는 깨끗하다 — 잔존은 자동 업데이트 한정 ★

- **측정값:** `yak uninstall yaksmoke` → **폴더째 사라짐**
  (`packages\8.0\yaksmoke\` 자체가 없음). **Rhino 가 실행 중인데도** 그렇다.
- **측정 방법:** 제거 전후 디렉터리 비교 + `yak list`.
- **유효 범위:** Rhino 8.33 / yak 0.15.2.

FACT-04 의 `OpenNest 2.93 + 2.94` 공존과 대조하면, **잔존은 일반 제거가 아니라
자동 업데이트 경로의 문제**로 보인다(McNeel 이 인정한 RH-85306 과 일치).
완료조건 6의 디스크 검증은 그대로 유지한다 — 확인 비용이 0에 가깝다.

---

## 미해결

- **F1 도움말 패널이 서드파티 컴포넌트에서 무엇을 보여주는지** 아직 안 봤다
  (사람 눈이 필요). 툴팁이 붙는 것은 실측으로 확인했다 —
  컴포넌트를 직접 인스턴스화해 입출력 `Description` 을 읽었고 한글이 온전했다.
- **`RHINO_PACKAGE_DIRS` 개발 루프를 버전 핀 수정 후 재확인하지 않았다.**
  설치본으로만 검증했다. 둘 다 되는 것이 맞겠지만 **미검증**이다.
- **`yak cache` 를 실제 사내 소스에 대해 돌려보지 않았다.** 인자를 안 받는다는
  것만 확인했고, 인덱스가 실제로 검색을 바꾸는지는 안 봤다.
- **다른 PC/계정에서의 설치**는 확인 못 했다. 완료조건 6이 요구하는 것이 그것이다.
- **`Rhino.Testing` 이 왜 discovery 에서 사라지는지 근본 원인은 모른다.**
  NUnit 버전은 아니었다(3.14 로 맞춰도 동일). 우회했으므로 더 파지 않았다.
- **소스를 등록하지 않은 다른 PC/계정**에서의 설치는 확인 못 했다.
  완료조건 6이 요구하는 것이 그것이다.
- `yak install --all-users` 의 설치 대상 — 이 PC 에 `C:\ProgramData\McNeel\
  Rhinoceros\packages` 가 없어 확인 불가.
- **정적 HTTPS 폴더를 소스 URL 로 직접 물릴 수 있는지** — 여전히 미검증.
  현재 설계는 여기에 기대지 않는다(로컬 폴더로만 간다).

---

## 승격 후보

전부 **프로젝트 맥락 없이 성립**하는 것들이다. `howick-grasshopper` 가 C# 플러그인
개발에 들어가면 그때가 두 번째다.

- **TRAP-03 (버전 핀)** — 가장 값어치가 높다. 증상이 완전히 침묵하고, Rhino 가
  자동 업데이트되므로 **누구에게나 어느 날 갑자기** 일어난다. 판별법(`yak` 파일명의
  태그)까지 한 세트다.
- **TRAP-07 (잠긴/낡은 DLL)** — Rhino 안에서 테스트를 태우는 모든 프로젝트에 해당.
- **DECISION-01 (러너)** — `Rhino.Testing` 의 현재 상태는 이 프로젝트 사정이 아니다.
- **PROCEDURE-01 (사내 배포)** · **PROCEDURE-02 (테스트 실행)**
- **TRAP-01** — `yak spec` 의 이름 유도는 yak 의 성질이다.
- **TRAP-04/05** — 브리지 연결 판정과 `mcpstart` 자동화 불가.
  이 둘은 이미 `~/.claude/skills/rhino-bridge/` 가 있으므로 **저장소 3개를
  기다리지 말고 그 스킬에 바로 반영할 후보**다(2026-08-12 사용자 지시의 예외 조항).

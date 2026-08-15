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

## 미해결

- **제거 후 디스크가 깨끗해지는지 아직 안 봤다** (Step 9). FACT-04 를 보면
  볼 가치가 있다.
- **소스를 등록하지 않은 다른 PC/계정**에서의 설치는 확인 못 했다.
  완료조건 6이 요구하는 것이 그것이다.
- `yak install --all-users` 의 설치 대상 — 이 PC 에 `C:\ProgramData\McNeel\
  Rhinoceros\packages` 가 없어 확인 불가.
- **정적 HTTPS 폴더를 소스 URL 로 직접 물릴 수 있는지** — 여전히 미검증.
  현재 설계는 여기에 기대지 않는다(로컬 폴더로만 간다).

---

## 승격 후보

- **PROCEDURE-01** — Rhino 플러그인을 사내 배포하는 절차는 프로젝트 맥락이
  없어도 성립한다. `howick-grasshopper` 가 같은 문제를 만나면 두 번째다.
- **TRAP-01** — `yak spec` 의 이름 유도는 이 프로젝트 사정이 아니라 yak 의
  성질이다.

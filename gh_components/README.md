# Grasshopper Components

GhPython 컴포넌트용 **RunScript 파일**은 `gh_scripts/` 폴더에 있습니다.

| 파일 | 용도 |
|---|---|
| `gh_scripts/AMv1_Bridge.py` | 대시보드 파라미터 pull |
| `gh_scripts/AdaptiveMold_v1.py` | AdaptiveMold 계산 + sync |
| `gh_scripts/AMv1_Inspect.py` | **몰드 시각화 — 핀·강선·시트·이탈량을 보며 판단** |
| `gh_scripts/AMv1_RollerPath.py` | 롤러 툴패스 생성 (왕복 지그재그 + 공중 이동) |
| `gh_scripts/AMv1_Robot.py` | IRB 6700 도달성 검사·포즈 생성 (IK) |
| `gh_scripts/AMv1_PathFrames.py` | 경로 위 법선·툴축 표시 (경로 확인용) |
| `gh_scripts/AMv1_Play.py` | **실제 속도 재생 — 핀 상승 + 로봇 성형 (IRB 6700 실물 형상)** |

로봇 실물 메시는 `adaptive_mold/grasshopper/irb6700_parts.3dm` (파트 9개, 12만 면).
웹 시뮬레이터의 GLB에서 `adaptive_mold/tools/import_robot_glb.py` 로 만든 것이고,
원본이 바뀌면 그 도구를 다시 돌립니다 (`ljks_website_v2` 가 형제 경로에 있어야 합니다).

리본에는 `LJKS / AMv1` 탭에 아이콘과 함께 등록되어 있습니다
(`adaptive_mold/tools/make_user_objects.py`).

**툴팁은 `.gh`가 보관하지 못합니다.** Rhino를 다시 켤 때마다 사라지므로 문서를 열면
`adaptive_mold/tools/apply_param_docs.py`를 한 번 돌리는 것이 정상 절차입니다
(정본: `param_docs.py`, 현재 125개).

개발 절차 전체는 스킬 `~/.claude/skills/gh-component-dev/` 에 정리해 두었습니다.

## 파이프라인 연결

```
Inspect.sheet_ht ──→ RollerPath.mold_srf
Inspect.pin_tops ─────────────────────────────→ Play.pin_tops
RollerPath.targets ──→ Robot.targets ──→ Robot.poses ──→ Play.poses
RollerPath.targets ───────────────────────────→ Play.targets
RollerPath.move_kind ─────────────────────────→ Play.move_kind
```

`Play`는 `Robot`을 **step=1** 로 돌린 결과를 필요로 합니다. step>1이면 포즈와 타겟이
어긋나 이송 시간을 쓸 수 없습니다(Play의 info가 경고합니다).

## 로봇 위치

`Robot`과 `Play`에 **같은** 베이스를 물려야 계산과 그림이 맞습니다. 우선순위는
`robot_base`(평면) > `base_pt`/`base_dir`(점·선) > 자동이고, 판단은
`robot.resolve_base_plane()` 한 곳에서 합니다.

```
python adaptive_mold/tools/make_robot_base_ref.py
```

Rhino 레이어 `robot_base`에 점·선을 만들고 GH 파라미터로 **참조**해 두 컴포넌트에
배선합니다. 그 다음부터는 **Rhino에서 점을 끌거나 선을 돌리면 로봇이 따라옵니다.**
방향 선은 `Param_Curve`로 받습니다 — `Param_Line`은 Rhino 객체를 참조하지 못해
값이 박히고, 선을 돌려도 방향이 바뀌지 않습니다.

### 위치를 자동으로 찾기

```
python adaptive_mold/tools/search_base.py --polar 1600,2400,200 --angles 0,330,30
python adaptive_mold/tools/search_base.py --polar 1800,2000,100 --angles 150,210,15 --apply
```

몰드 중심 기준 **고리**를 훑어 도달·간섭·가동범위·이송을 모두 통과하는 자리를
찾고 관절 여유가 큰 순서로 보고합니다(지도 + 상위 목록). 사각 격자(`--step`/
`--span`)도 되지만 가능한 자리가 고리 모양이라 대부분을 헛돕니다.

**후보당 약 8초**입니다(기각되는 자리가 더 느립니다 — IK가 수렴하지 못해 반복을
다 씁니다). 진행 상황은 `adaptive_mold/grasshopper/_search_base_log.txt`에
흘려 쓰므로 도는 중에 볼 수 있습니다.

`--apply`는 `robot_base_pt`를 최적점으로 옮기고 **방향선도 같이 맞춥니다** —
점만 옮기면 살아 있는 파이프라인은 옛 선 방향을 써서 탐색한 자세와 달라집니다.

## 파라미터 관리

```
python adaptive_mold/tools/build_gh_components.py [Play|Robot]
python adaptive_mold/tools/apply_param_docs.py      # 코드를 넣으면 툴팁이 지워진다
```

## 공통: platform_path 입력

두 컴포넌트 모두 **platform_path** (str) 입력이 필요합니다.

- **값**: `ljk_facade_platform` repo **root** 폴더 경로
- **예**: `C:\Users\leeja\Documents\dev\26_AdaptiveMold_development`
- Panel 컴포넌트에 상수로 한 번 넣어 두고 재사용하는 것을 권장합니다.

## AMv1 Bridge

1. GhPython Script 컴포넌트 추가
2. `gh_scripts/AMv1_Bridge.py` 내용 붙여넣기 (또는 외부 파일 로드)
3. Inputs 설정:

| Input | 타입 | 설명 |
|---|---|---|
| `platform_path` | str | repo root (필수) |
| `pull` | bool | True = REST pull |
| `api_url` | str | `http://127.0.0.1:8000` |

4. Outputs: `width`, `length`, `spacing`, `max_height`, `min_height`, `rod_base_length`, `panel_name`, `compute_requested`, `gh_connected`, `status`, `message`

## AdaptiveMold v1

1. GhPython Script 컴포넌트 추가
2. `gh_scripts/AdaptiveMold_v1.py` 내용 붙여넣기
3. Inputs: `platform_path` + 곡면/파라미터/모델 (README 상단 주석 참고)
4. Bridge 출력을 width/length/spacing 등에 연결 가능

`compute_requested=True`이면 AMv1의 `compute`를 True로 설정하세요.

## 사용 순서

1. API 서버 실행 (`python -m api.server`)
2. Dashboard 실행 (`cd dashboard && npm run dev`)
3. GH **Bridge** → 파라미터 pull
4. GH **AMv1** → `compute=True`, `sync_to_dashboard=True`

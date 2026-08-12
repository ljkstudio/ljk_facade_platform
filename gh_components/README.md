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
(정본: `param_docs.py`, 현재 112개).

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

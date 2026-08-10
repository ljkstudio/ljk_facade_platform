# Grasshopper Components

GhPython 컴포넌트용 **RunScript 파일**은 `gh_scripts/` 폴더에 있습니다.

| 파일 | 용도 |
|---|---|
| `gh_scripts/AMv1_Bridge.py` | 대시보드 파라미터 pull |
| `gh_scripts/AdaptiveMold_v1.py` | AdaptiveMold 계산 + sync |
| `gh_scripts/AMv1_Inspect.py` | **몰드 시각화 — 핀·데크·이탈량을 보며 판단** |

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

# LJK Facade Platform — Dashboard (Track 1)

React + Vite 대시보드. REST API를 통해 Grasshopper와 통신합니다.

## 실행

```powershell
# 1) API 서버 (repo root)
pip install -e ".[dev]"
python -m api.server

# 2) 대시보드 (별도 터미널)
cd dashboard
npm install
npm run dev
```

브라우저: http://localhost:5173

## GH ↔ Dashboard 통신 흐름

1. 대시보드에서 파라미터 수정 → `PUT /api/session/params`
2. **GH 재계산 요청** 클릭 → `POST /api/session/compute-request`
3. Grasshopper **AMv1 Bridge** (pull) → 세션 파라미터 수신
4. Grasshopper **AdaptiveMold v1** (compute + sync) → `POST /api/session/sync`
5. 대시보드 3초 polling으로 결과 표시

## 화면

- **AdaptiveMold v1**: 파라미터 슬라이더, 3D pin grid, 리포트
- **프로젝트 보드**: 세션/프로젝트 목록

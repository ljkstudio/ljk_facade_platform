"""Session endpoints — GH ↔ Dashboard communication."""

from fastapi import APIRouter

from api.schemas.geometry.adaptive_mold import (
    GhPingRequest,
    ParamsUpdateRequest,
    SessionStateSchema,
    SyncRequest,
)
from api.store import store

router = APIRouter(prefix="/api/session", tags=["session"])


@router.get("", response_model=SessionStateSchema)
def get_session() -> SessionStateSchema:
    """현재 세션 상태 조회 (대시보드 polling / GH pull)."""
    return store.get_session()


@router.put("/params", response_model=SessionStateSchema)
def update_params(body: ParamsUpdateRequest) -> SessionStateSchema:
    """대시보드에서 파라미터 업데이트."""
    return store.update_params(body.params)


@router.post("/compute-request", response_model=SessionStateSchema)
def request_compute() -> SessionStateSchema:
    """대시보드에서 GH 재계산 요청."""
    return store.request_compute()


@router.post("/sync", response_model=SessionStateSchema)
def sync_from_gh(body: SyncRequest) -> SessionStateSchema:
    """GH에서 계산 결과를 API로 동기화."""
    return store.sync_from_gh(body.result, body.params)


@router.post("/gh-ping", response_model=SessionStateSchema)
def gh_ping(body: GhPingRequest) -> SessionStateSchema:
    """GH Bridge heartbeat."""
    return store.gh_ping(body.client_id)


@router.get("/projects")
def list_projects() -> list:
    """프로젝트 보드용 목록."""
    return store.list_projects()

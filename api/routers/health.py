"""Health check endpoints."""

from fastapi import APIRouter

from api.store import store

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check() -> dict:
    """서버 및 GH 연결 상태."""
    session = store.get_session()
    return {
        "status": "ok",
        "gh_connected": session.gh_connected,
        "session_status": session.status,
    }

"""In-memory session store for GH ↔ Dashboard communication."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Optional

from api.schemas.geometry.adaptive_mold import (
    AdaptiveMoldParamsSchema,
    AdaptiveMoldResultSchema,
    ProjectSummarySchema,
    SessionStateSchema,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """Thread-safe in-memory session store (Phase 1)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session = SessionStateSchema()
        self._projects: dict[str, SessionStateSchema] = {}

    def get_session(self) -> SessionStateSchema:
        with self._lock:
            return deepcopy(self._session)

    def update_params(self, params: AdaptiveMoldParamsSchema) -> SessionStateSchema:
        with self._lock:
            self._session.params = params
            if self._session.status == "synced":
                self._session.status = "idle"
            self._save_project_snapshot()
            return deepcopy(self._session)

    def request_compute(self) -> SessionStateSchema:
        with self._lock:
            self._session.status = "compute_requested"
            self._session.compute_requested_at = _utc_now()
            self._session.error_message = None
            return deepcopy(self._session)

    def sync_from_gh(
        self,
        result: AdaptiveMoldResultSchema,
        params: Optional[AdaptiveMoldParamsSchema] = None,
    ) -> SessionStateSchema:
        with self._lock:
            if params is not None:
                self._session.params = params
            self._session.result = result
            self._session.status = "synced"
            self._session.last_sync_at = _utc_now()
            self._session.gh_connected = True
            self._session.error_message = None
            self._save_project_snapshot()
            return deepcopy(self._session)

    def gh_ping(self, client_id: str = "grasshopper") -> SessionStateSchema:
        with self._lock:
            self._session.gh_connected = True
            self._session.last_gh_ping_at = _utc_now()
            return deepcopy(self._session)

    def set_error(self, message: str) -> SessionStateSchema:
        with self._lock:
            self._session.status = "error"
            self._session.error_message = message
            return deepcopy(self._session)

    def list_projects(self) -> list[ProjectSummarySchema]:
        with self._lock:
            items = []
            for pid, session in self._projects.items():
                count = 0
                if session.result:
                    count = session.result.nx * session.result.ny
                items.append(
                    ProjectSummarySchema(
                        project_id=pid,
                        project_name=session.project_name,
                        status=session.status,
                        panel_name=session.params.panel_name,
                        actuator_count=count,
                        last_sync_at=session.last_sync_at,
                    )
                )
            if not items:
                items.append(
                    ProjectSummarySchema(
                        project_id=self._session.project_id,
                        project_name=self._session.project_name,
                        status=self._session.status,
                        panel_name=self._session.params.panel_name,
                        actuator_count=(
                            self._session.result.nx * self._session.result.ny
                            if self._session.result
                            else 0
                        ),
                        last_sync_at=self._session.last_sync_at,
                    )
                )
            return items

    def _save_project_snapshot(self) -> None:
        self._projects[self._session.project_id] = deepcopy(self._session)


# Singleton used by FastAPI
store = SessionStore()

"""AMv1 Bridge — GH ↔ Dashboard 통신 전용 컴포넌트.

대시보드에서 변경된 파라미터를 pull하고, compute 요청 상태를 확인합니다.

GhPython RunScript:

    import sys
    ROOT = r"C:\\Users\\leeja\\Documents\\dev\\26_AdaptiveMold_development"
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from gh_components.bridge_pull import ghpython_run

    (width, length, spacing, max_height, min_height, rod_base_length,
     panel_name, compute_requested, gh_connected, status, message) = ghpython_run(
        pull, api_url, ghenv.Component)
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from gh_components.bridge_client import BridgeClient, DEFAULT_API_URL  # noqa: E402
from gh_components.gh_utils import add_error, add_remark, add_warning  # noqa: E402
from gh_components.serializers import session_params_to_gh  # noqa: E402


def ghpython_run(pull=True, api_url=None, platform_path=None, component=None):
    """대시보드 세션에서 파라미터를 pull합니다.

    Args:
        pull: True일 때만 REST 호출.
        api_url: REST API base URL.
        platform_path: repo root (검증용, 선택).
        component: GhPython 컴포넌트 인스턴스.
    """
    if platform_path:
        from gh_components.path_setup import setup_platform_paths

        ok, msg = setup_platform_paths(platform_path, include_adaptive_src=False)
        if not ok:
            add_error(component, msg)
            return (
                None, None, None, None, None, None, "",
                False, False, "error", msg,
            )

    if not pull:
        return (
            None, None, None, None, None, None, "",
            False, False, "idle", "Pull disabled",
        )

    client = BridgeClient(api_url or DEFAULT_API_URL)
    ok_ping, _, err_ping = client.gh_ping()
    if not ok_ping:
        add_warning(component, "Bridge: {}".format(err_ping))
        return (
            None, None, None, None, None, None, "",
            False, False, "error", err_ping,
        )

    ok, session, err = client.get_session()
    if not ok or session is None:
        add_error(component, "Bridge get_session: {}".format(err))
        return (
            None, None, None, None, None, None, "",
            False, False, "error", err,
        )

    params = session_params_to_gh(session)
    status = session.get("status", "idle")
    gh_connected = session.get("gh_connected", False)

    if params.get("compute_requested"):
        add_remark(component, "Dashboard requested compute — set AMv1 compute=True")

    message = "Session: {} | GH connected".format(status)
    return (
        params["width"],
        params["length"],
        params["spacing"],
        params["max_height"],
        params["min_height"],
        params["rod_base_length"],
        params["panel_name"],
        params["compute_requested"],
        gh_connected,
        status,
        message,
    )

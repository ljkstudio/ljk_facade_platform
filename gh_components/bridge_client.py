# -*- coding: utf-8 -*-
"""REST API client for GH ↔ Dashboard communication (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


DEFAULT_API_URL = "http://127.0.0.1:8000"


class BridgeClient:
    """Grasshopper에서 REST API와 통신하는 클라이언트."""

    def __init__(self, base_url: str = DEFAULT_API_URL, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
    ) -> tuple[bool, Any, str]:
        url = "{}{}".format(self.base_url, path)
        data = None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return True, None, ""
                return True, json.loads(raw), ""
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                detail = str(e)
            return False, None, "HTTP {}: {}".format(e.code, detail)
        except urllib.error.URLError as e:
            return False, None, "Connection failed: {}".format(e.reason)
        except Exception as e:
            return False, None, str(e)

    def ping(self) -> tuple[bool, str]:
        ok, data, err = self._request("GET", "/api/health")
        if not ok:
            return False, err
        return True, "API ok (gh_connected={})".format(
            data.get("gh_connected") if data else False
        )

    def gh_ping(self) -> tuple[bool, dict, str]:
        return self._request("POST", "/api/session/gh-ping", {"client_id": "grasshopper"})

    def get_session(self) -> tuple[bool, dict, str]:
        return self._request("GET", "/api/session")

    def sync_result(
        self,
        result_payload: dict,
        params_payload: Optional[dict] = None,
    ) -> tuple[bool, dict, str]:
        body = {"result": result_payload}
        if params_payload is not None:
            body["params"] = params_payload
        return self._request("POST", "/api/session/sync", body)

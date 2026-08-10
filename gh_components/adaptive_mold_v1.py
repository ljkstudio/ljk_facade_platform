# -*- coding: utf-8 -*-
"""AdaptiveMold v1 — Grasshopper component adapter.

GhPython RunScript:

    import sys, os
    ROOT = r"C:\\Users\\leeja\\Documents\\dev\\26_AdaptiveMold_development"
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
        sys.path.insert(0, os.path.join(ROOT, "adaptive_mold", "src"))

    from gh_components.adaptive_mold_v1 import ghpython_run

    (positioned_srf, extended_srf, housings, rods, tops,
     pin_heights, pin_tops, grid_pts, clamp_flags,
     extension_flags, info, sync_ok, sync_msg) = ghpython_run(
        target_srf, base_plane, width, length, spacing,
        max_height, min_height, housing_model, rod_model,
        top_model, rod_base_length, compute,
        sync_to_dashboard, api_url, panel_name,
        ghenv.Component)
"""

from __future__ import annotations

import os
import sys

# Ensure legacy adaptive_mold src is importable
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ADAPTIVE_SRC = os.path.join(_REPO_ROOT, "adaptive_mold", "src")
for _p in (_REPO_ROOT, _ADAPTIVE_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import Rhino.Geometry as rg  # noqa: E402

from adaptive_mold_v1 import run_adaptive_mold  # noqa: E402
from gh_components.bridge_client import BridgeClient, DEFAULT_API_URL  # noqa: E402
from gh_components.gh_utils import add_error, add_remark, add_warning  # noqa: E402
from gh_components.serializers import params_to_payload, result_to_payload  # noqa: E402


def _compute_nx_ny(width, length, spacing):
    from grid import compute_grid_counts  # noqa: WPS433

    return compute_grid_counts(width, length, spacing)


def _sync_to_api(result, width, length, spacing, max_height, min_height,
                 rod_base_length, panel_name, base_plane, nx, ny,
                 opt_info, ext_method, api_url, component):
    client = BridgeClient(api_url or DEFAULT_API_URL)
    ok_ping, _, err_ping = client.gh_ping()
    if not ok_ping:
        add_warning(component, "Dashboard sync: {}".format(err_ping))
        return False, err_ping

    params_payload = params_to_payload(
        width, length, spacing, max_height, min_height,
        rod_base_length, panel_name, base_plane,
    )
    result_payload = result_to_payload(result, nx, ny, opt_info, ext_method)
    ok, _, err = client.sync_result(result_payload, params_payload)
    if not ok:
        add_warning(component, "Dashboard sync failed: {}".format(err))
        return False, err

    add_remark(component, "Synced to dashboard via REST")
    return True, "Synced OK"


def ghpython_run(
    target_srf,
    base_plane,
    width,
    length,
    spacing,
    max_height,
    min_height,
    housing_model,
    rod_model,
    top_model,
    rod_base_length,
    compute,
    sync_to_dashboard=False,
    api_url=None,
    panel_name="",
    platform_path=None,
    component=None,
):
    """AdaptiveMold v1 GH 컴포넌트 실행 + 선택적 대시보드 동기화."""
    if platform_path:
        from gh_components.path_setup import setup_platform_paths

        ok, msg = setup_platform_paths(platform_path, include_adaptive_src=True)
        if not ok:
            add_error(component, msg)
            return (
                None, None, [], [], [], [], [], [], [], [], msg, False, msg,
            )

    if base_plane is None:
        base_plane = rg.Plane.WorldXY

    result = run_adaptive_mold(
        target_srf,
        base_plane,
        width,
        length,
        spacing,
        max_height,
        min_height,
        housing_model,
        rod_model,
        top_model,
        rod_base_length,
        compute,
        component,
    )

    sync_ok = False
    sync_msg = "Sync disabled"

    if compute and sync_to_dashboard and result.pin_heights:
        try:
            nx, ny = _compute_nx_ny(
                float(width or 1000),
                float(length or 1000),
                float(spacing or 200),
            )
        except Exception:
            nx = ny = 0

        ext_method = ""
        if "Extension:" in result.info:
            for line in result.info.splitlines():
                if line.strip().startswith("Extension:"):
                    ext_method = line.split(":", 1)[1].strip()
                    break

        opt_info = ""
        if "Surface:" in result.info:
            for line in result.info.splitlines():
                if line.strip().startswith("Surface:"):
                    opt_info = line.split(":", 1)[1].strip()
                    break

        sync_ok, sync_msg = _sync_to_api(
            result,
            width,
            length,
            spacing,
            max_height,
            min_height,
            rod_base_length,
            panel_name,
            base_plane,
            nx,
            ny,
            opt_info,
            ext_method,
            api_url,
            component,
        )

    return (
        result.positioned_srf,
        result.extended_srf,
        result.housings,
        result.rods,
        result.tops,
        result.pin_heights,
        result.pin_tops,
        result.grid_pts,
        result.clamp_flags,
        result.extension_flags,
        result.info,
        sync_ok,
        sync_msg,
    )

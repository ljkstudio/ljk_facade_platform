"""AdaptiveMold v1 결과를 REST JSON payload로 변환."""

from __future__ import annotations

from typing import Any


def point_to_dict(pt) -> dict:
    return {"x": float(pt.X), "y": float(pt.Y), "z": float(pt.Z)}


def plane_to_dict(plane) -> dict:
    o = plane.Origin
    return {
        "origin": {"x": o.X, "y": o.Y, "z": o.Z},
        "xaxis": {"x": plane.XAxis.X, "y": plane.XAxis.Y, "z": plane.XAxis.Z},
        "yaxis": {"x": plane.YAxis.X, "y": plane.YAxis.Y, "z": plane.YAxis.Z},
    }


def params_to_payload(width, length, spacing, max_height, min_height,
                      rod_base_length, panel_name, base_plane) -> dict:
    payload = {
        "width": float(width),
        "length": float(length),
        "spacing": float(spacing),
        "max_height": float(max_height),
        "min_height": float(min_height),
        "rod_base_length": float(rod_base_length or 300.0),
        "panel_name": str(panel_name or ""),
    }
    if base_plane is not None:
        payload["base_plane"] = plane_to_dict(base_plane)
    return payload


def result_to_payload(result, nx, ny, opt_info="", ext_method="") -> dict:
    """AdaptiveMoldResult → REST SyncRequest.result dict."""
    fabricability = {
        "is_fabricable": True,
        "violations": [],
        "warnings": [],
        "max_pin_step_mm": 0.0,
        "max_pin_step_limit_mm": 50.0,
        "min_curvature_radius_mm": 0.0,
        "out_of_bounds_pin_count": sum(1 for e in result.extension_flags if e),
        "clamped_pin_count": sum(1 for c in result.clamp_flags if c),
    }

    if result.clamp_flags:
        heights = result.pin_heights
        max_step = 0.0
        for i in range(1, len(heights)):
            max_step = max(max_step, abs(heights[i] - heights[i - 1]))
        fabricability["max_pin_step_mm"] = max_step
        if max_step > 50.0:
            fabricability["warnings"].append(
                "Max pin step {:.1f}mm exceeds limit 50mm".format(max_step)
            )

    return {
        "nx": int(nx),
        "ny": int(ny),
        "grid_pts": [point_to_dict(p) for p in result.grid_pts],
        "pin_heights": [float(h) for h in result.pin_heights],
        "pin_tops": [point_to_dict(p) for p in result.pin_tops],
        "clamp_flags": [bool(c) for c in result.clamp_flags],
        "extension_flags": [bool(e) for e in result.extension_flags],
        "extension_method": str(ext_method),
        "optimization_info": str(opt_info),
        "info": str(result.info),
        "warnings": [],
        "fabricability": fabricability,
    }


def session_params_to_gh(session: dict) -> dict[str, Any]:
    """REST session.params → GH-friendly dict."""
    params = session.get("params", {})
    return {
        "width": params.get("width", 1000.0),
        "length": params.get("length", 1000.0),
        "spacing": params.get("spacing", 200.0),
        "max_height": params.get("max_height", 400.0),
        "min_height": params.get("min_height", 0.0),
        "rod_base_length": params.get("rod_base_length", 300.0),
        "panel_name": params.get("panel_name", ""),
        "compute_requested": session.get("status") == "compute_requested",
    }

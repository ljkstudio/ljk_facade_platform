# -*- coding: utf-8 -*-
"""
AdaptiveMold v1 — GhPython RunScript
====================================
Grasshopper GhPython 컴포넌트에 이 파일 내용을 붙여넣거나,
컴포넌트가 외부 .py를 로드하도록 설정하세요.

닉네임: AMv1
카테고리: AdaptiveMold / Core

Inputs (GhPython 컴포넌트에 추가):
  platform_path      str      ljk_facade_platform repo root 경로 (필수)
  target_srf         Brep/Surface  목표 곡면
  base_plane         Plane    베이스 평면 (기본 WorldXY)
  width              float    mold 가로 mm (기본 1000)
  length             float    mold 세로 mm (기본 1000)
  spacing            float    액추에이터 간격 mm (기본 200)
  max_height         float    최대 stroke mm (기본 400)
  min_height         float    최소 stroke mm (기본 0)
  housing_model      Brep     본체 (원점+Z, 선택)
  rod_model          Brep     로드 (원점+Z, 선택)
  top_model          Brep     상단 (원점+Z, 선택)
  rod_base_length    float    rod 기준 길이 mm (기본 300)
  compute            bool     True일 때만 계산
  sync_to_dashboard  bool     True이면 REST sync
  api_url            str      REST API 주소 (기본 http://127.0.0.1:8000)
  panel_name         str      패널 이름

Outputs:
  positioned_srf, extended_srf, housings, rods, tops
  pin_heights, pin_tops, grid_pts, clamp_flags, extension_flags
  info, sync_ok, sync_msg
"""

import os
import sys

_root = os.path.normpath(str(platform_path or "").strip().strip('"').strip("'"))
if not _root or not os.path.isdir(_root):
    raise ValueError("platform_path is required: {}".format(platform_path))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gh_components.path_setup import setup_platform_paths
from gh_components.adaptive_mold_v1 import ghpython_run

_ok, _msg = setup_platform_paths(platform_path, include_adaptive_src=True)
if not _ok:
    raise ValueError(_msg)

(
    positioned_srf,
    extended_srf,
    housings,
    rods,
    tops,
    pin_heights,
    pin_tops,
    grid_pts,
    clamp_flags,
    extension_flags,
    info,
    sync_ok,
    sync_msg,
) = ghpython_run(
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
    sync_to_dashboard,
    api_url,
    panel_name,
    platform_path,
    ghenv.Component,
)

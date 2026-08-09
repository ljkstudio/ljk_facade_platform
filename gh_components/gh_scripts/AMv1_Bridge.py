"""
AMv1 Bridge — GhPython RunScript
================================
Grasshopper GhPython 컴포넌트에 이 파일 내용을 붙여넣거나,
컴포넌트가 외부 .py를 로드하도록 설정하세요.

닉네임: AMv1Bridge
카테고리: AdaptiveMold / Core

Inputs (GhPython 컴포넌트에 추가):
  platform_path  str   ljk_facade_platform repo root 경로 (필수)
                       예: C:\\Users\\leeja\\Documents\\dev\\26_AdaptiveMold_development
  pull           bool  True일 때만 REST pull (기본 True)
  api_url        str   REST API 주소 (기본 http://127.0.0.1:8000)

Outputs:
  width, length, spacing, max_height, min_height, rod_base_length
  panel_name, compute_requested, gh_connected, status, message
"""

import os
import sys

_root = os.path.normpath(str(platform_path or "").strip().strip('"').strip("'"))
if not _root or not os.path.isdir(_root):
    raise ValueError("platform_path is required: {}".format(platform_path))
if _root not in sys.path:
    sys.path.insert(0, _root)

from gh_components.path_setup import setup_platform_paths
from gh_components.bridge_pull import ghpython_run

_ok, _msg = setup_platform_paths(platform_path, include_adaptive_src=False)
if not _ok:
    raise ValueError(_msg)

(
    width,
    length,
    spacing,
    max_height,
    min_height,
    rod_base_length,
    panel_name,
    compute_requested,
    gh_connected,
    status,
    message,
) = ghpython_run(pull, api_url, platform_path, ghenv.Component)

# -*- coding: utf-8 -*-
"""Grasshopper 컴포넌트에서 platform_path로 sys.path를 설정합니다."""

from __future__ import annotations

import os
import sys


def normalize_platform_path(platform_path):
    # type: (object) -> str
    """입력 경로 문자열을 정규화합니다."""
    if platform_path is None:
        return ""
    text = str(platform_path).strip().strip('"').strip("'")
    return os.path.normpath(text)


def setup_platform_paths(platform_path, include_adaptive_src=False):
    # type: (object, bool) -> tuple[bool, str]
    """repo root를 sys.path에 추가합니다.

    Args:
        platform_path: ljk_facade_platform repo root (예: C:\\...\\26_AdaptiveMold_development).
        include_adaptive_src: True이면 adaptive_mold/src도 추가 (AMv1용).

    Returns:
        (success, message) 튜플.
    """
    root = normalize_platform_path(platform_path)
    if not root:
        return False, "platform_path is required (repo root folder)"

    if not os.path.isdir(root):
        return False, "platform_path not found: {}".format(root)

    gh_components = os.path.join(root, "gh_components")
    if not os.path.isdir(gh_components):
        return False, "gh_components folder not found under: {}".format(root)

    paths = [root]
    if include_adaptive_src:
        adaptive_src = os.path.join(root, "adaptive_mold", "src")
        if not os.path.isdir(adaptive_src):
            return False, "adaptive_mold/src not found under: {}".format(root)
        paths.append(adaptive_src)

    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)

    return True, root

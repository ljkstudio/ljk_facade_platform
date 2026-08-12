# -*- coding: utf-8 -*-
# AMv1 RollerPath — 로봇암 롤러가 금속 박판을 몰드면에 눌러 앉히는 경로
#
# 계산은 adaptive_mold/src/toolpath.py 에 있다. 이 컴포넌트는 얇은 어댑터다.
#
# Inputs (전부 item, 비우면 기본값):
#   platform_path  str      repo root (필수)
#   mold_srf       Surface/Brep  성형면 = 내열 시트 상면 (필수)
#   base_plane     Plane    몰드 베이스. 비우면 WorldXY
#   sheet_t        float    금속 박판 두께, 없으면 1.5
#   roller_d       float    롤러 지름, 없으면 60
#   roller_w       float    롤러 폭(접촉선 길이), 없으면 80
#   stepover       float    패스 간격, 0이면 roller_w*0.5
#   passes         int      점진 가압 패스 수, 없으면 1
#   axis_mode      str      auto | u | v  (진행 방향 강제)
#   start_center   bool     중앙에서 시작해 좌우 교대, 없으면 True
#   compute        bool     False면 계산하지 않는다
#
# Outputs:
#   paths          롤러 중심 경로 (진행 순서대로)
#   targets        로봇 타겟 Plane (경로 순서대로 평탄화)
#   roller_lines   각 경로 시작점의 롤러 축 표시선
#   contact        판재-롤러 접촉점
#   info           진단 리포트

import sys
import os

import Rhino.Geometry as rg


_src = os.path.join(platform_path, "adaptive_mold", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_norm = os.path.normcase(os.path.normpath(_src))
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

from toolpath import generate_roller_paths


def _default(name, value, positive=False):
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


_default("sheet_t", 1.5, positive=True)
_default("roller_d", 60.0, positive=True)
_default("roller_w", 80.0, positive=True)
_default("stepover", 0.0)
_default("passes", 1, positive=True)
_default("axis_mode", "auto")
_default("start_center", True)

if base_plane is None:
    base_plane = rg.Plane.WorldXY


paths = []
targets = []
roller_lines = []
contact = []
info = ""


if compute and mold_srf is not None:
    r = generate_roller_paths(
        mold_srf,
        base_plane=base_plane,
        sheet_t=sheet_t,
        roller_d=roller_d,
        roller_w=roller_w,
        stepover=stepover,
        passes=int(passes),
        axis_mode=str(axis_mode),
        start_center=bool(start_center),
    )

    paths = r.paths
    roller_lines = r.roller_lines
    for group in r.targets:
        targets.extend(group)
    for group in r.contact:
        contact.extend(group)

    d = r.info
    if d.get("error"):
        info = "오류: {}".format(d["error"])
    else:
        so = d.get("stepover_measured")
        seat_max = d.get("seat_error_max")
        lines = [
            "AMv1 RollerPath",
            "=" * 40,
            "진행 방향:   {} 매개방향  (축은 그 직각)".format(d["travel"]),
            "             <- 롤러는 진행 방향으로만 굽힘을 준다.",
            "                축 방향에 곡률이 있으면 접촉선이 앉지 않는다.",
            "",
            "패스:        {}본 x {}회 = {}개  (타겟 {}개)".format(
                d["n_paths_per_pass"], d["passes"], d["path_count"],
                d["target_count"]),
            "간격:        설정 {:.1f} mm  실측 {} mm".format(
                d["stepover_set"],
                "{:.1f} ~ {:.1f}".format(so[0], so[1]) if so else "?"),
            "             <- 매개변수 등분이라 실측이 설정과 다를 수 있다",
            "롤러 중심:   접촉점에서 법선으로 {:.1f} mm (판두께 {:.1f} + 반지름 {:.1f})".format(
                d["roller_center_offset"], sheet_t, roller_d / 2.0),
            "",
            "접촉선 앉음: 최대 틈 {} mm  (롤러 폭 {:.0f} 기준)".format(
                "{:.3f}".format(seat_max) if seat_max is not None else "?",
                roller_w),
            "             <- 0에 가까울수록 선접촉. 커지면 점접촉이 되어",
            "                하중이 몰리고 판재에 흠이 난다. 형상 자체의",
            "                한계이지 경로 문제가 아니다 — 롤러 폭을 줄이거나",
            "                구면 공구로 바꿔야 한다.",
        ]
        if d.get("progressive_is_geometric"):
            lines += [
                "",
                "** 점진 가압 중간 깊이는 기하 가정이다.",
                "   실제 중간 형상은 해석(또는 실측) 없이는 알 수 없다.",
            ]
        lines += [
            "",
            "** 순서는 중앙 → 좌우 교대. 주름은 자유 경계에서 시작해 안으로",
            "   밀려오므로, 중앙을 먼저 앉히고 여분을 바깥으로 밀어낸다.",
        ]
        info = "\n".join(lines)
else:
    info = "compute=True 로 설정하고 mold_srf(성형면)를 연결하세요."

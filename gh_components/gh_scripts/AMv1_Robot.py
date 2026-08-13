# -*- coding: utf-8 -*-
# AMv1 Robot — IRB6700이 롤러 툴패스를 추종할 수 있는지 보고, 포즈를 만든다
#
# 기구학은 adaptive_mold/src/robot.py (웹 시뮬레이터에서 이식, 대조 완료).
#
# Inputs:
#   platform_path  str     repo root (필수)
#   targets        Plane*  AMv1 RollerPath 의 targets (list access)
#   move_kind      str*    같은 순서의 구간 종류 (선택). 있으면 구간별로 집계한다
#   robot_base     Plane   로봇 베이스 평면. 비우면 base_pt/base_dir 를 본다
#   base_pt        Point   베이스 원점 (Rhino 에서 점을 찍어 물린다)
#   base_dir       Curve   로봇이 바라보는 방향 (Rhino 에서 선을 그어 물린다)
#                          선만 주면 선의 시작점이 원점이 된다
#                          Line 이 아니라 Curve 로 받는다 — Rhino 의 선은
#                          LineCurve 객체이고 GH_Line 은 참조가 안 된다 떨어진 곳
#   frame          int     이 인덱스의 포즈로 로봇을 그린다 (애니메이션 슬라이더)
#   step           int     N개마다 하나만 계산, 없으면 1 (미리보기 가속)
#   iterations     int     IK 최대 반복, 없으면 30
#   rot_weight     float   자세 가중치, 없으면 0.4 (0이면 위치 전용)
#   compute        bool
#
# Outputs:
#   links          현재 frame 의 로봇 링크 선
#   tcp            현재 frame 의 TCP Plane
#   poses          전 구간 관절각 (6개씩 이어진 평탄 목록, deg)
#   reach_err      타겟별 위치 오차 (mm)
#   unreachable    오차가 큰 타겟의 인덱스
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

import robot as rb


def _default(name, value, positive=False):
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


_default("frame", 0)
_default("step", 1, positive=True)
_default("iterations", 30, positive=True)
_default("rot_weight", 0.4)

REACH_TOL_MM = 2.0          # 이보다 크면 롤러가 표면에서 뜬 것으로 본다


links = []
tcp = None
poses = []
reach_err = []
unreachable = []
info = ""


if compute and targets:
    tgts = list(targets)

    # 베이스 위치 — 주지 않으면 몰드 중심에서 -X로 1900mm.
    # 웹 시뮬레이터가 베드를 X=1.4m에 두고 도달 스위트스폿을 확인한 값에서 왔다.
    # 베이스 결정은 robot.py 한 곳에 있다 — AMv1 Play 가 같은 함수를 써야
    # 로봇이 계산된 위치에 그려진다
    robot_base, base_src = rb.resolve_base_plane(
        robot_base=robot_base,
        base_pt=globals().get("base_pt"),
        base_dir=globals().get("base_dir"),
        targets=tgts)

    picked = list(range(0, len(tgts), int(step)))
    sampled = [tgts[i] for i in picked]

    pose_list, results, flips = rb.track_toolpath(
        sampled, base_plane=robot_base,
        iterations=int(iterations), rot_weight=rot_weight)

    for p in pose_list:
        for j in rb.JOINT_NAMES:
            poses.append(p[j])

    reach_err = [r.pos_err_mm for r in results]
    unreachable = [picked[i] for i, r in enumerate(results)
                   if r.pos_err_mm > REACH_TOL_MM]

    # 현재 프레임 그리기
    fi = int(frame)
    if fi < 0:
        fi = 0
    if fi >= len(pose_list):
        fi = len(pose_list) - 1
    links = rb.link_lines_mm(pose_list[fi], base_plane=robot_base)
    tcp = rb.tcp_plane_mm(pose_list[fi])
    tcp.Transform(rg.Transform.PlaneToPlane(rg.Plane.WorldXY, robot_base))

    # 집계
    at_limit = {}
    for r in results:
        for j in r.at_limit:
            at_limit[j] = at_limit.get(j, 0) + 1

    worst_i = 0
    for i, r in enumerate(results):
        if r.pos_err_mm > results[worst_i].pos_err_mm:
            worst_i = i

    seconds = rb.cycle_time(pose_list)

    kinds = {}
    if move_kind:
        mk = list(move_kind)
        for i, r in zip(picked, results):
            if i < len(mk):
                k = str(mk[i])
                cur = kinds.get(k, [0, 0.0])
                cur[0] += 1
                cur[1] = max(cur[1], r.pos_err_mm)
                kinds[k] = cur

    lines = [
        "AMv1 Robot — IRB 6700-150/3.20",
        "=" * 44,
        "베이스:      {}".format(base_src),
        "             원점 ({:.0f}, {:.0f}, {:.0f})  바라보는 방향 ({:.2f}, {:.2f})".format(
            robot_base.Origin.X, robot_base.Origin.Y, robot_base.Origin.Z,
            robot_base.XAxis.X, robot_base.XAxis.Y),
        "             <- AMv1 Play 에 같은 입력을 물려야 그림이 맞는다",
        "타겟:        {}개 중 {}개 계산 (step {})".format(
            len(tgts), len(sampled), int(step)),
        "",
        "위치 오차:   max {:.3f} mm  (타겟 #{})   평균 {:.3f} mm".format(
            max(reach_err) if reach_err else 0.0,
            picked[worst_i] if reach_err else -1,
            sum(reach_err) / len(reach_err) if reach_err else 0.0),
        "             <- {:.1f} mm 초과를 도달 실패로 본다".format(REACH_TOL_MM),
        "도달 실패:   {}개".format(len(unreachable)),
        "가동범위 접촉: {}".format(at_limit if at_limit else "없음"),
        "             <- 축이 한계에 걸리면 그 자세를 못 만든 것이다",
        "롤러 대칭 활용: {}회 뒤집음 / {}개".format(flips, len(sampled)),
        "             <- 원통 롤러는 축 부호가 무의미하다. 이 자유도를 쓰지",
        "                않으면 지그재그마다 손목이 180도씩 감긴다",
        "",
        "관절 이동시간: {:.1f} 초 ({:.1f} 분) — 전 구간을 관절 최대속도로 갔을 때".format(
            seconds, seconds / 60.0),
        "             <- 이것을 사이클 타임으로 읽지 말 것. 성형 구간의 속도는",
        "                로봇 능력이 아니라 공정(가열 판재의 이송 속도)이 정한다.",
        "                실제 시간은 AMv1 Play 의 duration 을 볼 것 —",
        "                실측 feed 50 mm/s 에서 592.8 초로 13.8배다.",
    ]
    if kinds:
        lines.append("")
        lines.append("구간별 최대 오차:")
        for k in sorted(kinds.keys()):
            n, e = kinds[k]
            lines.append("  {:<9} {:>5}개  max {:.3f} mm".format(k, n, e))
    if int(step) > 1:
        lines += [
            "",
            "** step>1 이면 이 오차는 신뢰할 수 없다.",
            "   IK가 앞 포즈를 시드로 쓰는데 타겟을 건너뛰면 시드가 멀어져",
            "   수렴이 깨진다 (실측: step=10에서 max 1,850 mm).",
            "   미리보기 전용으로만 쓰고 판정은 step=1 로 할 것.",
        ]
    if unreachable:
        lines += [
            "",
            "** 도달 실패가 있다. 오차가 큰 지점은 롤러가 표면에서 뜬다.",
            "   실측: base_x -1400/-1300/-1200 비교에서 -1400이 최선이었고,",
            "   가까이 옮기면 나빠진다. X 이동으로는 더 못 줄인다 —",
            "   몰드 회전·높이(z)·베이스 기울기를 봐야 한다.",
        ]
    info = "\n".join(lines)

else:
    info = "compute=True 로 설정하고 RollerPath 의 targets 를 연결하세요."

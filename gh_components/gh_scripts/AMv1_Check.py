# -*- coding: utf-8 -*-
# AMv1 Check — 이 경로를 이 로봇이 실제로 갈 수 있는가 (판정 전용)
#
# ──────────────────────────────────────────────────────────
# 왜 재생과 나누는가
# ──────────────────────────────────────────────────────────
#
# 판정과 재생은 **바뀌는 이유가 다르다.** 판정은 공학적 기준(가동범위·정격속도·
# 여유)이 바뀔 때, 재생은 보이는 방식(색·프레임률·무엇을 그릴지)이 바뀔 때
# 손댄다. 한 컴포넌트에 넣으면 색을 고치려다 판정을 깨고, 그 반대도 된다.
#
# 그리고 판정은 **무겁고 재생은 실시간이어야 한다.** 나눠 두면 재생을 돌리는
# 동안 판정을 다시 계산하지 않는다.
#
# 세 가지를 본다. 서로 다른 질문이고 손볼 곳도 다르다:
#
#   도달   그 점에 닿는가            -> 못 닿으면 경로·베이스 위치
#   기구   그렇게 움직일 수 있는가    -> 걸리면 베이스 위치·feed·오버라이드
#   간섭   몰드를 치지 않는가        -> 치면 베이스 위치·접근 높이
#
# ──────────────────────────────────────────────────────────
# 판정이 아니라 여유를 낸다
# ──────────────────────────────────────────────────────────
#
# "된다/안 된다"는 기준값을 어떻게 잡았는지에 달린 이진값이다. 위치를 잡을 때
# 필요한 것은 **얼마나 아슬아슬한가**다. 그래서 관절 여유(deg)·간섭 여유(mm)·
# 최소 오버라이드(%)를 각각 숫자로 낸다.
#
# `bad` 는 문제가 있는 구간 인덱스다. **Play 는 이유를 모른 채 그 구간을 다른
# 색으로 칠한다** — 판정 논리가 재생 쪽으로 새지 않게 하는 경계다.
#
# Inputs:
#   platform_path  str      repo root (필수)
#   robot_plane    Plane    AMv1 Base 의 plane. **Robot·Play 와 같은 것**
#   poses          float*   AMv1 Robot 의 poses (6개씩 평탄, list)
#   reach_err      float*   AMv1 Robot 의 reach_err — **연결할 것.**
#                           없으면 못 닿는 자리도 되는 것처럼 보인다
#   targets        Plane*   AMv1 RollerPath 의 targets (list)
#   move_kind      str*     같은 순서의 구간 종류 (list)
#   pin_tops       Point3d* 핀 상단 (list) — 몰드 발자국·높이장용
#   feed           float    롤러 이송 mm/s, 없으면 50            <- 가정치
#   joint_scale    float    프로그램 속도 오버라이드 0~1, 없으면 0.25
#   mold_srf       Brep     성형면. 있으면 높이장을 이것으로 만든다
#   stack          float    핀 상단에서 성형면까지 두께 (mm), 없으면 28
#   parts_file     str      로봇 파트 .3dm. 비우면 저장소 기본 경로
#   check_hit      bool     팔 간섭 스크리닝 실행, 없으면 False
#   hit_margin     float    간섭 여유 (mm), 없으면 30
#   hit_step       int      N개마다 하나만 검사, 없으면 1
#
# Outputs:
#   report       사람이 읽는 판정 리포트
#   ok           세 판정 모두 통과했는가 (bool)
#   warn         한 줄 경고 목록 — Play 의 warn 에 물려 HUD 에 띄운다
#   bad          문제가 있는 구간 인덱스 (int list) — Play 가 색으로 쓴다
#   j_margin     최소 관절 여유 (deg)
#   min_clear    최소 간섭 여유 (mm). 미검사면 없음
#   min_override feed 를 유지하는 최소 오버라이드 비율 (0~1)
#   fail_pts     못 닿는 타겟 점
#   hit_pts      팔이 몰드에 걸리는 자리의 타겟 점

import sys
import os

import Rhino.Geometry as rg
import scriptcontext as sc


_src = os.path.join(platform_path, "adaptive_mold", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_norm = os.path.normcase(os.path.normpath(_src))
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb
import robot_body as rbb
import playback as pb
import collision as col
import mechanics as mc


def _default(name, value, positive=False):
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


_default("feed", pb.DEFAULT_FEED, positive=True)
_default("joint_scale", pb.DEFAULT_JOINT_SCALE, positive=True)
_default("stack", 28.0)
_default("check_hit", False)
_default("hit_margin", col.DEFAULT_MARGIN)
_default("hit_step", 1, positive=True)
_default("parts_file", "")

if not parts_file:
    parts_file = os.path.join(platform_path, "adaptive_mold", "grasshopper",
                              "irb6700_parts.3dm")

pose_flat = [float(v) for v in (poses or [])]
pose_list = pb.poses_from_flat(pose_flat) if pose_flat else []
tgts = [t for t in (targets or []) if t is not None]
tgt_pts = [t.Origin for t in tgts]
kinds = [str(k) for k in (move_kind or [])]
pins = [p for p in (pin_tops or []) if p is not None]
errs = [float(e) for e in (reach_err or [])]

warn = []
bad_set = set()

# 포즈와 타겟 개수가 다르면 어느 포즈가 어느 타겟인지 알 수 없다.
# 억지로 맞추면 엉뚱한 구간을 실패로 칠하게 되고 그게 더 나쁘다.
step_mismatch = bool(pose_list) and bool(tgt_pts) and \
    len(pose_list) != len(tgt_pts)
if step_mismatch:
    tgt_pts = []
    kinds = []
    warn.append("포즈 {}개 != 타겟 {}개 — Robot 이 step>1 로 돌았다".format(
        len(pose_list), len(tgts)))

err_mismatch = bool(errs) and bool(pose_list) and len(errs) != len(pose_list)
if err_mismatch:
    warn.append("reach_err 개수가 포즈와 달라 버렸다 — 도달 판정 못 함")
    errs = []


# ── 1. 도달 ────────────────────────────────────────────
fail_idx = [i for i, e in enumerate(errs) if e > pb.REACH_TOL_MM]
err_max = max(errs) if errs else None
fail_pts = [tgt_pts[i] for i in fail_idx if i < len(tgt_pts)]
for i in fail_idx:
    bad_set.add(i)
    if i > 0:
        bad_set.add(i - 1)          # 구간 양 끝 중 하나라도 못 닿으면 그 구간


# ── 2. 기구 ────────────────────────────────────────────
# 포즈 목록의 산술이라 값이 싸다 — 토글 없이 항상 돈다.
mech = None
if pose_list:
    mech = mc.check(pose_list, tgt_pts if tgt_pts else None,
                    kinds if kinds else None,
                    feed=float(feed), joint_scale=float(joint_scale))


# ── 3. 간섭 ────────────────────────────────────────────
# **검사가 아니라 스크리닝이다** — 표본으로 본다(collision.py 주석 참조).
PARTS_KEY = "AMv1_Check_parts"
PARTS = {}
parts_note = ""

hitfield = None
hit_sum = None
hit_pts = []

if check_hit and pose_list:
    if not os.path.isfile(parts_file):
        parts_note = "파트 파일이 없다"
    else:
        mt = os.path.getmtime(parts_file)
        cached = sc.sticky.get(PARTS_KEY)
        if cached and cached[0] == parts_file and cached[1] == mt:
            PARTS = cached[2]
            parts_note = "캐시"
        else:
            PARTS = rbb.load_parts(parts_file)
            sc.sticky[PARTS_KEY] = (parts_file, mt, PARTS)
            parts_note = "새로 읽음"

if check_hit and PARTS and pose_list:
    if mold_srf is not None:
        hitfield = col.Heightfield.from_surface(mold_srf, nx=40, ny=40)
    if hitfield is None and pins:
        # 핀 격자에서 만든다. 행 길이는 점 순서에서 유도한다 — 입력으로 받지
        # 않으면 잘못 연결될 여지가 없다.
        nx = len(pins)
        if len(pins) >= 3:
            d0 = pins[0].DistanceTo(pins[1])
            if d0 > 0:
                for i in range(1, len(pins) - 1):
                    if pins[i].DistanceTo(pins[i + 1]) > d0 * 1.5:
                        nx = i + 1
                        break
        ny = (len(pins) // nx) if nx else 0
        if nx >= 2 and ny >= 2:
            hitfield = col.Heightfield.from_grid_points(
                pins, nx, ny, offset=float(stack))

    if hitfield is not None:
        samples = col.sample_points(PARTS)
        pens, whos = col.scan_poses(
            pose_list, samples, hitfield, base_plane=robot_plane,
            margin=float(hit_margin), step=int(hit_step))
        hit_sum = col.summarize(pens, whos, step=int(hit_step),
                               total=len(pose_list), margin=float(hit_margin))
        for i in hit_sum["hit_indices"]:
            bad_set.add(i)
            if i < len(tgt_pts):
                hit_pts.append(tgt_pts[i])


# ── 판정 모으기 ────────────────────────────────────────
j_margin = mech["limits"]["worst"] if mech else None
min_override = mech["speed"]["min_override"] if mech else None
min_clear = hit_sum["min_clear"] if hit_sum else None
bad = sorted(bad_set)

# **통과도 적는다.** warn 은 경고 목록이 아니라 **HUD 에 띄울 판정 요약**이다.
# 통과를 안 적으면 화면에서 "판정했고 괜찮다"와 "판정 자체를 안 했다"가
# 구분되지 않는다 — 그 구분이 이 프로젝트에서 가장 자주 문제가 됐다.
if fail_idx:
    warn.append("도달 실패 {}개 / {}  최대 {:.1f} mm".format(
        len(fail_idx), len(errs), err_max))
elif not errs:
    warn.append("reach_err 미연결 — 도달 판정을 하지 못했다")
else:
    warn.append("도달 OK  최대 {:.2f} mm".format(err_max))

if mech:
    if mech["problems"]:
        warn.append("기구 문제: " + " / ".join(mech["problems"]))
    elif mech["tight"]:
        warn.append("기구 아슬아슬: " + " / ".join(mech["tight"]))

if hit_sum is not None:
    if hit_sum["hits"]:
        warn.append("팔 간섭 {}포즈  최대 {:.0f} mm".format(
            hit_sum["hits"], hit_sum["worst"]))
elif check_hit:
    warn.append("팔 간섭: 높이장을 못 만들었다 — mold_srf 나 pin_tops 확인")
else:
    warn.append("팔 간섭 미검사 (check_hit 를 켜세요)")

ok = bool(pose_list) and not fail_idx and bool(errs) \
    and (mech is not None and not mech["problems"]) \
    and (hit_sum is not None and not hit_sum["hits"])


# ── 리포트 ─────────────────────────────────────────────
lines = ["AMv1 Check", "=" * 44]

if not pose_list:
    lines.append("포즈가 없다 — AMv1 Robot 의 poses 를 연결하세요.")
else:
    lines.append("포즈 {}개 / 타겟 {}개".format(len(pose_list), len(tgts)))
    if robot_plane is not None:
        lines.append("베이스:      ({:.0f}, {:.0f}, {:.0f})  방향 ({:+.2f}, {:+.2f})".format(
            robot_plane.Origin.X, robot_plane.Origin.Y, robot_plane.Origin.Z,
            robot_plane.XAxis.X, robot_plane.XAxis.Y))
        lines.append("             <- AMv1 Base 에서 온 것. Robot·Play 와 같아야 한다")
    else:
        lines.append("** robot_plane 이 없다 — AMv1 Base 를 연결하세요.")
        lines.append("   없으면 로봇 좌표계로 계산해 전부 틀린 답이 나온다")

    lines.append("")
    lines.append("1. 도달")
    if not errs:
        lines.append("  reach_err 를 연결하지 않아 판정하지 못했다")
        lines.append("  <- 그러면 못 가는 위치도 되는 것처럼 보인다")
    else:
        lines.append("  실패 {}개 / {}개 ({:.1f}%)   최대 오차 {:.2f} mm".format(
            len(fail_idx), len(errs),
            100.0 * len(fail_idx) / len(errs), err_max))
        if fail_idx:
            lines.append("  <- 못 닿는 자세도 그려지기는 한다. IK 가 관절 한계에서")
            lines.append("     잘라내므로 화면에서는 그럴듯해 보인다")

    lines.append("")
    if mech:
        lines.append(mc.report(mech))
    else:
        lines.append("2. 기구: 포즈가 없어 판정하지 못했다")

    lines.append("")
    lines.append("3. 간섭")
    if hit_sum is not None:
        lines.append("  스크리닝 {}개 중 {}개 포즈 (여유 {:.0f} mm)".format(
            hit_sum["total"], hit_sum["checked"], float(hit_margin)))
        if hit_sum["min_clear"] is None:
            lines.append("  최소 여유: 판정 불가 (팔이 몰드 위를 지나지 않는다)")
        else:
            lines.append("  최소 여유: {:.0f} mm  <- margin 을 어떻게 잡아도 같은 값이다.".format(
                hit_sum["min_clear"]))
            lines.append("             형상이 정하는 실측값이므로 위치를 잡을 때")
            lines.append("             '얼마나 아슬아슬한가'를 이 숫자로 읽는다")
        if hit_sum["hits"]:
            lines.append("  걸림 {}포즈   최대 {:.0f} mm   처음 #{}".format(
                hit_sum["hits"], hit_sum["worst"], hit_sum["worst_at"]))
            for k in sorted(hit_sum["per_part"]):
                lines.append("    {:<10} {}포즈".format(
                    k, hit_sum["per_part"][k]))
        else:
            lines.append("  걸림 없음")
        lines.append("  ** 검사가 아니라 스크리닝이다. 표본으로 보므로 가느다란")
        lines.append("     돌출부는 빠져나갈 수 있다. 자기 간섭·프레임·주변")
        lines.append("     설비는 보지 않는다.")
        if hit_sum["step"] > 1:
            lines.append("  ** step={} 이라 사이 포즈는 보지 않았다.".format(
                hit_sum["step"]))
        if parts_note:
            lines.append("  파트 {}개 ({})".format(len(PARTS), parts_note))
    elif check_hit:
        lines.append("  높이장을 만들 수 없었다 — mold_srf 나 pin_tops 를 확인할 것")
        if parts_note:
            lines.append("  ({})".format(parts_note))
    else:
        lines.append("  미검사 (check_hit 를 켜면 훑는다)")

    lines.append("")
    lines.append("판정:        {}".format("통과" if ok else "걸림 또는 미판정"))
    for w in warn:
        lines.append("  - {}".format(w))
    lines.append("")
    lines.append("bad 구간 {}개 — Play 의 bad 에 물리면 그 구간을 다른 색으로".format(
        len(bad)))
    lines.append("그린다. warn 은 Play 의 warn 에 물려 HUD 에 띄운다.")

report = "\n".join(lines)

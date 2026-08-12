# -*- coding: utf-8 -*-
# AMv1 Play — 핀 상승과 로봇 성형을 실제 시간으로 재생한다
#
# 시간 계산은 adaptive_mold/src/playback.py 에 있다. 이 컴포넌트는 그리기와
# 타이머 수명 관리를 한다.
#
# ──────────────────────────────────────────────────────────
# 왜 이런 구조인가 — Grasshopper 는 연속 재계산을 하지 않는다
# ──────────────────────────────────────────────────────────
#
# GH 는 입력이 바뀔 때 한 번 계산하고 멈춘다. 그래서 컴포넌트가 스스로
# 프레임을 넘기며 움직이게 만들 수 없다. 타이머로 ExpireSolution 을 걸면
# 되긴 하지만 매 프레임 IK 체인 전체가 다시 도므로 실시간이 안 된다.
#
# 그래서 재생은 **GH 밖에서** 한다:
#   1) 계산은 한 번만 (타임라인을 미리 만든다)
#   2) Rhino.Display.DisplayConduit 이 뷰포트에 직접 그린다
#   3) WinForms Timer 가 벽시계 시간으로 프레임을 넘긴다
#   4) 둘 다 scriptcontext.sticky 에 담아 솔루션 사이에 살려 둔다
#
# 실측(Rhino 8.33): interval 33 ms 설정에 22 Hz, PostDrawObjects 는 틱당
# 2.15회 호출된다(열린 뷰포트 수). 프레임 예산이 좁으므로 **선과 폴리라인만**
# 그린다. Brep 을 그리면 재생이 늘어진다.
#
# **System.Timers.Timer 를 쓰면 안 된다** — 스레드풀에서 돌아 UI 스레드가
# 아닌 곳에서 Redraw 를 호출하게 되고, 그러면 Rhino 가 불안정해진다.
# WinForms Timer 는 UI 스레드에서 Tick 한다.
#
# 두 가지 모드:
#   play=False → 컨듀잇을 끄고, t 초 시점의 형상을 출력으로 낸다 (슬라이더 스크럽)
#   play=True  → 컨듀잇이 벽시계 시간으로 그린다. 출력은 t 시점에 멈춘다
#
# Inputs:
#   platform_path  str      repo root (필수)
#   pin_tops       Point3d* AMv1 Inspect 의 pin_tops (list)
#   base_plane     Plane    몰드 베이스. 비우면 WorldXY
#   pin_home       float    핀 출발 높이, 없으면 0
#   pin_speed      float    액추에이터 속도 mm/s, 없으면 50   <- 가정치
#   poses          float*   AMv1 Robot 의 poses (6개씩 평탄, list)
#   targets        Plane*   AMv1 RollerPath 의 targets (list)
#   move_kind      str*     같은 순서의 구간 종류 (list)
#   robot_base     Plane    AMv1 Robot 에 준 것과 같은 값
#   feed           float    롤러 이송 mm/s, 없으면 50          <- 가정치
#   joint_scale    float    공중 이동 속도 배율 0~1, 없으면 0.25
#   dwell          float    핀 상승 후 정지 시간, 없으면 1.0
#   t              float    스크럽 시각(초). play=True 면 시작 시각
#   play           bool     재생 (Boolean Toggle 을 붙인다)
#   loop           bool     끝나면 처음으로, 없으면 False
#   time_scale     float    재생 배속. 1.0 이 실제 속도
#   fps            int      목표 프레임률, 없으면 25
#   roller_d       float    롤러 지름(표시용), 없으면 60
#   show_path      bool     지나온 경로를 그린다, 없으면 True
#   solo           bool     재생 중 다른 컴포넌트 프리뷰를 끈다, 없으면 True
#
# Outputs:
#   pins       t 시점의 핀 (선)
#   deck       t 시점의 핀 상단 격자 (폴리라인)
#   links      t 시점의 로봇 링크
#   tcp        t 시점의 TCP Plane
#   roller     t 시점의 롤러 원
#   duration   전체 재생 길이 (초)
#   info       타임라인 리포트 + 실측 프레임률

import sys
import os

import clr
try:
    clr.AddReference("System.Windows.Forms")
except Exception:
    pass

import System
import System.Drawing as sd
import System.Windows.Forms as wf

import Rhino
import Rhino.Geometry as rg
import Rhino.Display as rd
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
import playback as pb


# sticky 키 — 컴포넌트가 여러 개 놓일 수 있으므로 인스턴스 GUID로 구분한다.
# 하나의 키를 공유하면 두 번째 컴포넌트가 첫 번째의 타이머를 죽인다.
KEY = "AMv1_Play_" + str(ghenv.Component.InstanceGuid)


def _default(name, value, positive=False):
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


_default("pin_home", 0.0)
_default("pin_speed", pb.DEFAULT_PIN_SPEED, positive=True)
_default("feed", pb.DEFAULT_FEED, positive=True)
_default("joint_scale", pb.DEFAULT_JOINT_SCALE, positive=True)
_default("dwell", 1.0)
_default("t", 0.0)
_default("play", False)
_default("loop", False)
_default("time_scale", 1.0, positive=True)
_default("fps", 25, positive=True)
_default("roller_d", 60.0, positive=True)
_default("show_path", True)
_default("solo", True)

if base_plane is None:
    base_plane = rg.Plane.WorldXY


C_PIN_MOVING = sd.Color.FromArgb(255, 235, 140, 40)
C_PIN_DONE = sd.Color.FromArgb(255, 130, 140, 150)
C_DECK = sd.Color.FromArgb(255, 90, 150, 200)
C_ROBOT = sd.Color.FromArgb(255, 40, 44, 52)
C_ROLLER = sd.Color.FromArgb(255, 200, 60, 50)
C_DONE = sd.Color.FromArgb(255, 200, 60, 50)
C_TODO = sd.Color.FromArgb(255, 190, 195, 200)
C_HUD = sd.Color.FromArgb(255, 30, 30, 30)


# ── 이전 재생 정리 ──────────────────────────────────────
# **먼저 끈다.** 이 컴포넌트는 입력이 바뀔 때마다 다시 도는데, 정리하지 않으면
# 컨듀잇과 타이머가 계속 쌓여 화면에 여러 프레임이 겹쳐 그려지고 CPU를 먹는다.

def teardown():
    old = sc.sticky.pop(KEY, None)
    if old is None:
        return False
    try:
        old["conduit"].Enabled = False
    except Exception:
        pass
    try:
        old["timer"].Stop()
        old["timer"].Dispose()
    except Exception:
        pass
    # 프리뷰를 원래대로 — **끈 것을 반드시 되돌린다.** 여기서 빠뜨리면
    # 재생을 멈춘 뒤에도 캔버스가 아무것도 안 보이는 상태로 남는다.
    for obj, was in old.get("hidden_prev", []):
        try:
            obj.Hidden = was
        except Exception:
            pass
    if old.get("hidden_prev"):
        try:
            ghenv.Component.OnPingDocument().ExpirePreview(True)
        except Exception:
            pass
    return True


def hide_previews(others):
    """재생 중 GH 프리뷰를 끈다. (객체, 원래값) 목록을 돌려준다.

    **자기 프리뷰는 항상 끈다.** 이 컴포넌트의 pins·deck 출력은 t 시점의
    형상인데, 재생 중에는 t 가 고정이라 **틀린 그림이 화면에 남는다**(실측:
    t=0 으로 재생을 시작하니 바닥에 납작한 격자가 그려져 있었다).
    움직이는 그림은 컨듀잇이 그리므로 출력 프리뷰는 방해만 된다.

    others=True 면 다른 컴포넌트도 끈다. 핀 Brep·강선·법선 화살표·롤러선이
    화면을 덮으면 재생이 보이지 않는다 — 이것도 실측이다.

    끄는 것이 아니라 **끈 것을 기억해 두는 것**이 요점이다. teardown 이 되돌린다.
    """
    prev = []
    me = ghenv.Component
    try:
        ghdoc = me.OnPingDocument()
    except Exception:
        ghdoc = None

    targets_ = [me]
    if others and ghdoc is not None:
        targets_ = [o for o in ghdoc.Objects]

    for o in targets_:
        try:
            was = o.Hidden          # IGH_PreviewObject 만 갖고 있다
        except Exception:
            continue
        prev.append((o, was))
        try:
            o.Hidden = True
        except Exception:
            pass

    if ghdoc is not None:
        try:
            ghdoc.ExpirePreview(True)
        except Exception:
            pass
    return prev


had_previous = teardown()


# ── 입력 정리 ───────────────────────────────────────────

pin_pts = [p for p in (pin_tops or []) if p is not None]
pose_flat = [float(v) for v in (poses or [])]
tgts = [p for p in (targets or []) if p is not None]
kinds = [str(k) for k in (move_kind or [])]

pin_bases = []
pin_h_end = []
if pin_pts:
    for p in pin_pts:
        u, v = 0.0, 0.0
        ok, u, v = base_plane.ClosestParameter(p)
        b = base_plane.PointAt(u, v)
        pin_bases.append(b)
        # 높이는 베이스면 법선 방향 거리 — 평면이 기울어도 맞는다
        pin_h_end.append((p - b) * base_plane.ZAxis)

pin_h_start = [float(pin_home)] * len(pin_bases)


def derive_nx(pts):
    """행 길이(nx)를 점 순서에서 유도한다.

    그리드는 row-major(idx = j*nx + i)이고 한 행 안에서는 간격이 일정하다.
    행이 바뀌는 지점에서 연속 두 점의 거리가 크게 뛴다 — 그 지점이 nx다.
    이렇게 하면 nx 를 입력으로 받지 않아도 되고, 잘못 연결될 여지가 없다.
    """
    if len(pts) < 3:
        return len(pts)
    d0 = pts[0].DistanceTo(pts[1])
    if d0 <= 0:
        return len(pts)
    for i in range(1, len(pts) - 1):
        if pts[i].DistanceTo(pts[i + 1]) > d0 * 1.5:
            return i + 1
    return len(pts)


NX = derive_nx(pin_bases) if pin_bases else 0
NY = (len(pin_bases) // NX) if NX else 0


# ── 타임라인 ────────────────────────────────────────────

pose_list = pb.poses_from_flat(pose_flat) if pose_flat else []
tgt_pts = [p.Origin for p in tgts]

# 로봇 포즈와 타겟 수가 다르면 AMv1 Robot 이 step>1 로 돌았다는 뜻이다.
# 그 경우 거리 기반 이송 시간을 타겟에 맞출 수 없다 — 관절 시간만 쓴다.
step_mismatch = bool(pose_list) and bool(tgt_pts) and len(pose_list) != len(tgt_pts)
if step_mismatch:
    tgt_pts = []
    kinds = []

# robot_base 를 주지 않았으면 AMv1 Robot 과 **같은** 기본값을 써야 한다.
# 각자 갖고 있으면 로봇이 계산된 위치와 다른 곳에 그려진다.
base_auto = robot_base is None
if base_auto:
    robot_base = rb.default_base_plane(tgts) if tgts else rg.Plane.WorldXY

timeline = pb.build(
    pin_bases=pin_bases, pin_h_start=pin_h_start, pin_h_end=pin_h_end,
    pin_speed=pin_speed,
    poses=pose_list, kinds=kinds, points=tgt_pts,
    feed=feed, joint_scale=joint_scale, dwell=dwell)

duration = timeline.duration


# ── 프레임 하나를 형상으로 ─────────────────────────────

def build_frame(t):
    """t초 시점의 표시 형상. 재생과 스크럽이 같은 코드를 쓴다."""
    s = timeline.sample(t)

    pin_lines = []
    moving = []
    hs = s["heights"]
    if hs:
        for b, h, h1 in zip(pin_bases, hs, pin_h_end):
            top = b + base_plane.ZAxis * h
            pin_lines.append(rg.Line(b, top))
            moving.append(abs(h - h1) > 1e-6)

    deck = []
    if hs and NX >= 2 and NY >= 1:
        tops = [b + base_plane.ZAxis * h for b, h in zip(pin_bases, hs)]
        for j in range(NY):
            row = tops[j * NX:(j + 1) * NX]
            if len(row) >= 2:
                deck.append(rg.Polyline(row))
        for i in range(NX):
            col = [tops[j * NX + i] for j in range(NY)]
            if len(col) >= 2:
                deck.append(rg.Polyline(col))

    lks = []
    tcp_pl = None
    roller_crv = None
    pose = s["pose"]
    if pose is not None:
        lks = rb.link_lines_mm(pose, base_plane=robot_base)
        tcp_pl = rb.tcp_plane_mm(pose)
        tcp_pl.Transform(rg.Transform.PlaneToPlane(rg.Plane.WorldXY, robot_base))
        # 롤러는 축(TCP X)에 직각인 원이다
        roller_crv = rg.Circle(
            rg.Plane(tcp_pl.Origin, tcp_pl.XAxis), roller_d / 2.0)

    return s, pin_lines, moving, deck, lks, tcp_pl, roller_crv


# ── 컨듀잇 ──────────────────────────────────────────────

class PlayConduit(rd.DisplayConduit):
    """벽시계 시간으로 프레임을 그린다. 상태는 state dict 에 둔다."""

    def __init__(self, state):
        self.state = state

    def CalculateBoundingBox(self, e):
        # 이걸 빼면 그린 것이 뷰 클리핑에 걸려 잘린다 — 카메라가 우리 형상을
        # 모르기 때문이다. ZoomExtents 도 반응하지 않는다.
        bb = self.state.get("bbox")
        if bb is not None and bb.IsValid:
            e.IncludeBoundingBox(bb)

    def PostDrawObjects(self, e):
        st = self.state
        sw = st["sw"]
        t0 = sw.Elapsed.TotalMilliseconds

        s, pin_lines, moving, deck, lks, tcp_pl, roller_crv = st["frame"]
        d = e.Display

        for ln, mv in zip(pin_lines, moving):
            d.DrawLine(ln, C_PIN_MOVING if mv else C_PIN_DONE, 3)
        for pl in deck:
            d.DrawPolyline(pl, C_DECK, 1)

        if st["show_path"] and st["tgt_pts"]:
            seg = s["seg"]
            if s["phase"] in ("robot", "done") and seg >= 1:
                d.DrawPolyline(st["tgt_pts"][:seg + 1], C_DONE, 2)
            if seg + 1 < len(st["tgt_pts"]):
                d.DrawPolyline(st["tgt_pts"][seg:], C_TODO, 1)

        for ln in lks:
            d.DrawLine(ln, C_ROBOT, 5)
        if roller_crv is not None:
            d.DrawCircle(roller_crv, C_ROLLER, 3)

        # HUD — 실제 시간으로 도는지 눈으로 확인할 수 있어야 한다
        txt = [
            "{:6.2f} / {:.1f} s   x{:.0f}   {}".format(
                s["t"], st["duration"], st["time_scale"], s["phase"]),
            "{:3.0f}%   {:.1f} fps   draw {:.2f} ms x{:.1f}".format(
                s["progress"] * 100.0, st["fps_measured"],
                st["draw_ms"], st["draws_per_frame"]),
        ]
        for i, line in enumerate(txt):
            d.Draw2dText(line, C_HUD, rg.Point2d(14, 16 + i * 18), False, 14)

        st["draw_ms"] = sw.Elapsed.TotalMilliseconds - t0
        st["draws"] += 1


# ── 재생 시작 / 스크럽 ──────────────────────────────────

frame = build_frame(float(t))
s0, pins, _mv, deck, links, tcp, roller = frame

info_extra = []

if play and duration > 0:
    all_pts = list(pin_bases)
    for b, h in zip(pin_bases, pin_h_end):
        all_pts.append(b + base_plane.ZAxis * h)
    for ln in links:
        all_pts.append(ln.From)
        all_pts.append(ln.To)
    all_pts.extend(tgt_pts)
    bbox = rg.BoundingBox(all_pts) if all_pts else rg.BoundingBox.Unset
    if bbox.IsValid:
        bbox.Inflate(500.0)

    state = {
        "frame": frame,
        "sw": System.Diagnostics.Stopwatch.StartNew(),
        "t0": float(t),
        "duration": duration,
        "time_scale": float(time_scale),
        "loop": bool(loop),
        "show_path": bool(show_path),
        "tgt_pts": tgt_pts,
        "bbox": bbox,
        "draws": 0,
        "draw_ms": 0.0,
        "ticks": 0,
        "fps_measured": 0.0,
        "draws_per_frame": 0.0,
        "last_fps_t": 0.0,
        "last_fps_draws": 0,
        "last_fps_ticks": 0,
    }

    state["hidden_prev"] = hide_previews(bool(solo))

    conduit = PlayConduit(state)
    conduit.Enabled = True

    def on_tick(sender, args):
        st = state
        st["ticks"] += 1
        secs = st["sw"].Elapsed.TotalSeconds
        t_now = st["t0"] + secs * st["time_scale"]

        if t_now > st["duration"]:
            if st["loop"]:
                st["t0"] = 0.0
                st["sw"].Restart()
                t_now = 0.0
            else:
                t_now = st["duration"]

        st["frame"] = build_frame(t_now)

        # 실측 프레임률 — 0.5초마다 갱신.
        # **프레임은 틱이고, 그리기는 뷰포트마다 한 번씩 더 일어난다.**
        # draws 로 fps 를 계산하면 열린 뷰포트 수만큼 부풀어 보인다
        # (실측: 21.2 fps 인데 draws 기준으로는 36.7 로 나왔다).
        dt_fps = secs - st["last_fps_t"]
        if dt_fps >= 0.5:
            dticks = st["ticks"] - st["last_fps_ticks"]
            ddraws = st["draws"] - st["last_fps_draws"]
            st["fps_measured"] = dticks / dt_fps
            st["draws_per_frame"] = (float(ddraws) / dticks) if dticks else 0.0
            st["last_fps_t"] = secs
            st["last_fps_draws"] = st["draws"]
            st["last_fps_ticks"] = st["ticks"]

        doc = Rhino.RhinoDoc.ActiveDoc
        if doc is not None:
            doc.Views.Redraw()

    timer = wf.Timer()
    timer.Interval = int(max(10, round(1000.0 / float(fps))))
    timer.Tick += on_tick
    timer.Start()

    # handler 를 함께 담아 둔다 — 델리게이트만 남기면 GC 대상이 된다
    sc.sticky[KEY] = {"conduit": conduit, "timer": timer,
                      "state": state, "handler": on_tick,
                      "hidden_prev": state["hidden_prev"]}

    # Windows 타이머는 시스템 틱(15.625 ms) 배수로 스냅된다. 40 ms 를 요청하면
    # 실제로는 46.9 ms 로 돌아 21.3 Hz 가 된다(실측 21.2). 그래서 요청값과
    # 실효값을 같이 적는다 — HUD 의 fps 가 낮게 보이는 것이 버그가 아니다.
    snapped = 15.625 * max(1.0, round(timer.Interval / 15.625))
    info_extra = [
        "",
        "재생 중 — 뷰포트에 직접 그린다 (GH 프리뷰가 아니다)",
        "  타이머 {} ms 요청 -> 실효 {:.1f} ms ({:.1f} fps)".format(
            timer.Interval, snapped, 1000.0 / snapped),
        "             <- Windows 타이머는 15.625 ms 배수로 스냅된다",
        "  배속 x{:.1f}  반복 {}  프리뷰 {}개 끔".format(
            float(time_scale), "예" if loop else "아니오",
            len(state["hidden_prev"])),
        "  play 를 끄면 멈추고 t 초 시점 형상이 출력으로 나온다",
        "",
        "재생 시각은 매 틱마다 스톱워치에서 다시 계산한다 — 프레임을 놓쳐도",
        "누적 오차가 생기지 않는다 (실측: 6.1초 구간에서 오차 0.5%)",
    ]
else:
    info_extra = [
        "",
        "정지 — t={:.2f} s 시점 형상을 출력으로 낸다 (슬라이더로 스크럽)".format(
            float(t)),
        "  play 를 켜면 벽시계 시간으로 재생한다",
    ]
    if had_previous:
        info_extra.append("  (직전 재생을 정리했다)")


# ── 리포트 ──────────────────────────────────────────────

lines = [
    "AMv1 Play",
    "=" * 44,
]

if not pin_bases and not pose_list:
    lines.append("입력이 없다 — Inspect 의 pin_tops, Robot 의 poses 를 연결하세요.")
else:
    if pin_bases:
        lines.append("핀:          {}개  격자 {}x{}  출발 {:.0f} mm".format(
            len(pin_bases), NX, NY, float(pin_home)))
        lines.append("             <- 격자 크기는 점 순서에서 유도했다")
    if pose_list:
        lines.append("로봇 포즈:   {}개".format(len(pose_list)))
        lines.append("베이스:      {}  원점 ({:.0f}, {:.0f}, {:.0f})".format(
            "자동" if base_auto else "입력",
            robot_base.Origin.X, robot_base.Origin.Y, robot_base.Origin.Z))
        lines.append("             <- AMv1 Robot 과 같은 값이어야 한다")
    lines.append("")
    lines.append(pb.report(timeline))
    lines.append("")
    lines.append("현재:        {:.2f} s  {}  {:.0f}%".format(
        s0["t"], s0["phase"], s0["progress"] * 100.0))

if step_mismatch:
    lines += [
        "",
        "** 포즈 {}개 != 타겟 {}개 — AMv1 Robot 이 step>1 로 돌았다.".format(
            len(pose_list), len(tgts)),
        "   어느 포즈가 어느 타겟인지 알 수 없으므로 이송 시간을 못 쓰고",
        "   관절 시간만 썼다. 시간이 실제보다 짧게 나온다.",
        "   step=1 로 다시 계산할 것.",
    ]

lines += info_extra
info = "\n".join(lines)

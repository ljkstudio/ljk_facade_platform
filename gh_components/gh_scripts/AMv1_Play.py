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
# **컨듀잇은 항상 켜 둔다. 타이머만 재생 시에 돈다.**
#   play=False → 일시정지. t 슬라이더로 그 시점의 형상을 그린다
#   play=True  → 타이머가 벽시계 시간으로 프레임을 넘긴다
#
# 처음에는 정지 상태를 GH 출력 프리뷰에 맡겼는데, **GH 프리뷰가 메시 와이어를
# 전부 그려서** 12만 면이 붉은 철망으로 보였다(실측). 컨듀잇은 셰이딩된 몸체를
# 제 색으로 그린다. 두 모드가 같은 그림을 쓰는 편이 보기에도 낫고 코드도 하나다.
#
# 그래서 **자기 GH 프리뷰는 항상 끈다** — 켜 두면 컨듀잇 그림 위에 붉은 철망이
# 겹친다. 반면 `solo`(다른 컴포넌트 프리뷰 끄기)는 **재생 중에만** 적용한다.
# 정지 상태에서까지 남의 프리뷰를 꺼 두면 작업을 방해한다.
#
# **고아 컨듀잇 방지:** 컴포넌트를 지우면 솔루션이 돌지 않아 teardown 이 불리지
# 않는다. 그래서 컨듀잇이 매 프레임 자기 컴포넌트가 아직 문서에 있는지 확인하고,
# 없으면 스스로 꺼진다. 없으면 지운 뒤에도 뷰포트에 로봇이 남는다.
#
# Inputs:
#   platform_path  str      repo root (필수)
#   pin_tops       Point3d* AMv1 Inspect 의 pin_tops (list)
#   base_plane     Plane    몰드 베이스. 비우면 WorldXY
#   pin_home       float    핀 출발 높이, 없으면 0
#   pin_speed      float    액추에이터 속도 mm/s, 없으면 50   <- 가정치
#   poses          float*   AMv1 Robot 의 poses (6개씩 평탄, list)
#   reach_err      float*   AMv1 Robot 의 reach_err — **연결할 것.**
#                           없으면 못 닿는 위치도 되는 것처럼 보인다
#   targets        Plane*   AMv1 RollerPath 의 targets (list)
#   move_kind      str*     같은 순서의 구간 종류 (list)
#   robot_base     Plane    로봇 베이스 평면. 비우면 base_pt/base_dir 를 본다
#   base_pt        Point    베이스 원점 (Rhino 에서 점을 찍어 물린다)
#   base_dir       Curve    로봇이 바라보는 방향 (Rhino 에서 선을 그어 물린다)
#                           **AMv1 Robot 에 같은 것을 물려야 그림이 맞는다**
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
#   show_body      bool     실물 메시로 그린다, 없으면 True
#   parts_file     str      irb6700_parts.3dm 경로. 비우면 저장소 기본 위치
#   mold_srf       Brep     간섭 검사용 성형면 (선택). 비우면 핀 상단 + stack
#   stack          float    핀 상단에서 성형면까지 (mm), 없으면 28
#   check_hit      bool     팔 간섭 스크리닝 실행, 없으면 False (무겁다)
#   hit_margin     float    간섭 여유 (mm), 없으면 30
#   hit_step       int      N개마다 하나만 검사, 없으면 1
#
# Outputs:
#   pins       t 시점의 핀 (선)
#   deck       t 시점의 핀 상단 격자 (폴리라인)
#   links      t 시점의 로봇 링크 (스틱 피겨)
#   body       t 시점의 로봇 실물 메시 (정지 상태에서만)
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
import robot_body as rbb
import playback as pb
import collision as col


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
_default("show_body", True)
_default("parts_file", "")
_default("check_hit", False)
_default("hit_margin", col.DEFAULT_MARGIN)
_default("hit_step", 1, positive=True)
_default("stack", 28.0)

if base_plane is None:
    base_plane = rg.Plane.WorldXY

if not parts_file:
    parts_file = os.path.join(platform_path, "adaptive_mold", "grasshopper",
                              "irb6700_parts.3dm")


# ── 실물 형상 로드 (캐시) ───────────────────────────────
# 4 MB / 12만 면이라 솔루션마다 다시 읽으면 눈에 띄게 느리다.
# 파일 수정시각까지 키에 넣어, 파일을 다시 만들면 알아서 갱신된다.

PARTS_KEY = "AMv1_Play_parts"
PARTS = {}
parts_note = ""

if show_body:
    if not os.path.isfile(parts_file):
        parts_note = "파트 파일이 없다 — 스틱 피겨로 그린다"
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
        missing = [n for n in rbb.PART_NAMES if n not in PARTS]
        if missing:
            parts_note += " (빠진 파트: {})".format(", ".join(missing))
else:
    parts_note = "show_body=False — 스틱 피겨"


C_PIN_MOVING = sd.Color.FromArgb(255, 235, 140, 40)
C_PIN_DONE = sd.Color.FromArgb(255, 130, 140, 150)
C_DECK = sd.Color.FromArgb(255, 90, 150, 200)
C_ROBOT = sd.Color.FromArgb(255, 40, 44, 52)
C_ROLLER = sd.Color.FromArgb(255, 200, 60, 50)
C_DONE = sd.Color.FromArgb(255, 200, 60, 50)
C_TODO = sd.Color.FromArgb(255, 190, 195, 200)
C_HUD = sd.Color.FromArgb(255, 30, 30, 30)
# ABB 그래파이트 화이트 — URDF material rgba(0.9255, 0.9255, 0.9059)
C_BODY = sd.Color.FromArgb(255, 236, 236, 231)
# 못 닿는 구간 — 로봇을 다른 색으로 칠한다. 자세만 보고는 구별이 안 된다
C_BODY_BAD = sd.Color.FromArgb(255, 235, 150, 140)
C_BAD = sd.Color.FromArgb(255, 220, 20, 20)
# 팔 간섭 — 도달 실패와 다른 색이어야 한다. 원인이 다르면 손볼 곳도 다르다
C_BODY_HIT = sd.Color.FromArgb(255, 250, 180, 60)
C_HIT = sd.Color.FromArgb(255, 230, 130, 0)


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
    tm = old.get("timer")
    if tm is not None:
        try:
            tm.Stop()
            tm.Dispose()
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


teardown()


# ── 입력 정리 ───────────────────────────────────────────

pin_pts = [p for p in (pin_tops or []) if p is not None]
pose_flat = [float(v) for v in (poses or [])]
tgts = [p for p in (targets or []) if p is not None]
kinds = [str(k) for k in (move_kind or [])]
errs = [float(e) for e in (globals().get("reach_err") or [])]

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

# 베이스 결정은 robot.py 한 곳에서 한다 — AMv1 Robot 과 **같은 함수**여야 한다.
# 각자 판단하면 한쪽만 고쳐도 오류가 나지 않고 로봇이 계산된 위치와 다른 곳에
# 그려진다. 그래서 두 컴포넌트에 같은 점·선을 물려야 한다.
robot_base, base_src = rb.resolve_base_plane(
    robot_base=robot_base,
    base_pt=globals().get("base_pt"),
    base_dir=globals().get("base_dir"),
    targets=tgts)

# 오차 개수가 포즈 개수와 다르면 어느 타겟의 오차인지 알 수 없다 — 버린다.
# 억지로 맞추면 엉뚱한 구간을 실패로 칠하게 되고, 그게 더 나쁘다.
err_mismatch = bool(errs) and bool(pose_list) and len(errs) != len(pose_list)
if err_mismatch:
    errs = []

timeline = pb.build(
    pin_bases=pin_bases, pin_h_start=pin_h_start, pin_h_end=pin_h_end,
    pin_speed=pin_speed,
    poses=pose_list, kinds=kinds, points=tgt_pts,
    feed=feed, joint_scale=joint_scale, dwell=dwell, errors=errs)

duration = timeline.duration

fail_idx = timeline.robot.failed_indices() if timeline.robot else []
err_max = max(errs) if errs else 0.0

# 베이스가 몰드 영역과 겹치면 그 위치는 물리적으로 불가능하다 — IK 는 이걸 모른다
base_ov = rb.base_overlap(robot_base, pin_bases) if pin_bases else 0.0
base_circle = rg.Circle(
    rg.Plane(robot_base.Origin, rg.Vector3d.ZAxis), rb.BASE_RADIUS_MM)


# ── 팔 간섭 스크리닝 ───────────────────────────────────
# **검사가 아니라 스크리닝이다** — 표본으로 본다(collision.py 주석 참조).
# 무거우므로 check_hit 토글로 잠근다. 결과는 포즈별 침투 깊이 목록이다.

hitfield = None
hit_pens = []
hit_sum = None
hit_pts = []

if check_hit and PARTS and pose_list and pin_pts:
    # 몰드 면 = 핀 상단 + 스택 두께. mold_srf 를 물리면 그쪽이 우선이다.
    srf = globals().get("mold_srf")
    if srf is not None:
        hitfield = col.Heightfield.from_surface(srf, nx=40, ny=40)
    if hitfield is None and NX >= 2 and NY >= 2:
        tops = [b + base_plane.ZAxis * h
                for b, h in zip(pin_bases, pin_h_end)]
        hitfield = col.Heightfield.from_grid_points(
            tops, NX, NY, offset=float(stack))

    if hitfield is not None:
        samples = col.sample_points(PARTS)
        hit_pens, hit_whos = col.scan_poses(
            pose_list, samples, hitfield, base_plane=robot_base,
            margin=float(hit_margin), step=int(hit_step))
        hit_sum = col.summarize(hit_pens, hit_whos, step=int(hit_step),
                                total=len(pose_list),
                                margin=float(hit_margin))
        hit_pts = [tgt_pts[i] for i in hit_sum["hit_indices"]
                   if i < len(tgt_pts)]


def hit_at(seg):
    """구간 seg 의 침투 깊이. step 을 쓰면 가장 가까운 표본을 본다."""
    if not hit_pens:
        return None
    k = int(seg) // max(1, int(hit_step))
    if k >= len(hit_pens):
        k = len(hit_pens) - 1
    return hit_pens[k]


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
    part_xf = {}
    pose = s["pose"]
    if pose is not None:
        lks = rb.link_lines_mm(pose, base_plane=robot_base)
        tcp_pl = rb.tcp_plane_mm(pose)
        tcp_pl.Transform(rg.Transform.PlaneToPlane(rg.Plane.WorldXY, robot_base))
        # 롤러는 축(TCP X)에 직각인 원이다
        roller_crv = rg.Circle(
            rg.Plane(tcp_pl.Origin, tcp_pl.XAxis), roller_d / 2.0)
        if PARTS:
            # 변환만 만든다 — **메시를 복제하지 않는다.** 프레임마다 12만 면을
            # 복제하면 재생이 늘어진다. 그리기는 PushModelTransform 이 한다.
            part_xf = rbb.part_transforms(pose, base_plane=robot_base)

    return {"s": s, "pins": pin_lines, "moving": moving, "deck": deck,
            "links": lks, "tcp": tcp_pl, "roller": roller_crv,
            "part_xf": part_xf, "hit": hit_at(s["seg"])}


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

        # 컴포넌트가 지워졌으면 스스로 꺼진다 — 지우면 솔루션이 돌지 않아
        # teardown 이 불리지 않고, 그대로 두면 뷰포트에 로봇이 남는다.
        try:
            if st["comp"].OnPingDocument() is None:
                self.Enabled = False
                return
        except Exception:
            self.Enabled = False
            return

        sw = st["sw"]
        t0 = sw.Elapsed.TotalMilliseconds

        f = st["frame"]
        s = f["s"]
        d = e.Display

        for ln, mv in zip(f["pins"], f["moving"]):
            d.DrawLine(ln, C_PIN_MOVING if mv else C_PIN_DONE, 3)
        for pl in f["deck"]:
            d.DrawPolyline(pl, C_DECK, 1)

        if st["show_path"] and st["tgt_pts"]:
            seg = s["seg"]
            if s["phase"] in ("robot", "done") and seg >= 1:
                d.DrawPolyline(st["tgt_pts"][:seg + 1], C_DONE, 2)
            if seg + 1 < len(st["tgt_pts"]):
                d.DrawPolyline(st["tgt_pts"][seg:], C_TODO, 1)

        # ── 도달 실패 표시 ──────────────────────────────
        # **못 닿는 자세도 그려진다.** IK 가 관절 한계에서 잘라내므로 팔은
        # 그럴듯한 자세로 서 있고, 롤러만 판재에서 떠 있다. 그 차이는 눈으로
        # 구별이 안 되므로 명시적으로 그린다.
        bad = not s["reachable"]
        hit = (f["hit"] is not None) and (f["hit"] > 0.0)
        if st["fail_pts"]:
            d.DrawPoints(st["fail_pts"], rd.PointStyle.X, 4, C_BAD)
        if st["hit_pts"]:
            d.DrawPoints(st["hit_pts"], rd.PointStyle.Square, 5, C_HIT)

        # 베이스 자리. 겹치면 붉게 — IK 가 통과해 버리는 종류의 불가능이다
        ov = st["base_ov"]
        d.DrawCircle(st["base_circle"], C_BAD if ov > 0 else C_PIN_DONE,
                     4 if ov > 0 else 2)
        if bad and f["tcp"] is not None and st["tgt_pts"]:
            seg = min(s["seg"], len(st["tgt_pts"]) - 1)
            # TCP 와 가려던 자리를 잇는다 — 이 선의 길이가 곧 오차다
            d.DrawLine(rg.Line(f["tcp"].Origin, st["tgt_pts"][seg]), C_BAD, 3)
            d.DrawPoint(st["tgt_pts"][seg], rd.PointStyle.RoundControlPoint,
                        6, C_BAD)

        # ── 실물 형상 ────────────────────────────────────
        # **메시를 옮기지 않고 좌표계를 옮긴다.** Push/Pop 이면 원본을 그대로
        # 그릴 수 있어 프레임마다 12만 면을 복제하지 않는다.
        parts = st["parts"]
        drew_body = False
        if parts and f["part_xf"]:
            mat = st["material"]
            if hit:
                mat = st["material_hit"]
            elif bad:
                mat = st["material_bad"]
            for name, mesh in parts.items():
                xf = f["part_xf"].get(name)
                if xf is None:
                    continue
                d.PushModelTransform(xf)
                try:
                    d.DrawMeshShaded(mesh, mat)
                finally:
                    d.PopModelTransform()
            drew_body = True

        # 스틱 피겨는 실물이 없을 때만 — 겹치면 실물 안쪽에 선이 비쳐 지저분하다
        if not drew_body:
            for ln in f["links"]:
                d.DrawLine(ln, C_BAD if bad else C_ROBOT, 5)

        if f["roller"] is not None:
            d.DrawCircle(f["roller"], C_ROLLER, 3)

        # HUD — 실제 시간으로 도는지 눈으로 확인할 수 있어야 한다
        if st["running"]:
            head = "{:6.2f} / {:.1f} s   x{:.0f}   {}".format(
                s["t"], st["duration"], st["time_scale"], s["phase"])
            tail = "{:3.0f}%   {:.1f} fps   draw {:.2f} ms x{:.1f}".format(
                s["progress"] * 100.0, st["fps_measured"],
                st["draw_ms"], st["draws_per_frame"])
        else:
            head = "||  {:6.2f} / {:.1f} s   {}".format(
                s["t"], st["duration"], s["phase"])
            tail = "{:3.0f}%   play 를 켜면 실제 속도로 돈다".format(
                s["progress"] * 100.0)
        txt = [head, tail]
        for i, line in enumerate(txt):
            d.Draw2dText(line, C_HUD, rg.Point2d(14, 16 + i * 18), False, 14)

        # 도달 판정은 눈에 띄어야 한다 — 이걸 안 적으면 못 가는 위치도
        # 되는 것처럼 보인다
        y = 16 + len(txt) * 18
        if st["n_err"] == 0:
            d.Draw2dText("도달 판정 없음 — reach_err 를 연결하세요",
                         C_BAD, rg.Point2d(14, y), False, 14)
        elif st["n_fail"]:
            d.Draw2dText(
                "도달 실패 {} / {} ({:.1f}%)   최대 {:.0f} mm{}".format(
                    st["n_fail"], st["n_err"],
                    100.0 * st["n_fail"] / st["n_err"], st["err_max"],
                    "   << 지금 이 구간 {:.0f} mm".format(s["err"])
                    if bad else ""),
                C_BAD, rg.Point2d(14, y), False, 14)
        else:
            d.Draw2dText("도달 OK  최대 {:.1f} mm".format(st["err_max"]),
                         C_HUD, rg.Point2d(14, y), False, 14)

        y += 18
        if st["base_ov"] > 0:
            d.Draw2dText(
                "베이스가 몰드 영역과 {:.0f} mm 겹친다 — 세울 수 없는 자리다".format(
                    st["base_ov"]),
                C_BAD, rg.Point2d(14, y), False, 14)
            y += 18

        hs = st["hit_sum"]
        if hs is None:
            d.Draw2dText("팔 간섭 미검사 (check_hit 를 켜세요)",
                         C_TODO, rg.Point2d(14, y), False, 14)
        elif hs["hits"]:
            d.Draw2dText(
                "팔 간섭 {} / {} 포즈   최대 {:.0f} mm   {}{}".format(
                    hs["hits"], hs["checked"], hs["worst"],
                    ", ".join("{} {}".format(k, v)
                              for k, v in sorted(hs["per_part"].items())),
                    "   << 지금 {:.0f} mm".format(f["hit"]) if hit else ""),
                C_HIT, rg.Point2d(14, y), False, 14)
        else:
            d.Draw2dText(
                "팔 간섭 없음 ({}포즈 표본)   최소 여유 {}".format(
                    hs["checked"],
                    "{:.0f} mm".format(hs["min_clear"])
                    if hs["min_clear"] is not None else "판정 불가"),
                C_HUD, rg.Point2d(14, y), False, 14)

        st["draw_ms"] = sw.Elapsed.TotalMilliseconds - t0
        st["draws"] += 1


# ── 표시 (항상) + 재생 (play 일 때) ────────────────────

frame = build_frame(float(t))
s0 = frame["s"]
pins = frame["pins"]
deck = frame["deck"]
links = frame["links"]
tcp = frame["tcp"]
roller = frame["roller"]

# 실물 메시 출력. **프리뷰로 보이는 것이 아니다** — 자기 프리뷰는 껐고 화면은
# 컨듀잇이 그린다. 이 출력은 다른 컴포넌트로 넘겨 쓸 때를 위한 것이다.
body = []
if PARTS and frame["part_xf"]:
    body = [m for _n, m in rbb.posed_meshes(
        PARTS, s0["pose"], base_plane=robot_base)]

running = bool(play) and duration > 0

all_pts = list(pin_bases)
for b, h in zip(pin_bases, pin_h_end):
    all_pts.append(b + base_plane.ZAxis * h)
for ln in links:
    all_pts.append(ln.From)
    all_pts.append(ln.To)
all_pts.extend(tgt_pts)
# 실물 형상은 링크 선보다 크다 — 베이스 반경과 팔 두께만큼 더 잡는다
all_pts.append(robot_base.Origin)
bbox = rg.BoundingBox(all_pts) if all_pts else rg.BoundingBox.Unset
if bbox.IsValid:
    bbox.Inflate(1200.0 if PARTS else 500.0)

state = {
    "frame": frame,
    "comp": ghenv.Component,
    "parts": PARTS,
    "material": rd.DisplayMaterial(C_BODY),
    "material_bad": rd.DisplayMaterial(C_BODY_BAD),
    "n_err": len(errs),
    "n_fail": len(fail_idx),
    "err_max": err_max,
    "base_ov": base_ov,
    "base_circle": base_circle,
    "hit_sum": hit_sum,
    "hit_pts": hit_pts,
    "hit_margin": float(hit_margin),
    "material_hit": rd.DisplayMaterial(C_BODY_HIT),
    # 실패 타겟 위치 — 못 가는 구간이 경로 어디인지 한눈에 보이게
    "fail_pts": [tgt_pts[i] for i in fail_idx if i < len(tgt_pts)],
    "sw": System.Diagnostics.Stopwatch.StartNew(),
    "t0": float(t),
    "duration": duration,
    "time_scale": float(time_scale),
    "loop": bool(loop),
    "running": running,
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

# 자기 프리뷰는 항상 끈다(컨듀잇 그림 위에 붉은 철망이 겹친다).
# 남의 프리뷰는 재생 중에만 끈다 — 정지 상태에서까지 꺼 두면 작업을 방해한다.
state["hidden_prev"] = hide_previews(bool(solo) and running)

conduit = PlayConduit(state)
conduit.Enabled = True

timer = None
info_extra = []

if running:

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
        "  배속 x{:.1f}  반복 {}  남의 프리뷰 {}개 끔".format(
            float(time_scale), "예" if loop else "아니오",
            max(0, len(state["hidden_prev"]) - 1)),
        "  play 를 끄면 그 자리에 멈춘 그림이 남는다",
        "",
        "재생 시각은 매 틱마다 스톱워치에서 다시 계산한다 — 프레임을 놓쳐도",
        "누적 오차가 생기지 않는다 (실측: 6.1초 구간에서 오차 0.5%)",
    ]
else:
    info_extra = [
        "",
        "일시정지 — t={:.2f} s 시점을 뷰포트에 그린다 (슬라이더로 스크럽)".format(
            float(t)),
        "  컨듀잇은 켜져 있다. GH 프리뷰가 아니라 이쪽이 그린다 —",
        "  GH 프리뷰는 메시 와이어를 다 그려서 12만 면이 철망으로 보인다",
        "  play 를 켜면 벽시계 시간으로 돈다",
    ]

# handler·conduit·timer 를 함께 담아 둔다 — 델리게이트만 남기면 GC 대상이 된다
sc.sticky[KEY] = {"conduit": conduit, "timer": timer, "state": state,
                  "handler": (on_tick if running else None),
                  "hidden_prev": state["hidden_prev"]}


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
        lines.append("베이스:      {}".format(base_src))
        lines.append("             원점 ({:.0f}, {:.0f}, {:.0f})  방향 ({:.2f}, {:.2f})".format(
            robot_base.Origin.X, robot_base.Origin.Y, robot_base.Origin.Z,
            robot_base.XAxis.X, robot_base.XAxis.Y))
        lines.append("             <- AMv1 Robot 과 같은 입력이어야 한다")
        if base_ov > 0:
            lines.append("** 베이스가 몰드 영역과 {:.0f} mm 겹친다 — 세울 수 없다.".format(
                base_ov))
            lines.append("   IK 는 간섭을 모르므로 팔이 몰드를 통과해 닿는 것을")
            lines.append("   '도달 성공'으로 센다. 베이스를 몰드 밖으로 옮길 것.")
        else:
            lines.append("             몰드 영역과 {:.0f} mm 여유".format(-base_ov))

    if hit_sum is not None:
        lines.append("")
        lines.append("팔 간섭 스크리닝 ({}개 중 {}개 포즈, 여유 {:.0f} mm)".format(
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
            lines.append("  <- 팔이 몰드 면 아래로 들어간다. 베이스를 옮기거나")
            lines.append("     경로 순서·접근 높이를 바꿔야 한다")
        else:
            lines.append("  걸림 없음")
        lines.append("  ** 검사가 아니라 스크리닝이다. 표본으로 보므로 가느다란")
        lines.append("     돌출부는 빠져나갈 수 있다. 자기 간섭·프레임·주변")
        lines.append("     설비는 보지 않는다.")
        if hit_sum["step"] > 1:
            lines.append("  ** step={} 이라 사이 포즈는 보지 않았다.".format(
                hit_sum["step"]))
    elif check_hit:
        lines.append("")
        lines.append("팔 간섭: 높이장을 만들 수 없었다 — 핀 격자나 mold_srf 를 확인할 것")
    else:
        lines.append("")
        lines.append("팔 간섭: 미검사 (check_hit 를 켜면 훑는다)")
        if PARTS:
            lines.append("실물 형상:   파트 {}개  면 {:,}개  ({})".format(
                len(PARTS), rbb.face_count(PARTS), parts_note))
            lines.append("             <- 메시를 복제하지 않고 좌표계를 옮겨 그린다")
        else:
            lines.append("실물 형상:   없음 — {}".format(parts_note))
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

if err_mismatch:
    lines += [
        "",
        "** reach_err {}개 != 포즈 {}개 — 어느 타겟의 오차인지 알 수 없어".format(
            len(globals().get("reach_err") or []), len(pose_list)),
        "   버렸다. 도달 판정을 하지 못한다.",
    ]

lines += info_extra
info = "\n".join(lines)

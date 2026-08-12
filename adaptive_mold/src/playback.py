# -*- coding: utf-8 -*-
"""재생 타임라인 — 핀 상승과 로봇 추종을 실제 시간축에 올린다.

이 모듈은 **시간만** 계산한다. 그리기는 gh_scripts/AMv1_Play.py 가 한다.
그렇게 나눠 두면 시간 모델을 여기서 단위 없이 검증할 수 있다.

──────────────────────────────────────────────────────────
시간 모델 — 왜 cycle_time() 을 그대로 쓰지 않는가
──────────────────────────────────────────────────────────

robot.cycle_time() 은 모든 구간을 **관절 최대 속도**로 계산한다. 그것은
공중 이동에는 맞지만 성형 구간에는 틀리다. 롤러가 판재를 눌러 앉히는
속도는 로봇의 능력이 아니라 **공정이 정한다**(가열 판재의 성형 속도).
관절 최대 속도로 성형하면 실제보다 훨씬 빠른 애니메이션이 나온다.

그래서 구간별로:

    성형(form)  dt = max(거리/feed,  관절시간)
    공중(air)   dt =      관절시간

성형에서도 max 를 취하는 이유: feed 가 아무리 빨라도 로봇이 그 자세 변화를
그 시간에 못 만들면 그 시간에 못 간다. 둘 중 **느린 쪽이 실제 시간**이다.

관절시간은 `|Δθ| / (최대속도 × joint_scale)` 이다. joint_scale 은 프로그램
속도 오버라이드에 해당한다(실장비에서 100%로 돌리는 일은 없다).

**가감속을 무시한다.** 따라서 모든 시간은 하한이다. 실제 장비는 더 걸린다.
정확히 하려면 축별 가속도 한계가 필요하고, 그것은 데이터시트에 없다.

──────────────────────────────────────────────────────────
핀 구간
──────────────────────────────────────────────────────────

핀은 전부 동시에 출발해 각자 자기 목표 높이에서 멈춘다(개별 액추에이터).
그래서 구간 길이는 **가장 많이 움직이는 핀**이 정하고, 짧은 핀은 먼저 서서
기다린다. 전부 같은 시간에 도착하도록 속도를 맞추는 제어(보간 이동)도
가능하지만 실물이 그렇게 도는지 확인되지 않았으므로 가정하지 않는다.
"""

import math

import Rhino.Geometry as rg

import robot as rb


# 액추에이터 속도 (mm/s) — **가정치**. 실제 스펙으로 교체해야 한다.
# 전동 리니어 액추에이터의 일반적인 무부하 속도대에서 잡았다.
DEFAULT_PIN_SPEED = 50.0

# 롤러 이송 속도 (mm/s) — **가정치**. 판재 온도·두께가 정하는 값이다.
DEFAULT_FEED = 50.0

# 프로그램 속도 오버라이드 (0~1). 실장비에서 공중 이동을 최대 속도로
# 돌리는 일은 없다.
DEFAULT_JOINT_SCALE = 0.25


def _pose_from_flat(flat, i):
    """AMv1 Robot 의 평탄 목록(6개씩)에서 i번째 포즈를 뽑는다."""
    base = i * 6
    return dict((n, float(flat[base + k]))
                for k, n in enumerate(rb.JOINT_NAMES))


def poses_from_flat(flat):
    """평탄 목록 전체를 포즈 목록으로."""
    n = len(flat) // 6
    return [_pose_from_flat(flat, i) for i in range(n)]


def joint_time(a, b, joint_scale=DEFAULT_JOINT_SCALE):
    """두 포즈 사이 관절 지배 시간 (초)."""
    if joint_scale <= 0.0:
        joint_scale = DEFAULT_JOINT_SCALE
    worst = 0.0
    for j in rb.JOINT_NAMES:
        d = abs(b[j] - a[j])
        worst = max(worst, d / (rb.JOINT_MAX_SPEED[j] * joint_scale))
    return worst


def lerp_pose(a, b, f):
    """관절 공간 선형 보간.

    관절 시간 모델이 |Δθ|/속도 이므로 보간도 관절 공간에서 해야 일관된다.
    TCP 공간에서 보간하면 표시되는 자세와 계산된 시간이 어긋난다.
    """
    if f <= 0.0:
        return dict(a)
    if f >= 1.0:
        return dict(b)
    return dict((j, a[j] + (b[j] - a[j]) * f) for j in rb.JOINT_NAMES)


class PinPhase(object):
    """핀이 home 에서 목표 높이로 올라가는 구간."""

    def __init__(self, bases, h_start, h_end, speed=DEFAULT_PIN_SPEED):
        if speed <= 0.0:
            speed = DEFAULT_PIN_SPEED
        self.bases = list(bases)            # Point3d — 핀 밑동 (z = 베이스면)
        self.h_start = [float(h) for h in h_start]
        self.h_end = [float(h) for h in h_end]
        self.speed = float(speed)
        self.travel = [abs(b - a) for a, b in zip(self.h_start, self.h_end)]
        self.duration = (max(self.travel) / self.speed) if self.travel else 0.0

    def heights_at(self, t):
        """t초 시점의 핀 높이 목록. 도착한 핀은 그 자리에 선다."""
        out = []
        for h0, h1 in zip(self.h_start, self.h_end):
            d = h1 - h0
            if d == 0.0:
                out.append(h0)
                continue
            moved = self.speed * t
            if moved >= abs(d):
                out.append(h1)
            else:
                out.append(h0 + math.copysign(moved, d))
        return out

    def arrived_at(self, t):
        """t초 시점에 목표에 닿은 핀 수."""
        n = 0
        for tr in self.travel:
            if self.speed * t >= tr:
                n += 1
        return n


class RobotPhase(object):
    """로봇이 타겟 열을 따라가는 구간."""

    def __init__(self, poses, kinds=None, points=None,
                 feed=DEFAULT_FEED, joint_scale=DEFAULT_JOINT_SCALE):
        self.poses = list(poses)
        self.kinds = list(kinds) if kinds else []
        self.points = list(points) if points else []
        self.feed = float(feed) if feed > 0 else DEFAULT_FEED
        self.joint_scale = float(joint_scale)

        self.dt = []              # 구간별 소요 시간
        self.dt_kind = []         # 그 구간을 지배한 것: "feed" | "joint"
        for i in range(len(self.poses) - 1):
            tj = joint_time(self.poses[i], self.poses[i + 1], self.joint_scale)
            kind = self._kind(i + 1)
            if kind == "form" and len(self.points) > i + 1:
                dist = self.points[i].DistanceTo(self.points[i + 1])
                tf = dist / self.feed
                if tf >= tj:
                    self.dt.append(tf)
                    self.dt_kind.append("feed")
                    continue
            self.dt.append(tj)
            self.dt_kind.append("joint")

        # 누적 시간 — 이분 탐색으로 프레임을 찾기 위해
        self.cum = [0.0]
        for d in self.dt:
            self.cum.append(self.cum[-1] + d)
        self.duration = self.cum[-1] if self.cum else 0.0

    def _kind(self, i):
        if i < len(self.kinds):
            return str(self.kinds[i])
        return "form"

    def sample(self, t):
        """(포즈, 구간 인덱스, 구간 내 비율) — 구간 경계를 이분 탐색."""
        if not self.poses:
            return None, 0, 0.0
        if t <= 0.0:
            return dict(self.poses[0]), 0, 0.0
        if t >= self.duration:
            last = len(self.poses) - 1
            return dict(self.poses[last]), max(last - 1, 0), 1.0

        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= t:
                lo = mid
            else:
                hi = mid
        span = self.dt[lo]
        f = ((t - self.cum[lo]) / span) if span > 0 else 0.0
        return lerp_pose(self.poses[lo], self.poses[lo + 1], f), lo, f


class Timeline(object):
    """핀 구간 → 정지(dwell) → 로봇 구간을 하나의 시간축으로 잇는다."""

    def __init__(self, pins=None, robot_phase=None, dwell=1.0):
        self.pins = pins
        self.robot = robot_phase
        self.dwell = max(0.0, float(dwell))

        self.t_pins = pins.duration if pins else 0.0
        self.t_robot = robot_phase.duration if robot_phase else 0.0
        self.duration = self.t_pins + self.dwell + self.t_robot

    def sample(self, t):
        """t초 시점의 상태.

        돌려주는 dict:
          phase        "pins" | "dwell" | "robot" | "done"
          heights      핀 높이 목록 (없으면 None)
          pose         로봇 관절각 dict (없으면 None)
          seg          로봇 구간 인덱스
          progress     0~1
        """
        t = max(0.0, float(t))
        out = {"t": t, "phase": "done", "heights": None, "pose": None,
               "seg": 0, "frac": 0.0,
               "progress": (t / self.duration) if self.duration > 0 else 1.0}
        if out["progress"] > 1.0:
            out["progress"] = 1.0

        if self.pins is not None:
            out["heights"] = self.pins.heights_at(min(t, self.t_pins))

        # 핀 구간·정지 구간에서도 로봇은 **출발 자세로 서 있다.**
        # pose 를 None 으로 두면 로봇이 화면에서 사라진다 — 실제로는 대기 중이고,
        # 정지 상태(t=0)로 두면 "로봇이 안 보인다"가 된다(실측으로 걸렸다).
        start_pose = None
        if self.robot is not None and self.robot.poses:
            start_pose = dict(self.robot.poses[0])

        if t < self.t_pins:
            out["phase"] = "pins"
            out["pose"] = start_pose
            return out

        if t < self.t_pins + self.dwell:
            out["phase"] = "dwell"
            out["pose"] = start_pose
            return out

        if self.robot is None or not self.robot.poses:
            return out

        tr = t - self.t_pins - self.dwell
        pose, seg, frac = self.robot.sample(tr)
        out["pose"] = pose
        out["seg"] = seg
        out["frac"] = frac
        out["phase"] = "robot" if tr < self.robot.duration else "done"
        return out


def build(pin_bases=None, pin_h_start=None, pin_h_end=None,
          pin_speed=DEFAULT_PIN_SPEED,
          poses=None, kinds=None, points=None,
          feed=DEFAULT_FEED, joint_scale=DEFAULT_JOINT_SCALE,
          dwell=1.0):
    """입력을 받아 Timeline 을 만든다. 없는 구간은 건너뛴다."""
    pins = None
    if pin_bases and pin_h_end:
        h0 = pin_h_start if pin_h_start else [0.0] * len(pin_h_end)
        pins = PinPhase(pin_bases, h0, pin_h_end, pin_speed)

    rp = None
    if poses:
        rp = RobotPhase(poses, kinds=kinds, points=points,
                        feed=feed, joint_scale=joint_scale)

    return Timeline(pins=pins, robot_phase=rp, dwell=dwell)


def report(tl):
    """타임라인 요약 — 컴포넌트 info 에 그대로 쓴다."""
    lines = []
    if tl.pins is not None:
        p = tl.pins
        lines.append("핀 상승:     {:.1f} 초  (최대 행정 {:.0f} mm @ {:.0f} mm/s)".format(
            p.duration, max(p.travel) if p.travel else 0.0, p.speed))
        lines.append("             <- 핀은 동시에 출발해 각자 멈춘다. 구간 길이는")
        lines.append("                가장 많이 움직이는 핀이 정한다")
    if tl.dwell > 0:
        lines.append("정지:        {:.1f} 초".format(tl.dwell))
    if tl.robot is not None:
        r = tl.robot
        n_feed = sum(1 for k in r.dt_kind if k == "feed")
        t_feed = sum(d for d, k in zip(r.dt, r.dt_kind) if k == "feed")
        t_joint = r.duration - t_feed
        lines.append("로봇:        {:.1f} 초  ({}구간)".format(
            r.duration, len(r.dt)))
        lines.append("  이송 지배: {:>5}구간  {:.1f} 초  (feed {:.0f} mm/s)".format(
            n_feed, t_feed, r.feed))
        lines.append("  관절 지배: {:>5}구간  {:.1f} 초  (속도 {:.0f}%)".format(
            len(r.dt) - n_feed, t_joint, r.joint_scale * 100.0))
        lines.append("             <- 성형은 공정 속도가, 공중 이동은 관절 속도가")
        lines.append("                지배한다. 느린 쪽이 실제 시간이다")
    lines.append("")
    lines.append("합계:        {:.1f} 초 ({:.1f} 분)".format(
        tl.duration, tl.duration / 60.0))
    lines.append("             <- 가감속 무시한 하한이다. 실제로는 더 걸린다")
    return "\n".join(lines)

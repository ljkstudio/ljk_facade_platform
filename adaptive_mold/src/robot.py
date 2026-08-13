# -*- coding: utf-8 -*-
"""ABB IRB 6700-150/3.20 기구학 — 웹 시뮬레이터(three.js)에서 이식.

원본: ljks_website_v2/src/lib/irb6700/{robotRig,kinematics}.ts
그쪽에는 vitest 테스트가 붙어 있어 정답지로 쓸 수 있다. 값은 ROS-Industrial
공식 URDF(abb_irb6700_support)와 GLB 실측 바운딩박스를 교차검증한 것이다.

──────────────────────────────────────────────────────────
단위 — 이 모듈의 가장 중요한 규약
──────────────────────────────────────────────────────────

**내부 계산은 미터, 외부 인터페이스는 밀리미터.**

IK의 수치(λ=0.06, posTol=0.0005, maxStep=0.25)는 미터 기준으로 튜닝돼 있다.
그대로 mm로 옮기면 자코비안이 1000배가 되어 λ²항이 상대적으로 10⁶배 작아지고,
감쇠가 사실상 사라져 특이점 근처에서 발산한다. 위치 오차와 자세 오차의
가중 균형도 1000배 어긋난다.

그래서 경계에서만 변환한다 — Rhino 문서는 mm, 이 모듈 속은 m.

──────────────────────────────────────────────────────────
TCP 규약 — 툴패스 타겟과 다르다
──────────────────────────────────────────────────────────

toolpath.py 의 타겟 Plane:  X = 진행 방향,  Y = 롤러 축,  Z = -법선
로봇 TCP 프레임:            X = 롤러 축,    Y = -진행,    Z = -법선

Z는 같고 X·Y가 Z축 기준 -90° 돌아가 있다. 그대로 넘기면 롤러가 90° 틀어진
자세로 굴러간다 — 화면으로는 그럴듯하고 실물에서 판재를 긁는다.
`tcp_target_from_toolpath()` 가 이 변환을 담당한다.
"""

import math

import Rhino.Geometry as rg


MM = 1000.0                     # m → mm

JOINT_NAMES = ["j1", "j2", "j3", "j4", "j5", "j6"]

# 관절 회전 피벗 — **절대 좌표**(native Z-up, meter). 부모 누적이 아니다.
PIVOTS_M = {
    "j1": (0.0, 0.0, 0.78),
    "j2": (0.32, 0.0, 0.78),
    "j3": (0.32, 0.0, 1.94),
    "j4": (0.32, 0.0, 2.105),
    "j5": (1.6, 0.0, 2.105),
    "j6": (1.876, 0.0, 2.105),
}

# ROS-Industrial 축 순서 (z, y, y, x, y, x)
JOINT_AXIS = {"j1": "z", "j2": "y", "j3": "y", "j4": "x", "j5": "y", "j6": "x"}

# ABB IRB6700-150/3.2 공식 가동범위 (deg)
JOINT_LIMITS = {
    "j1": (-170.0, 170.0),
    "j2": (-65.0, 85.0),
    "j3": (-180.0, 70.0),
    "j4": (-300.0, 300.0),
    "j5": (-130.0, 130.0),
    "j6": (-360.0, 360.0),
}

# 축별 최대 속도 (deg/s) — 데이터시트. 사이클 타임 산정용.
JOINT_MAX_SPEED = {"j1": 100.0, "j2": 90.0, "j3": 90.0,
                   "j4": 170.0, "j5": 120.0, "j6": 190.0}

# 툴 플랜지(J6 피벗)에서 롤러 접촉점까지 (native +x, meter)
TOOL_LENGTH_M = 0.34

HOME_POSE = dict((j, 0.0) for j in JOINT_NAMES)
READY_POSE = {"j1": 0.0, "j2": 20.0, "j3": -30.0, "j4": 0.0, "j5": 40.0, "j6": 0.0}
APPROACH_POSE = {"j1": 0.0, "j2": 45.0, "j3": -38.0, "j4": 0.0, "j5": 80.0, "j6": 0.0}

DEG = math.pi / 180.0
_AXIS_VEC = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def clamp_joint(name, deg):
    lo, hi = JOINT_LIMITS[name]
    return clamp(deg, lo, hi)


# ──────────────────────────────────────────────────────────
# 순기구학
# ──────────────────────────────────────────────────────────

def joint_frames(pose_deg):
    """관절별 월드 변환(미터)을 순서대로 돌려준다.

    three.js 규약을 그대로 옮긴다. 각 관절 그룹의 로컬 행렬은
    `T(부모피벗과의 차) * R(로컬축, 각도)` 이고 월드는 부모 누적이다.
    """
    frames = []
    world = rg.Transform.Identity
    prev = (0.0, 0.0, 0.0)
    for j in JOINT_NAMES:
        px, py, pz = PIVOTS_M[j]
        off = rg.Transform.Translation(px - prev[0], py - prev[1], pz - prev[2])
        ax = _AXIS_VEC[JOINT_AXIS[j]]
        rot = rg.Transform.Rotation(pose_deg.get(j, 0.0) * DEG,
                                    rg.Vector3d(ax[0], ax[1], ax[2]),
                                    rg.Point3d.Origin)
        world = world * off * rot
        frames.append(world)
        prev = (px, py, pz)
    return frames


def tcp_frame(pose_deg):
    """TCP 월드 변환(미터).

    J6 플랜지에서 native +x로 TOOL_LENGTH 만큼 나간 뒤 Y축 +90° 회전.
    그 회전 때문에 TCP 로컬 +Z가 팔이 뻗은 방향(native +x)을 향한다 —
    공구가 플랜지에서 앞으로 튀어나온 형상에 맞는 규약이다.
    """
    j6 = joint_frames(pose_deg)[-1]
    tool = rg.Transform.Translation(TOOL_LENGTH_M, 0.0, 0.0)
    spin = rg.Transform.Rotation(math.pi / 2.0, rg.Vector3d.YAxis,
                                 rg.Point3d.Origin)
    return j6 * tool * spin


def _origin_of(xf):
    p = rg.Point3d(0.0, 0.0, 0.0)
    p.Transform(xf)
    return p


def _dir_of(xf, v):
    d = rg.Vector3d(v[0], v[1], v[2])
    d.Transform(xf)          # Vector3d.Transform은 평행이동을 무시한다
    d.Unitize()
    return d


def frame_to_plane(xf):
    """변환에서 Plane을 뽑는다 (원점 + X·Y축)."""
    o = _origin_of(xf)
    x = _dir_of(xf, (1.0, 0.0, 0.0))
    y = _dir_of(xf, (0.0, 1.0, 0.0))
    return rg.Plane(o, x, y)


def tcp_plane_mm(pose_deg):
    """TCP를 mm 단위 Plane으로 — Rhino 문서에 그릴 때 쓴다."""
    pl = frame_to_plane(tcp_frame(pose_deg))
    pl.Origin = rg.Point3d(pl.Origin.X * MM, pl.Origin.Y * MM, pl.Origin.Z * MM)
    return pl


DEFAULT_BASE_OFFSET_MM = 1900.0

# 베이스 원기둥의 반경 (mm). **실측**: irb6700_parts.3dm 의 base 파트 바운딩박스가
# x[-627, 377], y[-360, 360] 이므로 원점에서 가장 먼 쪽이 627 mm 다.
# 630 으로 잡아 조금 보수적으로 본다.
BASE_RADIUS_MM = 630.0


def base_overlap(base_plane, points, radius=BASE_RADIUS_MM):
    """베이스가 몰드 영역과 평면상 겹치는 깊이 (mm). 0 이하면 안 겹친다.

    **IK 는 간섭을 모른다.** 로봇을 몰드 한가운데 세워도 팔이 몰드를 통과해
    타겟에 닿으면 "도달 성공"으로 센다(실측: 베이스를 몰드 위로 옮겼더니
    668/1175 는 실패했지만 나머지 507 개는 성공으로 잡혔고, 그 자세들은 몸통이
    몰드를 관통한다).

    전면 간섭 검사는 무겁다. 그런데 **베이스가 몰드 영역과 겹치는 것만은
    무조건 불가능**하므로, 그것만은 값싸게 잡을 수 있다. 이 함수가 그 몫이다.

    `points` 는 몰드 영역을 대표하는 점들(핀 격자 등)이다. 월드 XY 로 투영한
    축정렬 상자를 쓴다 — 회전한 몰드에서는 조금 보수적으로 나온다.
    """
    pts = [p for p in (points or []) if p is not None]
    if not pts or base_plane is None:
        return 0.0

    xs = [p.X for p in pts]
    ys = [p.Y for p in pts]
    o = base_plane.Origin
    dx = max(min(xs) - o.X, 0.0, o.X - max(xs))
    dy = max(min(ys) - o.Y, 0.0, o.Y - max(ys))
    dist = math.sqrt(dx * dx + dy * dy)
    return radius - dist


def default_base_plane(target_planes):
    """robot_base 를 주지 않았을 때 쓰는 베이스 — 타겟 박스 중심에서 -X로.

    웹 시뮬레이터가 베드를 X=1.4 m 에 두고 도달 스위트스폿을 확인한 값에서
    왔고, 이 저장소에서 base_x 를 -1400/-1300/-1200 으로 훑어 -1400(= 중심에서
    1900) 이 최선인 것을 실측했다.

    **표시 컴포넌트와 계산 컴포넌트가 이 값을 각자 갖고 있으면 안 된다.**
    한쪽만 고치면 로봇이 계산된 위치와 다른 곳에 그려지는데, 화면은 그럴듯해서
    틀린 줄 모른다. 그래서 여기 한 곳에 둔다.
    """
    pts = [p.Origin for p in target_planes if p is not None]
    if not pts:
        return rg.Plane.WorldXY
    c = rg.BoundingBox(pts).Center
    return rg.Plane(rg.Point3d(c.X - DEFAULT_BASE_OFFSET_MM, c.Y, 0.0),
                    rg.Vector3d.XAxis, rg.Vector3d.YAxis)


def _direction_of(obj):
    """Line·Curve·Vector 무엇이 와도 방향 벡터를 뽑는다.

    GH 입력이 무엇으로 들어올지 한 가지로 못 정한다 — 힌트를 Line 으로 걸어도
    사용자가 Curve 나 Vector 를 물릴 수 있다. 되는 것을 다 받는다.
    """
    if obj is None:
        return None
    v = getattr(obj, "Direction", None)      # Line, Vector3d 는 여기서 끝난다
    if v is None:
        a = getattr(obj, "From", None) or getattr(obj, "PointAtStart", None)
        b = getattr(obj, "To", None) or getattr(obj, "PointAtEnd", None)
        if a is None or b is None:
            if isinstance(obj, rg.Vector3d):
                v = rg.Vector3d(obj)
            else:
                return None
        else:
            v = rg.Vector3d(b - a)
    v = rg.Vector3d(v)
    return v if v.Length > 1e-9 else None


def _start_of(obj):
    if obj is None:
        return None
    p = getattr(obj, "From", None)
    if p is None:
        p = getattr(obj, "PointAtStart", None)
    return rg.Point3d(p) if p is not None else None


def base_plane_from(point=None, line=None, targets=None):
    """점과 선으로 베이스 평면을 만든다. `(평면, 설명)` 을 돌려준다.

    Plane 을 GH 에서 만드는 것보다 **Rhino 에서 점을 찍고 선을 긋는 것**이 쉽다.
    그래서 이 두 입력을 받는다.

        선만       원점 = 선의 시작점, +X = 선 방향
        점 + 선    원점 = 점,          +X = 선 방향
        점만       원점 = 점,          +X = 타겟 중심을 향한다
        둘 다 없음 (None, "") — 호출한 쪽이 기본값을 쓴다

    **로봇은 언제나 똑바로 선다.** 방향 벡터를 월드 XY 로 투영하므로 기울어진
    선을 그어도 베이스가 눕지 않는다 — 원격 뷰포트에서 선을 그으면 의도와 달리
    기울어지기 쉽고, 그걸 그대로 받으면 로봇이 넘어진다. 투영으로 바뀌었으면
    설명에 적어 돌려주므로 조용히 넘어가지 않는다.
    베이스를 실제로 기울이고 싶으면 `robot_base` 로 평면을 직접 준다.
    """
    origin = rg.Point3d(point) if point is not None else _start_of(line)
    if origin is None:
        return None, ""

    notes = []
    v = _direction_of(line)

    if v is None and targets:
        pts = [p.Origin for p in targets if p is not None]
        if pts:
            c = rg.BoundingBox(pts).Center
            v = rg.Vector3d(c - origin)
            notes.append("방향은 타겟 중심을 향하게 잡았다")

    if v is None:
        v = rg.Vector3d.XAxis
        notes.append("방향이 없어 월드 X 를 썼다")

    if abs(v.Z) > 1e-6:
        notes.append("선이 수평이 아니라 XY 로 투영했다 (로봇은 똑바로 선다)")
    v.Z = 0.0
    if v.Length < 1e-9:
        v = rg.Vector3d.XAxis
        notes.append("선이 수직이어서 방향을 못 얻었다 — 월드 X 를 썼다")
    v.Unitize()

    y = rg.Vector3d.CrossProduct(rg.Vector3d.ZAxis, v)
    return rg.Plane(origin, v, y), "; ".join(notes)


def resolve_base_plane(robot_base=None, base_pt=None, base_dir=None,
                       targets=None):
    """베이스 평면 하나로 정리한다 — **두 컴포넌트가 반드시 같이 써야 한다.**

    우선순위: `robot_base`(평면) > 점·선 > 자동 기본값.

    표시 컴포넌트와 계산 컴포넌트가 각자 이 판단을 하면, 한쪽만 고쳐도 오류가
    나지 않고 **로봇이 계산된 위치와 다른 곳에 그려진다**(J-006 TRAP-03).
    """
    if robot_base is not None:
        return robot_base, "입력(평면)"

    pl, note = base_plane_from(base_pt, base_dir, targets)
    if pl is not None:
        src = "점+선" if (base_pt is not None and base_dir is not None) else (
            "선" if base_dir is not None else "점")
        return pl, src + ((" — " + note) if note else "")

    return default_base_plane(targets), "자동"


def link_lines_mm(pose_deg, base_plane=None):
    """관절 피벗을 이은 선 + 플랜지→TCP 선 (mm). 애니메이션 표시용."""
    frames = joint_frames(pose_deg)
    pts = [rg.Point3d(0.0, 0.0, 0.0)]
    for xf in frames:
        pts.append(_origin_of(xf))
    pts.append(_origin_of(tcp_frame(pose_deg)))

    scaled = [rg.Point3d(p.X * MM, p.Y * MM, p.Z * MM) for p in pts]
    if base_plane is not None:
        xf = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, base_plane)
        for p in scaled:
            p.Transform(xf)
    return [rg.Line(a, b) for a, b in zip(scaled, scaled[1:])]


# ──────────────────────────────────────────────────────────
# 역기구학 — Damped Least Squares (Levenberg–Marquardt)
# ──────────────────────────────────────────────────────────
#
# 해석적 6R 해를 쓰지 않는 이유: 이 리그의 손목(J4·J5·J6)이 한 점에서 만나는
# 완전 구면손목이 아니라 해석해가 지저분하다. DLS는 특이점 근처에서도 발산하지
# 않고, 이전 포즈를 시드로 주면 타깃이 조금씩 움직이는 곡면 추종에서 매우
# 안정적으로 수렴한다.

def _solve_linear(A, b):
    """작은 선형계 가우스 소거 (부분 피벗)."""
    n = len(b)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = col
        for r in range(col + 1, n):
            if abs(M[r][col]) > abs(M[piv][col]):
                piv = r
        if abs(M[piv][col]) < 1e-12:
            continue
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        for c in range(col, n + 1):
            M[col][c] /= d
        for r in range(n):
            if r == col:
                continue
            f = M[r][col]
            if f == 0.0:
                continue
            for c in range(col, n + 1):
                M[r][c] -= f * M[col][c]
    return [M[i][n] for i in range(n)]


def _quat_from_frame(xf):
    """회전행렬 → 쿼터니언 (Shepperd). 자세 오차를 각도-축으로 바꾸는 데 쓴다."""
    x = _dir_of(xf, (1.0, 0.0, 0.0))
    y = _dir_of(xf, (0.0, 1.0, 0.0))
    z = _dir_of(xf, (0.0, 0.0, 1.0))
    m = [[x.X, y.X, z.X], [x.Y, y.Y, z.Y], [x.Z, y.Z, z.Z]]
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        return ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s,
                (m[1][0] - m[0][1]) / s, 0.25 * s)
    if m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        return (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s,
                (m[2][1] - m[1][2]) / s)
    if m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        return ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s,
                (m[0][2] - m[2][0]) / s)
    s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
    return ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s,
            (m[1][0] - m[0][1]) / s)


def _quat_mul_inv(qa, qb):
    """qa * inverse(qb) — 단위 쿼터니언 가정."""
    ax, ay, az, aw = qa
    bx, by, bz, bw = qb
    bx, by, bz = -bx, -by, -bz
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


class IKResult(object):
    def __init__(self, pose, pos_err_mm, rot_err, iterations, converged,
                 at_limit):
        self.pose = pose
        self.pos_err_mm = pos_err_mm
        self.rot_err = rot_err
        self.iterations = iterations
        self.converged = converged
        self.at_limit = at_limit      # 가동범위에 걸린 관절 이름 목록


def solve_ik(target_plane_m, seed_pose=None, iterations=30, pos_tol_m=0.0005,
             rot_weight=0.4, lam=0.06, max_step=0.25):
    """TCP를 target_plane(미터)에 맞추는 포즈를 찾는다.

    target_plane 은 **TCP 규약**이어야 한다 (X=롤러축, Z=-법선).
    툴패스 타겟을 넣으려면 tcp_target_from_toolpath()를 먼저 거칠 것.

    rot_weight=0 이면 위치 전용 IK.
    """
    pose = dict(seed_pose if seed_pose else APPROACH_POSE)
    rows = 6 if rot_weight > 0 else 3
    lam2 = lam * lam

    t_pos = target_plane_m.Origin
    t_quat = _quat_from_frame(
        rg.Transform.PlaneToPlane(rg.Plane.WorldXY, target_plane_m))

    pos_err = float("inf")
    rot_err = 0.0
    it = 0

    for it in range(iterations):
        frames = joint_frames(pose)
        tcp = tcp_frame(pose)
        ee = _origin_of(tcp)

        ex = t_pos.X - ee.X
        ey = t_pos.Y - ee.Y
        ez = t_pos.Z - ee.Z
        pos_err = math.sqrt(ex * ex + ey * ey + ez * ez)

        rx = ry = rz = 0.0
        if rows == 6:
            q = _quat_from_frame(tcp)
            qe = _quat_mul_inv(t_quat, q)
            if qe[3] < 0.0:
                qe = (-qe[0], -qe[1], -qe[2], -qe[3])
            rx, ry, rz = 2.0 * qe[0], 2.0 * qe[1], 2.0 * qe[2]
            rot_err = math.sqrt(rx * rx + ry * ry + rz * rz)

        if pos_err < pos_tol_m and (rows == 3 or rot_err < 0.02):
            break

        J = [[0.0] * 6 for _ in range(rows)]
        for c, name in enumerate(JOINT_NAMES):
            xf = frames[c]
            axis = _dir_of(xf, _AXIS_VEC[JOINT_AXIS[name]])
            piv = _origin_of(xf)
            tx, ty, tz = ee.X - piv.X, ee.Y - piv.Y, ee.Z - piv.Z
            J[0][c] = axis.Y * tz - axis.Z * ty
            J[1][c] = axis.Z * tx - axis.X * tz
            J[2][c] = axis.X * ty - axis.Y * tx
            if rows == 6:
                J[3][c] = axis.X * rot_weight
                J[4][c] = axis.Y * rot_weight
                J[5][c] = axis.Z * rot_weight

        e = [ex, ey, ez]
        if rows == 6:
            e += [rx * rot_weight, ry * rot_weight, rz * rot_weight]

        JJt = [[0.0] * rows for _ in range(rows)]
        for i in range(rows):
            for k in range(rows):
                s = 0.0
                for c in range(6):
                    s += J[i][c] * J[k][c]
                JJt[i][k] = s + (lam2 if i == k else 0.0)

        y = _solve_linear(JJt, e)
        for c, name in enumerate(JOINT_NAMES):
            s = 0.0
            for i in range(rows):
                s += J[i][c] * y[i]
            d = clamp(s, -max_step, max_step)
            pose[name] = clamp_joint(name, pose[name] + d / DEG)

    at_limit = []
    for name in JOINT_NAMES:
        lo, hi = JOINT_LIMITS[name]
        if abs(pose[name] - lo) < 1e-6 or abs(pose[name] - hi) < 1e-6:
            at_limit.append(name)

    return IKResult(pose, pos_err * MM, rot_err, it,
                    pos_err < pos_tol_m * 3.0, at_limit)


# ──────────────────────────────────────────────────────────
# 툴패스 ↔ 로봇 좌표 어댑터
# ──────────────────────────────────────────────────────────

def tcp_target_from_toolpath(plane_mm, base_plane=None):
    """툴패스 타겟(mm, X=진행) → 로봇 TCP 타겟(m, X=롤러축).

    두 규약의 Z는 같고 X·Y가 Z축 기준 -90° 돌아가 있다. 이 변환을 빼먹으면
    롤러가 90° 틀어진 자세로 굴러간다.

    base_plane 이 주어지면 그 평면을 로봇 베이스 원점으로 보고 역변환한다
    (= 몰드를 로봇 좌표계로 가져온다).
    """
    pl = rg.Plane(plane_mm)
    if base_plane is not None:
        pl.Transform(rg.Transform.PlaneToPlane(base_plane, rg.Plane.WorldXY))

    x_new = rg.Vector3d(pl.YAxis)                 # 롤러 축
    y_new = rg.Vector3d(pl.XAxis)
    y_new.Reverse()                               # -진행
    o = rg.Point3d(pl.Origin.X / MM, pl.Origin.Y / MM, pl.Origin.Z / MM)
    return rg.Plane(o, x_new, y_new)


def flip_about_approach(plane):
    """접근축(Z) 기준 180° 회전한 같은 자세.

    **롤러는 원통이므로 축 방향의 부호가 물리적으로 무의미하다.** 축을 뒤집어도
    접촉선은 같은 직선이고 같은 자세다. 이 자유도를 쓰지 않으면 지그재그로
    진행 방향이 뒤집힐 때마다 손목이 180°씩 감겨 J6이 가동한계에 걸린다.
    """
    x = rg.Vector3d(plane.XAxis)
    y = rg.Vector3d(plane.YAxis)
    x.Reverse()
    y.Reverse()
    return rg.Plane(plane.Origin, x, y)


def track_toolpath(targets_mm, base_plane=None, seed_pose=None,
                   resolve_flip=True, **ik_opts):
    """툴패스 타겟 전체를 추종한다. 앞 결과를 다음 시드로 쓴다(continuation).

    시드를 이어 쓰지 않으면 매 타겟에서 다른 해로 튀어 관절이 요동친다.

    resolve_flip=True 이면 롤러 대칭(180°)을 이용해 **이전 자세에 가까운 쪽**을
    고른다. 끄면 손목이 감긴다.
    """
    poses = []
    results = []
    flips = 0
    seed = dict(seed_pose if seed_pose else APPROACH_POSE)
    prev_axis = None

    for pl in targets_mm:
        tgt = tcp_target_from_toolpath(pl, base_plane)

        if resolve_flip and prev_axis is not None:
            alt = flip_about_approach(tgt)
            if alt.XAxis * prev_axis > tgt.XAxis * prev_axis:
                tgt = alt
                flips += 1

        r = solve_ik(tgt, seed_pose=seed, **ik_opts)
        seed = r.pose
        prev_axis = rg.Vector3d(tgt.XAxis)
        poses.append(dict(r.pose))
        results.append(r)

    return poses, results, flips


def cycle_time(poses, speed_scale=1.0):
    """관절 최대 속도로 포즈 사이 이동 시간을 합산한다 (초).

    가감속을 무시한 **하한**이다. 실제로는 더 걸린다.
    """
    total = 0.0
    for a, b in zip(poses, poses[1:]):
        worst = 0.0
        for j in JOINT_NAMES:
            d = abs(b[j] - a[j])
            worst = max(worst, d / (JOINT_MAX_SPEED[j] * speed_scale))
        total += worst
    return total

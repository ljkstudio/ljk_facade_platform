# -*- coding: utf-8 -*-
"""IRB6700 실물 형상(메시)을 관절에 매핑한다.

기구학은 robot.py 가 갖고, 이 모듈은 **그 프레임에 메시를 얹는 일만** 한다.

──────────────────────────────────────────────────────────
매핑의 근거 — 왜 이 한 줄로 끝나는가
──────────────────────────────────────────────────────────

`irb6700_parts.3dm` 의 파트는 **영각(零角) 자세로 제자리에 있다**
(원본 GLB 가 공통 좌표계에 배치돼 있었다 — import_robot_glb.py 참조).

`robot.joint_frames(pose)[j]` 는 관절 j 의 월드 변환이고, 영각에서는
`Translation(pivot_j)` 다. 따라서 파트를 영각에서 임의 자세로 옮기는 변환은

    M_j(pose) = joint_frames(pose)[j] * Translation(-pivot_j)

이다. 영각에서 이것이 **정확히 항등**이 되는 것이 정합의 증거이고,
`test_robot_body.py` 가 그것을 확인한다.

더 강한 불변식도 확인한다: `M_j` 로 영각 피벗점을 옮기면 그 자세의 피벗
위치가 나와야 한다. 이건 부동소수 오차 말고는 어긋날 여지가 없다.

──────────────────────────────────────────────────────────
단위
──────────────────────────────────────────────────────────

robot.py 속은 **미터**, 메시는 **밀리미터**다. 그래서 미터 변환을 mm 공간으로
켤레변환(S·M·S⁻¹)한다 — 회전은 그대로, 평행이동만 1000배가 된다.
mm 로 계산된 변환을 미터 프레임에 섞으면 회전 중심이 1000배 어긋난다.

──────────────────────────────────────────────────────────
밸런서(cylinder / rod) — 슬라이더-크랭크로 푼다
──────────────────────────────────────────────────────────

실린더는 link1(캐러셀)에 핀으로 달려 있고, 로드는 link2(상완)에 핀으로 물려
실린더 안에서 미끄러진다. 즉 **삼각형 하나**다 — 두 피벗과 그 사이 거리.

    P_c  실린더 뒤끝 핀. link1 에 고정 → j1 만 따라간다
    P_a  로드 앞끝 핀. link2 에 고정 → j2 를 따라 움직인다
    축   언제나 P_c → P_a. 실린더는 P_c 에서 돌고, 로드는 그만큼 밀려 나온다

j2 축이 Y 이므로 P_a 는 **x-z 평면 안에서만** 움직인다(y 보존). 그래서 각도와
신장은 x-z 투영으로 정확히 풀린다 — 근사가 아니다.

**전에는 `J2 mimic -0.25` 근사였고, 부호가 반대였다.** 실측(J-013):

| j2 | 실린더 회전 (참) | 옛 구현 | 신장 |
|---|---|---|---|
| -17° | -3.58° | +4.25° | +8 mm |
| +30° | +5.98° | -7.50° | +25 mm |
| +78° | +10.18° | **-19.50°** | +136 mm |

게다가 옛 구현은 회전 중심을 **j2 피벗**으로 잡아 실린더 마운트가 최대 295 mm
움직였다(프레임에 볼트로 고정된 점이다). 눈에 그대로 보였다.

**피벗은 하드코딩하지 않고 형상에서 유도한다** — `balancer_pivots_from_parts()`.
아래 상수는 그것을 실측해 적어 둔 기본값이고, 테스트가 둘이 일치하는지 본다.
GLB 원본이 바뀌면 테스트가 먼저 깨진다.

교차 검증: 유도한 피벗으로 계산한 행정이 **136 mm** 이고, 원본 문서
(KINEMATICS.md)의 `piston_joint: prismatic 0.15` = 150 mm 안이다. 서로 다른
출처가 같은 값을 말한다.
"""

import math

import Rhino
import Rhino.Geometry as rg

import robot as rb


# 파트 이름 → 관절. None 은 고정(베이스).
PART_JOINT = [
    ("base",     None),
    ("link1",    "j1"),
    ("link2",    "j2"),
    ("link3",    "j3"),
    ("link4",    "j4"),
    ("link5",    "j5"),
    ("link6",    "j6"),
]

BALANCER_PARTS = ("cylinder", "rod")

# 밸런서 두 피벗 (mm, 영각 좌표) — **형상에서 유도한 실측값.**
#   P_c 실린더 뒤끝: link1 에 고정
#   P_a 로드 앞끝:   link2 에 고정
# 유도 방법은 balancer_pivots_from_parts() 에 있고, 테스트가 이 상수와
# 형상에서 다시 유도한 값이 일치하는지 확인한다.
BALANCER_MOUNT_MM = (-530.83, -195.88, 599.53)
BALANCER_PIN_MM = (168.83, -190.56, 748.53)

# 로드 축에서 이 거리 안의 정점만 실린더 관으로 본다 (mm).
# 실린더 파트는 마운트 요크를 포함해 y 폭이 389 mm 라 bbox 로는 축을 못 잡는다.
BALANCER_TUBE_R = 90.0

PART_NAMES = [n for n, _ in PART_JOINT] + list(BALANCER_PARTS)


def _mm(xf_m):
    """미터 변환을 mm 공간으로 켤레변환한다."""
    s = rg.Transform.Scale(rg.Point3d.Origin, rb.MM)
    si = rg.Transform.Scale(rg.Point3d.Origin, 1.0 / rb.MM)
    return s * xf_m * si


def _rest_inverse(joint):
    """영각 프레임의 역 = Translation(-pivot) (미터)."""
    px, py, pz = rb.PIVOTS_M[joint]
    return rg.Transform.Translation(-px, -py, -pz)


def _pt(v, default):
    """Point3d 든 (x, y, z) 든 Point3d 로. None 이면 기본값.

    두 형태를 다 받는 이유: 상수는 튜플이고 `balancer_pivots_from_parts()` 는
    Point3d 를 돌려준다. 한쪽만 받게 두면 호출부에 따라 조용히 깨진다
    (실측: `*(mount or CONST)` 가 Point3d 에서 TypeError — 기본값으로만 쓰는
    테스트는 이걸 못 잡았다).
    """
    if v is None:
        return rg.Point3d(*default)
    if isinstance(v, rg.Point3d):
        return rg.Point3d(v)
    return rg.Point3d(v[0], v[1], v[2])


def balancer_pivots_from_parts(parts, tube_r=BALANCER_TUBE_R):
    """메시에서 두 피벗을 유도한다. `(mount, pin)` 또는 `(None, None)`.

    **축은 로드로 잡는다.** 로드는 y 폭 55 mm 짜리 깨끗한 원통이라 주축이
    선명한데, 실린더 파트는 마운트 요크를 포함해 bbox 로는 축을 못 잡는다
    (y 폭 389 mm). 축을 잡은 뒤 두 파트의 양 끝을 그 축 위로 투영한다.

    실린더 쪽은 **축에서 `tube_r` 안의 정점만** 쓴다 — 요크의 정점이 섞이면
    뒤끝이 엉뚱한 곳으로 간다.
    """
    rod = parts.get("rod")
    cyl = parts.get("cylinder")
    if rod is None or cyl is None:
        return None, None

    o, d = _principal_axis(rod)
    if d is None:
        return None, None
    if d.X < 0.0:
        d.Reverse()                       # +x 를 앞으로 (로드가 나오는 쪽)

    def at(t):
        return rg.Point3d(o.X + d.X * t, o.Y + d.Y * t, o.Z + d.Z * t)

    t_front = None
    for i in range(rod.Vertices.Count):
        v = rod.Vertices[i]
        t = (rg.Point3d(v.X, v.Y, v.Z) - o) * d
        if t_front is None or t > t_front:
            t_front = t

    t_back = None
    for i in range(cyl.Vertices.Count):
        v = cyl.Vertices[i]
        p = rg.Point3d(v.X, v.Y, v.Z)
        t = (p - o) * d
        if p.DistanceTo(at(t)) > tube_r:
            continue                      # 요크 — 관이 아니다
        if t_back is None or t < t_back:
            t_back = t

    if t_front is None or t_back is None:
        return None, None
    return at(t_back), at(t_front)


def _principal_axis(mesh):
    """정점 분포의 주축. `(중심, 방향)` — 공분산 최대 고유벡터를 거듭제곱법으로."""
    n = mesh.Vertices.Count
    if n < 3:
        return rg.Point3d.Origin, None
    cx = cy = cz = 0.0
    for i in range(n):
        v = mesh.Vertices[i]
        cx += v.X
        cy += v.Y
        cz += v.Z
    cx, cy, cz = cx / n, cy / n, cz / n

    c = [[0.0] * 3 for _ in range(3)]
    for i in range(n):
        v = mesh.Vertices[i]
        dd = (v.X - cx, v.Y - cy, v.Z - cz)
        for a in range(3):
            for b in range(3):
                c[a][b] += dd[a] * dd[b]

    vec = [1.0, 0.0, 0.0]
    for _ in range(200):
        w = [sum(c[a][b] * vec[b] for b in range(3)) for a in range(3)]
        m = math.sqrt(sum(x * x for x in w))
        if m < 1e-12:
            return rg.Point3d(cx, cy, cz), None
        vec = [x / m for x in w]
    return rg.Point3d(cx, cy, cz), rg.Vector3d(vec[0], vec[1], vec[2])


def _balancer_transforms(by_joint, mount, pin):
    """밸런서 두 파트의 mm 변환. `(실린더, 로드)`

    j2 축이 Y 라 P_a 는 x-z 평면 안에서만 움직인다(y 보존). 그래서 각도와
    신장을 x-z 투영으로 정확히 구할 수 있다.

    실린더는 P_c 에서 회전만, 로드는 같은 회전 + 새 축 방향 신장이다.
    둘 다 마지막에 link1 의 운동을 얹는다 — P_c 가 link1 에 고정이므로.
    """
    m1 = _mm(by_joint["j1"] * _rest_inverse("j1"))
    m2 = _mm(by_joint["j2"] * _rest_inverse("j2"))

    # link1 국소 프레임에서의 j2 운동. 역행렬을 쓰는 이유는 j1 이 빠지는 것을
    # 가정하지 않기 위해서다(가정해도 맞지만, 가정은 언젠가 틀린다).
    ok, inv = m1.TryGetInverse()
    rel = (inv * m2) if ok else m2

    pin_now = rg.Point3d(pin)
    pin_now.Transform(rel)

    a0x, a0z = pin.X - mount.X, pin.Z - mount.Z
    a1x, a1z = pin_now.X - mount.X, pin_now.Z - mount.Z
    l0 = math.sqrt(a0x * a0x + a0z * a0z)
    l1 = math.sqrt(a1x * a1x + a1z * a1z)
    if l0 < 1e-9 or l1 < 1e-9:
        return m1, m1

    # Rhino 의 Y축 회전은 x-z 각을 **감소**시킨다(오른손 법칙: +Z -> +X).
    # 그래서 각을 Δφ 만큼 키우려면 -Δφ 로 돌려야 한다.
    dphi = math.atan2(a1z, a1x) - math.atan2(a0z, a0x)
    rot = rg.Transform.Rotation(-dphi, rg.Vector3d.YAxis, mount)

    # 로드의 신장은 **회전시킨 앞끝을 실제 핀 자리로 옮기는 벡터**다.
    # (l1 - l0) 을 축 방향으로 곱하지 않고 이렇게 두면 로드 앞끝이 link2 의 핀에
    # 정확히 붙는 것이 구성상 보장된다 — 그 불변식이 이 리깅의 전부다.
    # 두 점의 y 는 같다(Y축 회전과 j2 회전 모두 y 를 보존하므로) 그래서 이
    # 벡터는 x-z 안에 있다.
    tip_rot = rg.Point3d(pin)
    tip_rot.Transform(rot)
    slide = rg.Transform.Translation(rg.Vector3d(pin_now - tip_rot))

    return m1 * rot, m1 * slide * rot


def balancer_extension_mm(pose_deg, mount=None, pin=None):
    """그 자세에서 피스톤이 나온 길이 (mm). 영각에서 0."""
    by_joint = dict(zip(rb.JOINT_NAMES, rb.joint_frames(pose_deg)))
    mt = _pt(mount, BALANCER_MOUNT_MM)
    pn = _pt(pin, BALANCER_PIN_MM)
    m1 = _mm(by_joint["j1"] * _rest_inverse("j1"))
    m2 = _mm(by_joint["j2"] * _rest_inverse("j2"))
    ok, inv = m1.TryGetInverse()
    rel = (inv * m2) if ok else m2
    q = rg.Point3d(pn)
    q.Transform(rel)
    l0 = math.sqrt((pn.X - mt.X) ** 2 + (pn.Z - mt.Z) ** 2)
    l1 = math.sqrt((q.X - mt.X) ** 2 + (q.Z - mt.Z) ** 2)
    return l1 - l0


def part_transforms(pose_deg, base_plane=None, balancer=None):
    """파트 이름 → mm 월드 변환.

    base_plane 을 주면 로봇 베이스를 그 평면에 놓는다
    (robot.link_lines_mm 과 같은 규약).

    `balancer` 로 `(mount, pin)` 을 주면 그 피벗을 쓴다. 메시를 들고 있는 쪽은
    `balancer_pivots_from_parts()` 결과를 넘기면 원본이 바뀌어도 따라간다.
    """
    frames = rb.joint_frames(pose_deg)
    by_joint = dict(zip(rb.JOINT_NAMES, frames))

    out = {}
    for part, joint in PART_JOINT:
        if joint is None:
            out[part] = rg.Transform.Identity
            continue
        m = by_joint[joint] * _rest_inverse(joint)
        out[part] = _mm(m)

    mount, pin = (balancer if balancer else (None, None))
    mount = _pt(mount, BALANCER_MOUNT_MM)
    pin = _pt(pin, BALANCER_PIN_MM)
    cyl_xf, rod_xf = _balancer_transforms(by_joint, mount, pin)
    out["cylinder"] = cyl_xf
    out["rod"] = rod_xf

    if base_plane is not None:
        b = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, base_plane)
        for k in list(out.keys()):
            out[k] = b * out[k]

    return out


def load_parts(path):
    """`irb6700_parts.3dm` 에서 파트 메시를 읽는다. 이름 → Mesh.

    **문서에 열지 않는다.** File3dm 으로 직접 읽으므로 작업 문서를 오염시키지 않고
    Grasshopper 솔루션 중에도 안전하다.
    """
    f = Rhino.FileIO.File3dm.Read(path)
    if f is None:
        return {}
    out = {}
    for obj in f.Objects:
        g = obj.Geometry
        if not isinstance(g, rg.Mesh):
            continue
        name = obj.Attributes.Name
        if not name:
            li = obj.Attributes.LayerIndex
            if 0 <= li < f.AllLayers.Count:
                name = f.AllLayers[li].Name
        if not name:
            continue
        m = g.DuplicateMesh()
        if name in out:
            out[name].Append(m)
        else:
            out[name] = m
    return out


def posed_meshes(parts, pose_deg, base_plane=None, balancer=None):
    """(이름, 변환된 Mesh 복제본) 목록. 정적 표시·출력용.

    **재생에는 쓰지 말 것.** 프레임마다 메시를 복제하면 12만 면을 매번 만든다.
    재생은 컨듀잇에서 PushModelTransform 으로 원본을 그대로 그린다.
    """
    xfs = part_transforms(pose_deg, base_plane, balancer=balancer)
    out = []
    for name, mesh in parts.items():
        xf = xfs.get(name)
        if xf is None:
            continue
        m = mesh.DuplicateMesh()
        m.Transform(xf)
        out.append((name, m))
    return out


def face_count(parts):
    return sum(m.Faces.Count for m in parts.values())

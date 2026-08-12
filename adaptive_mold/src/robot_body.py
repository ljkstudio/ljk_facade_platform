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
밸런서(cylinder / rod)는 근사다
──────────────────────────────────────────────────────────

실물의 실린더는 link1 에 달려 있고 피스톤은 link2 에 핀으로 물려 미끄러진다.
원본 문서(KINEMATICS.md)는 `cylinder_joint: J2 mimic, multiplier -0.25`,
`piston_joint: prismatic 0.15` 로 적어 두었다.

여기서는 **실린더와 로드를 같은 프레임에 묶어** J2 각도의 -0.25 배만 돌린다.
그래서 **피스톤이 늘어나지 않는다** — 큰 J2 각에서 실물과 다르다.
따로 움직이게 하면 둘이 어긋나 보이므로, 어긋나는 것보다 안 늘어나는 것을 골랐다.
표시 품질 문제이고 기구학·시간 계산에는 영향이 없다. **미검증**(실물 대조 안 됨).
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

# J2 에 종속되는 밸런서 회전 배율 (KINEMATICS.md). 미검증.
BALANCER_MIMIC = -0.25

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


def part_transforms(pose_deg, base_plane=None):
    """파트 이름 → mm 월드 변환.

    base_plane 을 주면 로봇 베이스를 그 평면에 놓는다
    (robot.link_lines_mm 과 같은 규약).
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

    # 밸런서 — link1 을 따라가고 J2 의 일부만 받는다
    j1_m = by_joint["j1"] * _rest_inverse("j1")
    px, py, pz = rb.PIVOTS_M["j2"]
    ang = pose_deg.get("j2", 0.0) * BALANCER_MIMIC * rb.DEG
    tilt = rg.Transform.Rotation(ang, rg.Vector3d.YAxis,
                                 rg.Point3d(px, py, pz))
    bal = _mm(j1_m * tilt)
    for part in BALANCER_PARTS:
        out[part] = bal

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


def posed_meshes(parts, pose_deg, base_plane=None):
    """(이름, 변환된 Mesh 복제본) 목록. 정적 표시·출력용.

    **재생에는 쓰지 말 것.** 프레임마다 메시를 복제하면 12만 면을 매번 만든다.
    재생은 컨듀잇에서 PushModelTransform 으로 원본을 그대로 그린다.
    """
    xfs = part_transforms(pose_deg, base_plane)
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

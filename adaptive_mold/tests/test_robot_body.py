#! python 3
# -*- coding: utf-8 -*-
"""robot_body.py 테스트 — 메시가 관절 프레임에 정확히 얹히는지.

Rhino 환경에서 실행:
    python adaptive_mold/tools/run_tests_via_bridge.py robot_body

**눈으로 보고 판단하지 않는다.** 로봇이 그럴듯하게 접혀 있어도 링크 하나가
잘못된 프레임에 붙어 있으면 큰 각도에서만 어긋나고, 그때는 이미 경로를
믿고 있는 상태다.
"""

import math
import os
import sys

import Rhino.Geometry as rg

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, _SRC)

# 모듈 캐시를 비운다 — Rhino 의 파이썬은 프로세스 수명 동안 캐시하므로 src/ 를
# 고쳐도 옛 모듈이 쓰인다 (test_playback.py 의 같은 주석 참조).
_norm = os.path.normcase(_SRC)
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb          # noqa: E402
import robot_body as rbb    # noqa: E402


PARTS_3DM = os.path.normpath(os.path.join(
    HERE, "..", "grasshopper", "irb6700_parts.3dm"))

TOL = 1e-6          # mm
TOL_XF = 1e-9


def _pose(**kw):
    p = dict((j, 0.0) for j in rb.JOINT_NAMES)
    p.update(kw)
    return p


def _xf_max_diff(a, b):
    return max(abs(a[i, j] - b[i, j]) for i in range(4) for j in range(4))


# ── 변환 자체 ───────────────────────────────────────────

def test_zero_pose_is_identity():
    """영각에서 모든 파트 변환이 항등이어야 한다.

    이것이 '메시가 영각 자세로 제자리에 있다'는 전제의 검증이다.
    깨지면 임포트 좌표계가 틀린 것이다.
    """
    xfs = rbb.part_transforms(_pose())
    for name, xf in xfs.items():
        d = _xf_max_diff(xf, rg.Transform.Identity)
        assert d < TOL_XF, "{}: 항등이 아니다 (최대차 {:.3e})".format(name, d)
    assert len(xfs) == 9, len(xfs)
    print("PASS: test_zero_pose_is_identity")


def test_pivot_invariant():
    """M_j 로 영각 피벗을 옮기면 그 자세의 피벗 위치가 나와야 한다.

    부동소수 오차 말고는 어긋날 여지가 없는 불변식이다.
    링크-관절 매핑이 하나라도 밀려 있으면 여기서 깨진다.
    """
    pose = _pose(j1=37.0, j2=21.0, j3=-44.0, j4=15.0, j5=63.0, j6=-88.0)
    xfs = rbb.part_transforms(pose)
    frames = rb.joint_frames(pose)

    for (part, joint), frame in zip(rbb.PART_JOINT[1:], frames):
        px, py, pz = rb.PIVOTS_M[joint]
        p = rg.Point3d(px * rb.MM, py * rb.MM, pz * rb.MM)
        p.Transform(xfs[part])

        q = rg.Point3d(0.0, 0.0, 0.0)
        q.Transform(frame)
        q = rg.Point3d(q.X * rb.MM, q.Y * rb.MM, q.Z * rb.MM)

        d = p.DistanceTo(q)
        assert d < TOL, "{}({}) 피벗 불일치 {:.6f} mm".format(part, joint, d)
    print("PASS: test_pivot_invariant")


def test_j1_rotates_about_z():
    """j1=90 이면 파트가 Z축 기준 90도 돈다 — (x,y) -> (-y,x)."""
    xfs = rbb.part_transforms(_pose(j1=90.0))
    p = rg.Point3d(1000.0, 0.0, 500.0)
    q = rg.Point3d(p)
    q.Transform(xfs["link6"])
    assert abs(q.X - 0.0) < TOL, q
    assert abs(q.Y - 1000.0) < TOL, q
    assert abs(q.Z - 500.0) < TOL, q
    print("PASS: test_j1_rotates_about_z")


def test_base_is_fixed():
    """베이스는 어떤 자세에서도 움직이지 않는다."""
    for pose in (_pose(), _pose(j1=170.0, j2=80.0), _pose(j5=-130.0)):
        d = _xf_max_diff(rbb.part_transforms(pose)["base"],
                         rg.Transform.Identity)
        assert d < TOL_XF, d
    print("PASS: test_base_is_fixed")


def test_agrees_with_link_lines():
    """실물 프레임과 스틱 피겨가 같은 자세여야 한다 — 두 코드 경로 대조.

    `link_lines_mm` 은 미터 좌표를 1000배 한 뒤 base_plane 을 걸고,
    `part_transforms` 는 변환을 켤레변환한 뒤 base_plane 을 건다. 결과가 같아야
    하지만 **경로가 다르므로 한쪽만 고치면 조용히 어긋난다** — 화면으로는
    로봇이 그럴듯하게 서 있고 계산된 위치와 다른 곳에 그려진다.

    기울고 옮겨진 베이스로 확인한다. 축이 정렬된 평면은 규약 실수를 숨긴다.
    """
    pose = _pose(j1=-52.0, j2=31.0, j3=-63.0, j4=-24.0, j5=77.0, j6=140.0)
    pl = rg.Plane(rg.Point3d(-1400.0, 500.0, 120.0),
                  rg.Vector3d(1.0, 0.35, 0.0), rg.Vector3d(-0.2, 1.0, 0.15))

    lines_ = rb.link_lines_mm(pose, base_plane=pl)
    xfs = rbb.part_transforms(pose, base_plane=pl)

    # link_lines_mm 의 점 순서: [베이스원점, j1..j6 피벗, TCP]
    for i, (part, joint) in enumerate(rbb.PART_JOINT[1:]):
        px, py, pz = rb.PIVOTS_M[joint]
        p = rg.Point3d(px * rb.MM, py * rb.MM, pz * rb.MM)
        p.Transform(xfs[part])
        q = lines_[i + 1].From          # i+1 번째 점 = 그 관절의 피벗
        d = p.DistanceTo(q)
        assert d < 1e-6, "{} 불일치 {:.6f} mm".format(part, d)
    print("PASS: test_agrees_with_link_lines")


def test_base_plane_offset():
    """base_plane 을 주면 전부 그만큼 옮겨진다."""
    pl = rg.Plane(rg.Point3d(-1400.0, 500.0, 0.0),
                  rg.Vector3d.XAxis, rg.Vector3d.YAxis)
    xfs = rbb.part_transforms(_pose(), base_plane=pl)
    p = rg.Point3d(0.0, 0.0, 0.0)
    p.Transform(xfs["link3"])
    assert p.DistanceTo(rg.Point3d(-1400.0, 500.0, 0.0)) < TOL, p
    print("PASS: test_base_plane_offset")


def test_balancer_follows_j1_only_partly():
    """밸런서는 j1 을 그대로 따르고 j2 는 배율만큼만 받는다."""
    x1 = rbb.part_transforms(_pose(j1=90.0))
    a = rg.Point3d(0.0, 0.0, 1000.0)
    b = rg.Point3d(a)
    b.Transform(x1["cylinder"])
    c = rg.Point3d(a)
    c.Transform(x1["link1"])
    assert b.DistanceTo(c) < TOL, (b, c)      # j1 만 있으면 link1 과 같다

    x2 = rbb.part_transforms(_pose(j2=40.0))
    d = rg.Point3d(0.0, 0.0, 1000.0)
    d.Transform(x2["cylinder"])
    e = rg.Point3d(0.0, 0.0, 1000.0)
    e.Transform(x2["link2"])
    assert d.DistanceTo(e) > 1.0, "j2 를 그대로 받고 있다"
    assert rbb.BALANCER_MIMIC == -0.25
    print("PASS: test_balancer_follows_j1_only_partly")


def test_cylinder_and_rod_share_frame():
    """실린더와 로드는 같은 프레임이다 (어긋나 보이지 않게)."""
    xfs = rbb.part_transforms(_pose(j2=55.0, j1=-30.0))
    assert _xf_max_diff(xfs["cylinder"], xfs["rod"]) < TOL_XF
    print("PASS: test_cylinder_and_rod_share_frame")


# ── 파일 ────────────────────────────────────────────────

def test_parts_file_loads():
    """9개 파트가 이름으로 다 읽혀야 한다."""
    assert os.path.isfile(PARTS_3DM), PARTS_3DM
    parts = rbb.load_parts(PARTS_3DM)
    missing = [n for n in rbb.PART_NAMES if n not in parts]
    assert not missing, "빠진 파트: {}".format(missing)
    assert len(parts) == 9, sorted(parts.keys())
    for n, m in parts.items():
        assert m.Faces.Count > 100, "{} 면 {}개".format(n, m.Faces.Count)
    print("PASS: test_parts_file_loads")


def test_parts_are_in_mm_and_upright():
    """단위가 mm 이고 로봇이 바닥에 서 있어야 한다.

    임포트 축 보정이 풀리면 여기서 걸린다 — 그때는 z 가 아니라 y 로 뻗는다.
    """
    parts = rbb.load_parts(PARTS_3DM)
    zmin = min(m.GetBoundingBox(True).Min.Z for m in parts.values())
    zmax = max(m.GetBoundingBox(True).Max.Z for m in parts.values())
    assert -2.0 < zmin < 2.0, "바닥이 z=0 이 아니다: {:.1f}".format(zmin)
    assert 2000.0 < zmax < 2500.0, "높이가 mm 가 아니다: {:.1f}".format(zmax)

    # J6 피벗은 link6 안에 있어야 한다 (임포트 도구의 판정 기준과 같다)
    bb = parts["link6"].GetBoundingBox(True)
    px, py, pz = rb.PIVOTS_M["j6"]
    p = rg.Point3d(px * rb.MM, py * rb.MM, pz * rb.MM)
    assert bb.Contains(p), "J6 피벗이 link6 밖이다: {} vs {}".format(p, bb)
    print("PASS: test_parts_are_in_mm_and_upright")


def test_posed_meshes_move():
    """posed_meshes 가 실제로 옮긴 복제본을 준다 (원본은 그대로)."""
    parts = rbb.load_parts(PARTS_3DM)
    before = parts["link6"].GetBoundingBox(True).Center

    out = dict(rbb.posed_meshes(parts, _pose(j1=90.0)))
    after = out["link6"].GetBoundingBox(True).Center
    assert before.DistanceTo(after) > 100.0, (before, after)

    # 원본이 변형되지 않았는지 — 프레임마다 복제하는 구조라 여기가 새면 누적된다
    still = parts["link6"].GetBoundingBox(True).Center
    assert still.DistanceTo(before) < TOL, (before, still)
    print("PASS: test_posed_meshes_move")


def test_face_budget():
    """표시용 면수가 재생 예산 안에 있어야 한다."""
    parts = rbb.load_parts(PARTS_3DM)
    n = rbb.face_count(parts)
    assert n < 200000, "면 {}개 — 재생이 늘어진다".format(n)
    print("PASS: test_face_budget ({}면)".format(n))


TESTS = [
    test_zero_pose_is_identity,
    test_pivot_invariant,
    test_j1_rotates_about_z,
    test_agrees_with_link_lines,
    test_base_is_fixed,
    test_base_plane_offset,
    test_balancer_follows_j1_only_partly,
    test_cylinder_and_rod_share_frame,
    test_parts_file_loads,
    test_parts_are_in_mm_and_upright,
    test_posed_meshes_move,
    test_face_budget,
]


def run_all():
    log = []
    ok = 0
    bad = 0
    for fn in TESTS:
        try:
            fn()
            log.append("PASS: " + fn.__name__)
            ok += 1
        except Exception as ex:
            log.append("FAIL: {} -> {}: {}".format(
                fn.__name__, type(ex).__name__, ex))
            bad += 1
    log.append("")
    log.append("{}개 통과 / {}개 실패".format(ok, bad))
    return ok, bad, log


if __name__ == "__main__":
    _ok, _bad, _log = run_all()
    _out = os.path.join(HERE, "_robot_body_log.txt")
    with open(_out, "w", encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

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


def test_balancer_mount_never_moves():
    """실린더 마운트는 link1 에 고정이다 — j2 로는 절대 움직이지 않는다.

    **옛 구현이 여기서 깨졌다**(j2=78 에서 295 mm 이동). 프레임에 볼트로
    고정된 점이 움직이면 눈에 그대로 보인다.
    """
    mount = rg.Point3d(*rbb.BALANCER_MOUNT_MM)
    for j2 in (-17.0, 0.0, 30.0, 78.0):
        xfs = rbb.part_transforms(_pose(j2=j2))
        q = rg.Point3d(mount)
        q.Transform(xfs["cylinder"])
        assert mount.DistanceTo(q) < TOL, (j2, mount, q)
    print("PASS: test_balancer_mount_never_moves")


def test_balancer_mount_follows_j1():
    """j1 은 그대로 따른다 — 캐러셀에 실려 있으므로."""
    mount = rg.Point3d(*rbb.BALANCER_MOUNT_MM)
    xfs = rbb.part_transforms(_pose(j1=90.0))
    a = rg.Point3d(mount)
    a.Transform(xfs["cylinder"])
    b = rg.Point3d(mount)
    b.Transform(xfs["link1"])
    assert a.DistanceTo(b) < TOL, (a, b)
    assert a.DistanceTo(mount) > 100.0, "j1 을 안 따라간다"
    print("PASS: test_balancer_mount_follows_j1")


def test_rod_tip_stays_pinned_to_link2():
    """로드 앞끝은 link2 의 핀 자리에 **정확히** 붙어 있어야 한다.

    이것이 이 리깅의 핵심 불변식이다 — 부호가 틀리면 여기서 바로 깨진다.
    옛 구현은 j2=78 에서 232 mm 벌어졌다.
    """
    pin = rg.Point3d(*rbb.BALANCER_PIN_MM)
    for j1 in (0.0, -30.0, 120.0):
        for j2 in (-17.0, 0.0, 25.0, 52.9, 78.0):
            xfs = rbb.part_transforms(_pose(j1=j1, j2=j2))
            a = rg.Point3d(pin)
            a.Transform(xfs["rod"])
            b = rg.Point3d(pin)
            b.Transform(xfs["link2"])
            assert a.DistanceTo(b) < 1e-3, (j1, j2, a.DistanceTo(b))
    print("PASS: test_rod_tip_stays_pinned_to_link2")


def test_cylinder_and_rod_stay_collinear():
    """실린더와 로드는 한 축 위에 있어야 한다 — 어긋나 보이면 안 된다.

    이제 두 변환이 다르다(로드가 미끄러진다). 같은지 보는 대신 **축이 같은지**
    본다.

    **정확히 1 이 아니다.** 유도한 밸런서 축이 x-z 평면에서 0.43° 벗어나 있고
    (mount y -195.88 / pin y -190.56, 715 mm 에 5.3 mm 드리프트), 신장은 y 를
    보존하는 x-z 안에서 일어난다. 그래서 최대 신장에서 약 1 mm 어긋난다 —
    보이지 않는 크기이고, 대신 로드 앞끝이 핀에 **정확히** 붙는다.
    0.43° 를 0 으로 가정해 축을 억지로 맞추면 그 보장이 깨진다.
    """
    mount = rg.Point3d(*rbb.BALANCER_MOUNT_MM)
    pin = rg.Point3d(*rbb.BALANCER_PIN_MM)
    for j2 in (-17.0, 30.0, 78.0):
        xfs = rbb.part_transforms(_pose(j1=-30.0, j2=j2))
        m = rg.Point3d(mount)
        m.Transform(xfs["cylinder"])
        p = rg.Point3d(pin)
        p.Transform(xfs["rod"])
        # 로드를 회전만 시킨 점(신장 전)도 같은 축 위에 있어야 한다
        r0 = rg.Point3d(mount)
        r0.Transform(xfs["rod"])
        v1 = rg.Vector3d(p - m)
        v2 = rg.Vector3d(r0 - m)
        if v2.Length < 1e-9:
            continue
        v1.Unitize()
        v2.Unitize()
        # 0.43° 면외 기울기 = dot 0.99997. 1e-4 는 그것을 담고
        # 진짜 어긋남(수 도)은 잡는 폭이다.
        assert abs(v1 * v2 - 1.0) < 1e-4, (j2, v1 * v2)
    print("PASS: test_cylinder_and_rod_stay_collinear")


def test_extension_is_zero_at_rest_and_grows_with_j2():
    """영각에서 0, j2 가 커지면 늘어난다. 문서 행정(150 mm) 안이어야 한다."""
    assert abs(rbb.balancer_extension_mm(_pose())) < 1e-6
    prev = None
    for j2 in (0.0, 20.0, 40.0, 60.0, 78.0):
        e = rbb.balancer_extension_mm(_pose(j2=j2))
        assert e >= -1e-6, (j2, e)
        if prev is not None:
            assert e > prev, "j2 가 커졌는데 안 늘어난다: {} -> {}".format(prev, e)
        prev = e
    assert prev < 150.0, "행정 초과 {:.1f} mm".format(prev)
    assert prev > 100.0, "너무 조금 늘어난다 {:.1f} mm".format(prev)
    print("PASS: test_extension_is_zero_at_rest_and_grows_with_j2 "
          "(최대 {:.1f}mm)".format(prev))


def test_extension_does_not_depend_on_j1():
    """j1 은 밸런서 삼각형을 통째로 돌릴 뿐 신장을 바꾸지 않는다."""
    a = rbb.balancer_extension_mm(_pose(j1=0.0, j2=50.0))
    b = rbb.balancer_extension_mm(_pose(j1=137.0, j2=50.0))
    assert abs(a - b) < 1e-6, (a, b)
    print("PASS: test_extension_does_not_depend_on_j1")


def test_pivots_derived_from_mesh_match_constants():
    """상수는 형상에서 유도한 값이다 — 원본이 바뀌면 여기가 먼저 깨진다."""
    parts = rbb.load_parts(PARTS_3DM)
    mount, pin = rbb.balancer_pivots_from_parts(parts)
    assert mount is not None and pin is not None
    m0 = rg.Point3d(*rbb.BALANCER_MOUNT_MM)
    p0 = rg.Point3d(*rbb.BALANCER_PIN_MM)
    assert mount.DistanceTo(m0) < 0.5, (mount, m0)
    assert pin.DistanceTo(p0) < 0.5, (pin, p0)
    print("PASS: test_pivots_derived_from_mesh_match_constants "
          "(mount {:.2f}mm / pin {:.2f}mm 차이)".format(
              mount.DistanceTo(m0), pin.DistanceTo(p0)))


def test_derived_pivots_can_be_passed_in():
    """메시를 들고 있는 쪽은 유도값을 넘길 수 있다 (하드코딩에 묶이지 않는다)."""
    parts = rbb.load_parts(PARTS_3DM)
    bal = rbb.balancer_pivots_from_parts(parts)
    xfs = rbb.part_transforms(_pose(j2=60.0), balancer=bal)
    a = rg.Point3d(bal[1])
    a.Transform(xfs["rod"])
    b = rg.Point3d(bal[1])
    b.Transform(xfs["link2"])
    assert a.DistanceTo(b) < 1e-3, (a, b)
    print("PASS: test_derived_pivots_can_be_passed_in")


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
    test_balancer_mount_never_moves,
    test_balancer_mount_follows_j1,
    test_rod_tip_stays_pinned_to_link2,
    test_cylinder_and_rod_stay_collinear,
    test_extension_is_zero_at_rest_and_grows_with_j2,
    test_extension_does_not_depend_on_j1,
    test_pivots_derived_from_mesh_match_constants,
    test_derived_pivots_can_be_passed_in,
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

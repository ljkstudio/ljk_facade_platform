#! python 3
# -*- coding: utf-8 -*-
"""collision.py 테스트 — 높이장 조회와 포즈 스크리닝.

    python adaptive_mold/tools/run_tests_via_bridge.py collision

**부호와 '밖' 처리가 요점이다.** 침투를 음수로 잡거나 발자국 밖을 0 으로
처리하면, 팔이 몰드 옆을 지나갈 때마다 거짓 경보가 나거나 반대로 파고들어도
조용하다.
"""

import os
import sys

import Rhino.Geometry as rg

HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.normpath(os.path.join(HERE, "..", "src"))
sys.path.insert(0, _SRC)

_norm = os.path.normcase(_SRC)
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb            # noqa: E402
import robot_body as rbb      # noqa: E402
import collision as col       # noqa: E402


PARTS_3DM = os.path.normpath(os.path.join(
    HERE, "..", "grasshopper", "irb6700_parts.3dm"))


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def _pose(**kw):
    p = dict((j, 0.0) for j in rb.JOINT_NAMES)
    p.update(kw)
    return p


def _flat_grid(z=200.0, n=3, span=1000.0):
    """z 가 일정한 n x n 격자 (0,0) ~ (span, span)."""
    step = span / (n - 1)
    return [rg.Point3d(i * step, j * step, z)
            for j in range(n) for i in range(n)]


# ── 높이장 ──────────────────────────────────────────────

def test_flat_field_reads_back():
    hf = col.Heightfield.from_grid_points(_flat_grid(200.0), 3, 3)
    assert hf is not None
    for x, y in ((0, 0), (250, 700), (1000, 1000), (500, 500)):
        assert close(hf.z_at(x, y), 200.0), (x, y, hf.z_at(x, y))
    print("PASS: test_flat_field_reads_back")


def test_offset_raises_field():
    """offset 은 몰드를 위로 올린다 — 보수적으로 보게."""
    hf = col.Heightfield.from_grid_points(_flat_grid(200.0), 3, 3, offset=28.0)
    assert close(hf.z_at(500, 500), 228.0), hf.z_at(500, 500)
    print("PASS: test_offset_raises_field")


def test_bilinear_interpolates_slope():
    """x 방향으로 기울어진 면에서 중간값이 선형이어야 한다."""
    pts = []
    for j in range(3):
        for i in range(3):
            pts.append(rg.Point3d(i * 500.0, j * 500.0, i * 100.0))
    hf = col.Heightfield.from_grid_points(pts, 3, 3)
    assert close(hf.z_at(0, 0), 0.0), hf.z_at(0, 0)
    assert close(hf.z_at(250, 0), 50.0), hf.z_at(250, 0)
    assert close(hf.z_at(1000, 750), 200.0), hf.z_at(1000, 750)
    print("PASS: test_bilinear_interpolates_slope")


def test_outside_footprint_is_none():
    """발자국 밖은 None — 0 이 아니다. 0 이면 몰드 높이 0 으로 오해한다."""
    hf = col.Heightfield.from_grid_points(_flat_grid(200.0), 3, 3)
    for x, y in ((-1.0, 500.0), (1001.0, 500.0), (500.0, -1.0),
                 (500.0, 1001.0)):
        assert hf.z_at(x, y) is None, (x, y, hf.z_at(x, y))
    print("PASS: test_outside_footprint_is_none")


def test_penetration_sign():
    """면 아래가 양수, 위가 음수, 밖은 아주 큰 음수."""
    hf = col.Heightfield.from_grid_points(_flat_grid(200.0), 3, 3)
    assert close(hf.penetration(rg.Point3d(500, 500, 150)), 50.0)
    assert close(hf.penetration(rg.Point3d(500, 500, 260)), -60.0)
    assert hf.penetration(rg.Point3d(-500, 500, 0)) < -1.0e8
    print("PASS: test_penetration_sign")


def test_from_surface_matches_flat_plane():
    """평면 곡면에서 만든 높이장이 그 z 를 돌려줘야 한다."""
    pl = rg.Plane(rg.Point3d(0, 0, 300), rg.Vector3d.ZAxis)
    srf = rg.PlaneSurface(pl, rg.Interval(0, 1000), rg.Interval(0, 1000))
    hf = col.Heightfield.from_surface(srf, nx=10, ny=10)
    assert hf is not None
    assert close(hf.z_at(500, 500), 300.0, 1e-3), hf.z_at(500, 500)
    assert close(hf.z_at(100, 900), 300.0, 1e-3), hf.z_at(100, 900)
    print("PASS: test_from_surface_matches_flat_plane")


def test_from_surface_none_input():
    assert col.Heightfield.from_surface(None) is None
    assert col.Heightfield.from_grid_points([], 3, 3) is None
    print("PASS: test_from_surface_none_input")


# ── 표본점 ──────────────────────────────────────────────

def test_sample_points_excludes_base():
    """베이스는 안 본다 — 안 움직이고, 겹침은 base_overlap 이 본다."""
    parts = rbb.load_parts(PARTS_3DM)
    s = col.sample_points(parts, per_part=40)
    assert "base" not in s, sorted(s.keys())
    assert len(s) == 8, sorted(s.keys())
    for name, pts in s.items():
        assert 30 <= len(pts) <= 60, (name, len(pts))
    print("PASS: test_sample_points_excludes_base ({}점)".format(
        sum(len(v) for v in s.values())))


def test_sample_points_spread_out():
    """표본이 파트 전체에 퍼져 있어야 한다 — 한쪽에 뭉치면 못 잡는다."""
    parts = rbb.load_parts(PARTS_3DM)
    s = col.sample_points(parts, per_part=60)
    for name in ("link4", "link2"):
        pts = s[name]
        bb_s = rg.BoundingBox(pts)
        bb_m = parts[name].GetBoundingBox(True)
        for axis in ("X", "Y", "Z"):
            span_s = getattr(bb_s.Max, axis) - getattr(bb_s.Min, axis)
            span_m = getattr(bb_m.Max, axis) - getattr(bb_m.Min, axis)
            if span_m < 1.0:
                continue
            assert span_s > span_m * 0.6, (name, axis, span_s, span_m)
    print("PASS: test_sample_points_spread_out")


# ── 포즈 판정 ───────────────────────────────────────────

def _setup():
    parts = rbb.load_parts(PARTS_3DM)
    samples = col.sample_points(parts, per_part=60)
    return parts, samples


def test_pose_above_field_is_clear():
    """몰드를 로봇 발밑 낮은 곳에 두면 팔이 안 닿는다."""
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 100.0)
         for y in (2000.0, 2500.0, 3000.0) for x in (2000.0, 2500.0, 3000.0)],
        3, 3)
    pen, who = col.check_pose(_pose(j2=20.0), samples, hf, margin=0.0)
    assert pen < 0.0, (pen, who)
    print("PASS: test_pose_above_field_is_clear")


def test_pose_inside_field_is_hit():
    """로봇 위로 높은 천장을 두면 팔이 반드시 걸린다 — 부호 확인용."""
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 5000.0)
         for y in (-3000.0, 0.0, 3000.0) for x in (-3000.0, 0.0, 3000.0)],
        3, 3)
    pen, who = col.check_pose(_pose(), samples, hf, margin=0.0)
    assert pen > 1000.0, (pen, who)
    assert who is not None
    print("PASS: test_pose_inside_field_is_hit ({} {:.0f}mm)".format(who, pen))


def test_margin_shifts_verdict():
    """margin 은 몰드를 두껍게 본다 — 통과가 실패로 바뀔 수 있다."""
    _parts, samples = _setup()
    # 팔 아래 살짝 낮은 면
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 1000.0)
         for y in (-2000.0, 0.0, 2000.0) for x in (0.0, 1000.0, 2000.0)],
        3, 3)
    a, _ = col.check_pose(_pose(), samples, hf, margin=0.0)
    b, _ = col.check_pose(_pose(), samples, hf, margin=500.0)
    assert close(b - a, 500.0, 1e-6), (a, b)
    print("PASS: test_margin_shifts_verdict")


def test_scan_and_summary():
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 5000.0)
         for y in (-3000.0, 0.0, 3000.0) for x in (-3000.0, 0.0, 3000.0)],
        3, 3)
    poses = [_pose(), _pose(j2=10.0), _pose(j2=20.0), _pose(j2=30.0)]
    pens, whos = col.scan_poses(poses, samples, hf, margin=0.0)
    assert len(pens) == 4 and len(whos) == 4, (len(pens), len(whos))
    s = col.summarize(pens, whos, step=1, total=4)
    assert s["hits"] == 4, s
    assert s["checked"] == 4, s
    assert s["worst"] > 1000.0, s
    assert sum(s["per_part"].values()) == 4, s
    print("PASS: test_scan_and_summary")


def test_min_clear_is_margin_independent():
    """최소 여유는 margin 을 어떻게 잡아도 같아야 한다 — 형상이 정하는 값이다.

    걸림 개수는 margin 에 따라 달라지지만 min_clear 는 안 달라진다.
    이게 성립해야 "얼마나 아슬아슬한가"를 그 값으로 읽을 수 있다.
    """
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 1000.0)
         for y in (-2000.0, 0.0, 2000.0) for x in (0.0, 1000.0, 2000.0)],
        3, 3)
    poses = [_pose(), _pose(j2=10.0)]

    vals = []
    for m in (0.0, 200.0, 900.0):
        pens, whos = col.scan_poses(poses, samples, hf, margin=m)
        s = col.summarize(pens, whos, margin=m)
        vals.append(s["min_clear"])
    for v in vals[1:]:
        assert close(v, vals[0], 1e-6), vals
    print("PASS: test_min_clear_is_margin_independent ({:.0f}mm)".format(
        vals[0]))


def test_min_clear_none_when_all_outside():
    """전부 발자국 밖이면 판정 불가 — 0 이나 큰 수로 속이지 않는다."""
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(
        [rg.Point3d(x, y, 0.0)
         for y in (9000.0, 9500.0, 10000.0)
         for x in (9000.0, 9500.0, 10000.0)], 3, 3)
    pens, whos = col.scan_poses([_pose()], samples, hf)
    s = col.summarize(pens, whos, margin=30.0)
    assert s["min_clear"] is None, s["min_clear"]
    assert s["hits"] == 0, s
    print("PASS: test_min_clear_none_when_all_outside")


def test_scan_step_reports_what_it_skipped():
    """step 을 쓰면 검사한 개수와 전체 개수가 다르게 보고돼야 한다."""
    _parts, samples = _setup()
    hf = col.Heightfield.from_grid_points(_flat_grid(0.0), 3, 3)
    poses = [_pose(j1=float(i)) for i in range(10)]
    pens, whos = col.scan_poses(poses, samples, hf, step=5)
    s = col.summarize(pens, whos, step=5, total=len(poses))
    assert s["checked"] == 2, s
    assert s["total"] == 10, s
    assert s["step"] == 5, s
    print("PASS: test_scan_step_reports_what_it_skipped")


def test_no_field_means_no_verdict():
    """높이장이 없으면 '통과'가 아니라 판정 불가여야 한다."""
    _parts, samples = _setup()
    pen, who = col.check_pose(_pose(), samples, None)
    assert pen < -1.0e8, pen
    assert who is None
    print("PASS: test_no_field_means_no_verdict")


TESTS = [
    test_flat_field_reads_back,
    test_offset_raises_field,
    test_bilinear_interpolates_slope,
    test_outside_footprint_is_none,
    test_penetration_sign,
    test_from_surface_matches_flat_plane,
    test_from_surface_none_input,
    test_sample_points_excludes_base,
    test_sample_points_spread_out,
    test_pose_above_field_is_clear,
    test_pose_inside_field_is_hit,
    test_margin_shifts_verdict,
    test_min_clear_is_margin_independent,
    test_min_clear_none_when_all_outside,
    test_scan_and_summary,
    test_scan_step_reports_what_it_skipped,
    test_no_field_means_no_verdict,
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
    with open(os.path.join(HERE, "_collision_log.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

#! python 3
# -*- coding: utf-8 -*-
"""base_search.py 테스트 — 격자·제약 분류·순위·지도.

    python adaptive_mold/tools/run_tests_via_bridge.py base_search

IK 평가 자체는 tools/search_base.py 실행으로 검증한다. 여기서는 **판정 논리**를
고정한다 — 어느 제약이 먼저 걸리는지, 동점을 어떻게 깨는지, 통과한 칸과
기각된 칸이 지도에서 구분되는지.
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
import base_search as bs      # noqa: E402


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def res(x, y, **kw):
    """평가 결과 흉내. evaluate() 를 부르지 않고 판정 논리만 본다."""
    r = {"origin": rg.Point3d(x, y, 0.0), "ok": False, "reason": "",
         "fails": 0, "err_max": 0.5, "j_margin": 20.0, "j_worst": "j2",
         "min_override": 0.3, "clear": 60.0, "flips": 0, "overlap": -500.0}
    r.update(kw)
    r["reason"] = bs.classify(r)
    r["ok"] = (r["reason"] == "")
    return r


# ── 1. 격자 ─────────────────────────────────────────────

def test_grid_includes_both_ends():
    pts, xs, ys = bs.grid_points(-1000.0, -600.0, 0.0, 400.0, step=200.0)
    assert xs == [-1000.0, -800.0, -600.0], xs
    assert ys == [0.0, 200.0, 400.0], ys
    assert len(pts) == 9, len(pts)


def test_grid_handles_reversed_bounds():
    _, xs, _ = bs.grid_points(-600.0, -1000.0, 0.0, 0.0, step=200.0)
    assert xs == [-1000.0, -800.0, -600.0], xs


def test_grid_appends_ragged_end():
    """간격으로 딱 나뉘지 않으면 끝점을 따로 붙인다 — 경계를 잃지 않는다."""
    _, xs, _ = bs.grid_points(0.0, 500.0, 0.0, 0.0, step=200.0)
    assert xs[-1] == 500.0, xs
    assert 400.0 in xs, xs


def test_polar_ring_lands_on_the_circle():
    c = rg.Point3d(500.0, 500.0, 0.0)
    pts, angs, radii = bs.polar_points(c, 1000.0, 1000.0, 100.0,
                                       0.0, 270.0, 90.0)
    assert radii == [1000.0], radii
    assert angs == [0.0, 90.0, 180.0, 270.0], angs
    assert len(pts) == 4, pts
    for x, y, a, r in pts:
        d = ((x - c.X) ** 2 + (y - c.Y) ** 2) ** 0.5
        assert close(d, 1000.0, 1e-6), (x, y, d)
    # 0deg 은 +x 방향이다
    assert close(pts[0][0], 1500.0, 1e-6), pts[0]
    assert close(pts[0][1], 500.0, 1e-6), pts[0]


def test_polar_carries_cell_coords():
    """지도의 축이 각도·반경이 되도록 각 점이 자기 칸을 들고 있어야 한다."""
    c = rg.Point3d(0.0, 0.0, 0.0)
    pts, _, _ = bs.polar_points(c, 1000.0, 1200.0, 200.0, 0.0, 90.0, 90.0)
    cells = sorted((a, r) for _x, _y, a, r in pts)
    assert cells == [(0.0, 1000.0), (0.0, 1200.0),
                     (90.0, 1000.0), (90.0, 1200.0)], cells


def test_polar_rejects_zero_step():
    pts, a, r = bs.polar_points(rg.Point3d(0, 0, 0), 1000.0, 2000.0, 0.0)
    assert pts == [] and a == [] and r == [], (pts, a, r)


def test_map_uses_cell_when_present():
    """극좌표 결과는 원점 x·y 가 아니라 (각도, 반경) 칸으로 찍혀야 한다."""
    a = res(9999.0, 9999.0, j_margin=12.0)
    a["cell"] = (0.0, 1800.0)
    b = res(-9999.0, -9999.0, j_margin=6.0)
    b["cell"] = (90.0, 1800.0)
    txt = bs.render_map([a, b], [0.0, 90.0], [1800.0], axes=("각도", "반경"))
    assert "각도" in txt and "반경" in txt, txt
    assert "12" in txt and " 6" in txt, txt


def test_grid_rejects_zero_step():
    pts, xs, ys = bs.grid_points(0.0, 100.0, 0.0, 100.0, step=0.0)
    assert pts == [] and xs == [] and ys == [], (pts, xs, ys)


# ── 2. 제약 분류 — 순서가 중요하다 ──────────────────────

def test_clean_candidate_passes():
    r = res(-1400.0, 500.0)
    assert r["ok"], r["reason"]


def test_overlap_rejected():
    r = res(0.0, 0.0, overlap=120.0)
    assert not r["ok"]
    assert "겹침" in r["reason"], r["reason"]


def test_reach_failure_rejected():
    r = res(-2000.0, 0.0, fails=7)
    assert "도달 실패 7개" in r["reason"], r["reason"]


def test_negative_joint_margin_rejected():
    r = res(-700.0, 0.0, j_margin=-3.5, j_worst="j2")
    assert "j2" in r["reason"] and "3.5" in r["reason"], r["reason"]


def test_rated_speed_excess_rejected():
    r = res(-1400.0, 0.0, min_override=1.4)
    assert "정격 속도 140% 필요" in r["reason"], r["reason"]


def test_collision_rejected():
    r = res(-1400.0, 0.0, hits=12)
    assert "팔 간섭 12포즈" in r["reason"], r["reason"]


def test_overlap_wins_over_reach():
    """값싸고 확실한 이유를 먼저 보고한다 — 겹치면 IK 결과는 의미가 없다."""
    r = res(0.0, 0.0, overlap=50.0, fails=99)
    assert "겹침" in r["reason"], r["reason"]


def test_tight_margin_is_not_a_rejection():
    """여유 7.1deg 는 통과다. 경고와 기각을 섞으면 쓸 자리가 사라진다."""
    r = res(-1400.0, 500.0, j_margin=7.1)
    assert r["ok"], r["reason"]


def test_zero_margin_is_not_rejected():
    """정확히 0 은 한계에 닿았지만 넘지는 않았다 — 음수만 기각한다."""
    r = res(-1400.0, 500.0, j_margin=0.0)
    assert r["ok"], r["reason"]


# ── 3. 순위 ─────────────────────────────────────────────

def test_rank_prefers_larger_joint_margin():
    rs = [res(-1000.0, 0.0, j_margin=5.0),
          res(-1200.0, 0.0, j_margin=18.0),
          res(-1400.0, 0.0, j_margin=11.0)]
    best = bs.rank(rs)
    assert [r["j_margin"] for r in best] == [18.0, 11.0, 5.0], best


def test_rank_drops_infeasible():
    rs = [res(-1000.0, 0.0, j_margin=30.0, fails=3),
          res(-1200.0, 0.0, j_margin=8.0)]
    best = bs.rank(rs)
    assert len(best) == 1, best
    assert close(best[0]["j_margin"], 8.0), best


def test_rank_tie_breaks_on_clearance():
    rs = [res(-1000.0, 0.0, j_margin=10.0, clear=40.0),
          res(-1200.0, 0.0, j_margin=10.0, clear=90.0)]
    best = bs.rank(rs)
    assert close(best[0]["clear"], 90.0), best


def test_rank_tie_breaks_on_override_last():
    rs = [res(-1000.0, 0.0, j_margin=10.0, clear=50.0, min_override=0.8),
          res(-1200.0, 0.0, j_margin=10.0, clear=50.0, min_override=0.2)]
    best = bs.rank(rs)
    assert close(best[0]["min_override"], 0.2), best


def test_unchecked_collision_does_not_beat_measured():
    """간섭을 안 재고 통과한 것이 실측된 것보다 앞서면 안 된다."""
    a = res(-1000.0, 0.0, j_margin=10.0, clear=None)
    b = res(-1200.0, 0.0, j_margin=10.0, clear=10.0)
    best = bs.rank([a, b])
    assert best[0]["clear"] == 10.0, best


# ── 4. 지도 ─────────────────────────────────────────────

def test_map_marks_each_rejection_differently():
    rs = [res(-1000.0, 0.0, overlap=10.0),
          res(-800.0, 0.0, fails=2),
          res(-1000.0, 200.0, j_margin=-1.0),
          res(-800.0, 200.0, j_margin=14.0)]
    txt = bs.render_map(rs, [-1000.0, -800.0], [0.0, 200.0])
    assert "." in txt and "x" in txt and "!" in txt and "14" in txt, txt


def test_map_rows_run_high_y_first():
    """지도는 위가 +y 여야 도면과 같은 방향으로 읽힌다."""
    rs = [res(-1000.0, 0.0, j_margin=11.0),
          res(-1000.0, 200.0, j_margin=22.0)]
    txt = bs.render_map(rs, [-1000.0], [0.0, 200.0])
    body = [ln for ln in txt.split("\n")[1:]]
    assert "22" in body[0], body
    assert "11" in body[1], body


def test_map_shows_question_for_missing_cell():
    txt = bs.render_map([], [-1000.0], [0.0])
    assert "?" in txt, txt


# ── 5. 리포트 ───────────────────────────────────────────

def test_report_lists_top_and_counts():
    rs = [res(-1000.0, 0.0, j_margin=5.0),
          res(-1200.0, 0.0, j_margin=18.0),
          res(-1400.0, 0.0, fails=4)]
    txt = bs.report(rs, [-1400.0, -1200.0, -1000.0], [0.0], top=2)
    assert "통과 2개" in txt, txt
    assert "18.0" in txt, txt


def test_report_explains_when_nothing_passes():
    rs = [res(-1000.0, 0.0, fails=4), res(-1200.0, 0.0, overlap=30.0)]
    txt = bs.report(rs, [-1200.0, -1000.0], [0.0])
    assert "통과한 후보가 없다" in txt, txt
    assert "도달" in txt, txt


def test_report_says_what_was_skipped():
    """생략한 검사를 말하지 않으면 '전부 봤다'로 읽힌다."""
    rs = [res(-1000.0, 0.0, j_margin=9.0, clear=None)]
    txt = bs.report(rs, [-1000.0], [0.0], skipped="팔 간섭 검사")
    assert "생략" in txt and "간섭" in txt, txt
    assert "미검사" in txt, txt


def test_prefilter_is_reported_not_hidden():
    r = res(-9000.0, 0.0)
    r["prefiltered"] = True
    r["reason"] = "도달 범위 밖 5000mm (사전 기각)"
    r["ok"] = False
    txt = bs.report([r], [-9000.0], [0.0])
    assert "사전 기각 1개" in txt, txt
    assert "-" in bs.render_map([r], [-9000.0], [0.0]), txt


# ── 6. 사전 기각 ────────────────────────────────────────

def test_far_target_flags_only_beyond_limit():
    plane = rg.Plane(rg.Point3d(0, 0, 0), rg.Vector3d.XAxis,
                     rg.Vector3d.YAxis)
    near = [rg.Plane(rg.Point3d(1000.0, 0.0, 0.0), rg.Vector3d.XAxis,
                     rg.Vector3d.YAxis)]
    far = [rg.Plane(rg.Point3d(9000.0, 0.0, 0.0), rg.Vector3d.XAxis,
                    rg.Vector3d.YAxis)]
    assert bs.far_target(near, plane) is None
    d = bs.far_target(far, plane)
    assert d is not None and d > bs.PREFILTER_REACH_MM, d


def test_far_target_measures_from_shoulder_not_origin():
    """어깨는 베이스 원점에서 +x 320, +z 780 이다. 원점에서 재면 어긋난다."""
    plane = rg.Plane(rg.Point3d(0, 0, 0), rg.Vector3d.XAxis,
                     rg.Vector3d.YAxis)
    t = [rg.Plane(rg.Point3d(0.0, 0.0, 0.0), rg.Vector3d.XAxis,
                  rg.Vector3d.YAxis)]
    d = bs.far_target(t, plane, limit=0.0)
    want = (320.0 ** 2 + 780.0 ** 2) ** 0.5
    assert close(d, want, 1e-6), (d, want)


TESTS = [
    test_grid_includes_both_ends,
    test_grid_handles_reversed_bounds,
    test_grid_appends_ragged_end,
    test_grid_rejects_zero_step,
    test_polar_ring_lands_on_the_circle,
    test_polar_carries_cell_coords,
    test_polar_rejects_zero_step,
    test_map_uses_cell_when_present,
    test_clean_candidate_passes,
    test_overlap_rejected,
    test_reach_failure_rejected,
    test_negative_joint_margin_rejected,
    test_rated_speed_excess_rejected,
    test_collision_rejected,
    test_overlap_wins_over_reach,
    test_tight_margin_is_not_a_rejection,
    test_zero_margin_is_not_rejected,
    test_rank_prefers_larger_joint_margin,
    test_rank_drops_infeasible,
    test_rank_tie_breaks_on_clearance,
    test_rank_tie_breaks_on_override_last,
    test_unchecked_collision_does_not_beat_measured,
    test_map_marks_each_rejection_differently,
    test_map_rows_run_high_y_first,
    test_map_shows_question_for_missing_cell,
    test_report_lists_top_and_counts,
    test_report_explains_when_nothing_passes,
    test_report_says_what_was_skipped,
    test_prefilter_is_reported_not_hidden,
    test_far_target_flags_only_beyond_limit,
    test_far_target_measures_from_shoulder_not_origin,
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
    with open(os.path.join(HERE, "_base_search_log.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(_log))
    print("\n".join(_log))

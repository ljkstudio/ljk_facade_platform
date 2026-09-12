# -*- coding: utf-8 -*-
"""pipeline.py 테스트 — 실패가 조용하지 않은가.

**어댑터(GH)는 이 결과를 그대로 화면에 옮긴다.** 그러니 실패든 성공이든 여기서
말이 완성되어 있어야 한다. 어댑터가 판단을 하기 시작하면 판단이 두 곳에 생긴다.
"""

import material as mt
import meshes
import pipeline as pl
import solver as sv


def test_plane_runs_end_to_end():
    verts, faces = meshes.plane_grid()
    out = pl.run(verts, faces, allow_mm=10.0)
    assert out.ok
    assert len(out.curve) >= 4
    assert out.info


def test_warn_lists_passing_checks_too():
    """빈 경고 목록이 '검사 안 함'과 구별되어야 한다."""
    verts, faces = meshes.plane_grid()
    out = pl.run(verts, faces)
    joined = " ".join(out.warn)
    assert "통과" in joined
    assert "미판정" in joined            # elong_max 가 없으므로


def test_bad_topology_stops_before_the_solver():
    """나쁜 메쉬를 통과시키면 솔버가 그럴듯한 틀린 답을 낸다."""
    out = pl.run([(0.0, 0.0, 0.0)] * 4, [(0, 1, 2), (0, 2, 1)])   # 닫힌 껍질
    assert not out.ok
    assert out.curve == []
    assert any("위상" in w for w in out.warn)
    assert any("경계가 없" in w for w in out.warn)


def test_vertex_cap_refuses_instead_of_freezing_rhino():
    verts, faces = meshes.sphere_cap(nr=8, nt=24)
    out = pl.run(verts, faces, max_verts=10)
    assert not out.ok
    joined = " ".join(out.warn)
    assert "10" in joined and ("요소 크기" in joined or "정점" in joined)


def test_vertex_cap_says_how_long_it_would_take():
    """**"상한을 넘었다"만으로는 얼마나 줄여야 하는지 알 수 없다.**

    사용자가 겪는 것은 "정점 5889개"가 아니라 "Rhino 가 멈춰 있는 6초"다.
    예상 시간을 말해야 요소 크기를 얼마나 키울지 판단할 수 있다.
    """
    verts, faces = meshes.sphere_cap(nr=8, nt=24)
    out = pl.run(verts, faces, max_verts=10)
    joined = " ".join(out.warn)
    assert "초" in joined, joined
    assert "멈춰" in joined or "얼어" in joined, joined


def test_default_vertex_cap_follows_the_backend():
    """**같은 상한을 두 백엔드에 쓰면 한쪽은 과보호, 다른 쪽은 무방비가 된다.**

    실측 2026-08-14 (돔, Rhino 8 py39): numpy 로 2049정점 0.50 s / 5889정점
    1.44 s / 16385정점 6.14 s. numpy 없이는 2049정점이 10.28 s — 20배다.
    """
    before = sv.FORCE_PURE
    try:
        sv.FORCE_PURE = False
        fast = pl.default_max_verts()
        sv.FORCE_PURE = True
        slow = pl.default_max_verts()
    finally:
        sv.FORCE_PURE = before
    if sv.HAS_NUMPY:
        assert fast > slow * 5, "numpy=%d pure=%d" % (fast, slow)
    assert slow > 0


def test_explicit_max_verts_still_wins():
    """자동 상한이 사용자의 명시값을 덮으면 안 된다."""
    verts, faces = meshes.plane_grid()
    assert pl.run(verts, faces, max_verts=len(verts)).ok
    assert not pl.run(verts, faces, max_verts=len(verts) - 1).ok


def test_bad_material_is_reported_not_swallowed():
    out = pl.run(*meshes.plane_grid(), props=mt.MaterialProps(wrinkle_penalty=0.2))
    assert not out.ok
    assert any("wrinkle_penalty" in w for w in out.warn)


def test_info_carries_the_numbers_a_person_needs():
    verts, faces = meshes.sphere_cap(R=500.0, theta=0.5, nr=5, nt=14)
    out = pl.run(verts, faces, allow_mm=12.0)
    assert out.ok
    for token in ("σ", "반복", "면적", "여유"):
        assert token in out.info, "info 에 %r 가 없다:\n%s" % (token, out.info)


def test_info_says_which_material_fields_did_nothing():
    props = mt.MaterialProps(name="AL", thickness=3.0, source="테스트")
    out = pl.run(*meshes.plane_grid(), props=props)
    assert "형상에는 영향 없음" in out.info


def test_degenerate_triangle_is_reported_not_raised():
    """예외가 GH 캔버스까지 올라가면 사용자는 빨간 상자만 본다."""
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    out = pl.run(verts, [(0, 1, 2), (0, 2, 3)])
    assert not out.ok
    assert any("퇴화" in w or "면적" in w for w in out.warn)

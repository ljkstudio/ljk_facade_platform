# -*- coding: utf-8 -*-
"""pipeline.py 테스트 — 실패가 조용하지 않은가.

**어댑터(GH)는 이 결과를 그대로 화면에 옮긴다.** 그러니 실패든 성공이든 여기서
말이 완성되어 있어야 한다. 어댑터가 판단을 하기 시작하면 판단이 두 곳에 생긴다.
"""

import material as mt
import meshes
import pipeline as pl


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

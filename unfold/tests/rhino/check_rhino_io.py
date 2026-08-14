#! python 3
# -*- coding: utf-8 -*-
"""rhino_io.py 검사 — Rhino 안에서 돈다.

    python unfold/tools/run_rhino_check.py

결과는 `_rhino_io_log.txt` 에 쓴다. Rhino 콘솔 출력은 밖에서 보이지 않는다.
로그를 **먼저 지우므로** 파일이 없으면 "통과"가 아니라 "실행되지 않았다"다.
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "src")))

for _name in [n for n in list(sys.modules) if getattr(sys.modules.get(n), "__file__", None)
              and os.path.normcase(os.path.normpath(sys.modules[n].__file__)).startswith(
                  os.path.normcase(os.path.normpath(os.path.join(HERE, "..", "..", "src"))))]:
    del sys.modules[_name]

import Rhino.Geometry as rg          # noqa: E402

import material as mt                # noqa: E402
import pipeline as pl                # noqa: E402
import rhino_io as rio               # noqa: E402

LOG = os.path.join(HERE, "_rhino_io_log.txt")
lines = []
fails = [0]

SPHERE_RADIUS_MM = 2000.0      # 브리핑대로: 반지름 2000
PATCH_DOMAIN_FRACTION = 0.20   # 구 파라미터 도메인 가운데 20% 만 남긴다 (열린 트림 경계 확보)


def check(name, cond, detail=""):
    lines.append("%s %s %s" % ("OK  " if cond else "FAIL", name, detail))
    if not cond:
        fails[0] += 1


try:
    # 반지름 2000 구면 조각을 Brep 으로 만든다 (복곡면 + 트림 경계).
    #
    # 브리핑 원안은 Brep.CreateBooleanIntersection([face], [box]) 로 구면 패치와
    # 박스를 불리언 교집합했는데, 실제로 돌려보니(첫 실행 로그) 열린 패치가 아니라
    # 닫힌 솔리드(면 6개, 경계 없음)가 나왔다 — RhinoCommon 이 불리언을 위해 열린
    # 서피스를 자동으로 캡을 씌우기 때문으로 보인다. pipeline 은 "경계가 없다"로
    # 정확히 거부했으므로 rhino_io.py 쪽 문제가 아니라 검사용 지오메트리 구성의
    # 문제였다. Surface.Trim 으로 U/V 파라미터 도메인을 직접 좁혀 열린 트림 패치를
    # 만드는 방식으로 바꿨다 — 여전히 반지름 2000 구, 여전히 복곡면 + 트림 경계다.
    sphere = rg.Sphere(rg.Point3d(0, 0, 0), SPHERE_RADIUS_MM)
    srf = sphere.ToNurbsSurface()
    du, dv = srf.Domain(0), srf.Domain(1)
    half = PATCH_DOMAIN_FRACTION / 2.0
    u_range = rg.Interval(du.ParameterAt(0.5 - half), du.ParameterAt(0.5 + half))
    v_range = rg.Interval(dv.ParameterAt(0.5 - half), dv.ParameterAt(0.5 + half))
    patch = srf.Trim(u_range, v_range)
    brep = rg.Brep.CreateFromSurface(patch) if patch is not None else None

    verts, faces, notes = rio.mesh_from_brep(brep, 60.0)
    lines.extend("    " + n for n in notes)
    check("메쉬화", len(verts) > 50 and len(faces) > 50,
          "정점 %d 면 %d" % (len(verts), len(faces)))
    check("삼각형만", all(len(f) == 3 for f in faces))

    out = pl.run(verts, faces, mt.MaterialProps(name="검사용", elong_max=0.12,
                                                source="검사 스크립트"),
                 allow_mm=15.0, max_verts=20000)
    lines.append("    ok=%s" % out.ok)
    lines.extend("    " + w for w in out.warn)
    check("파이프라인", out.ok)

    if out.ok:
        m = rio.to_mesh(out.uv, out.faces)
        check("평면 메쉬", m is not None and m.Vertices.Count == len(out.uv))
        sm = rio.to_strain_mesh(out.uv, out.faces, out.sigmas)
        check("변형률 색칠", sm is not None and sm.VertexColors.Count == len(out.uv))
        crv = rio.to_curve(out.curve)
        check("재단 곡선", crv is not None and crv.IsClosed)

        amp = rg.AreaMassProperties.Compute(crv)
        check("재단 면적 > 평면 메쉬 면적",
              amp is not None and amp.Area > out.metrics.area_2d,
              "재단 %.1f vs 평면 %.1f" % (amp.Area if amp else -1, out.metrics.area_2d))
        check("최소 여유가 요구치 이상", out.blank.clearance_min >= 15.0 - 1e-6,
              "%.3f mm" % out.blank.clearance_min)
except Exception:
    lines.append("EXCEPTION")
    lines.append(traceback.format_exc())
    fails[0] += 1

lines.append("실패 %d건" % fails[0])
with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

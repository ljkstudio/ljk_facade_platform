#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""회귀 픽스처를 만든다 — 지금 나오는 수치를 파일로 굳힌다.

    python unfold/tools/dump_fixture.py

**숫자를 눈으로 확인하고 커밋해야 한다.** 자동 생성된 값을 보지 않고 굳히면
그때의 버그까지 정본이 된다.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "src")))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "tests")))

import flatten as fl          # noqa: E402
import material as mt         # noqa: E402
import meshes                 # noqa: E402
import metrics as mx          # noqa: E402
import topology as tp         # noqa: E402

R, THETA, NR, NT, ITERS = 500.0, 0.6, 8, 24, 120
OUT = os.path.normpath(os.path.join(HERE, "..", "tests", "fixtures", "cap_golden.json"))


def main():
    verts, faces = meshes.sphere_cap(R=R, theta=THETA, nr=NR, nt=NT)
    topo = tp.build(len(verts), faces)
    res = fl.run(verts, faces, topo, mt.DEFAULT, iters=ITERS)
    m = mx.evaluate(res, mt.DEFAULT)
    cx = sum(p[0] for p in res.uv) / len(res.uv)
    cy = sum(p[1] for p in res.uv) / len(res.uv)
    radii = [math.hypot(res.uv[v][0] - cx, res.uv[v][1] - cy)
             for v in topo.boundary_loops[0]]
    data = {
        "case": {"R": R, "theta": THETA, "nr": NR, "nt": NT, "iters": ITERS},
        "bracket": {
            "orthographic": R * math.sin(THETA),              # σ_hoop=1 극단 — **하한**
            "isometric": R * THETA,                           # σ_r=1 극단 — **상한**
            "equal_area": 2.0 * R * math.sin(THETA / 2.0),    # 참고값. 하한이 아니다
        },
        "outer_radius_mean": sum(radii) / len(radii),
        "sigma_min": m.sigma_min,
        "sigma_max": m.sigma_max,
        "max_forming_strain": m.max_forming_strain,
        "area_3d": m.area_3d,
        "area_2d": m.area_2d,
        "wrinkle_face_count": len(m.wrinkle_faces),
        "iterations": res.iterations,
        "converged": res.converged,
    }
    if not os.path.isdir(os.path.dirname(OUT)):
        os.makedirs(os.path.dirname(OUT))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

#! python 3
# r: numpy
# -*- coding: utf-8 -*-
"""전개 한 판이 **Rhino 안에서** 어디에 시간을 쓰는지 잰다.

    python unfold/tools/profile_in_rhino.py [panel_dome] [edge_mm] [iters]

GH 컴포넌트가 도는 것과 같은 엔진(Rhino 8 의 CPython 3)에서 재야 의미가 있다.
밖에서 재면 numpy 유무와 인터프리터가 달라 다른 숫자가 나온다.

로그를 **먼저 지우므로** 파일이 없으면 "빨랐다"가 아니라 "실행되지 않았다"다.
"""

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.normpath(os.path.join(HERE, "..", "..", "src"))
sys.path.insert(0, SRC)

_norm = os.path.normcase(os.path.normpath(SRC))
for _name in [n for n in list(sys.modules)
              if getattr(sys.modules.get(n), "__file__", None)
              and os.path.normcase(
                  os.path.normpath(sys.modules[n].__file__)).startswith(_norm)]:
    del sys.modules[_name]

import Rhino                            # noqa: E402

import blank as bk                      # noqa: E402
import flatten as fl                    # noqa: E402
import material as mt                   # noqa: E402
import metrics as mx                    # noqa: E402
import rhino_io as rio                  # noqa: E402
import solver as sv                     # noqa: E402
import topology as tp                   # noqa: E402

LOG = os.path.join(HERE, "_profile_log.txt")
CFG = os.path.join(HERE, "_profile_cfg.txt")

TARGET, EDGE_MM, ITERS = "panel_dome", 60.0, 30
if os.path.exists(CFG):
    with open(CFG, encoding="utf-8") as f:
        parts = f.read().split()
    if len(parts) >= 3:
        TARGET, EDGE_MM, ITERS = parts[0], float(parts[1]), int(parts[2])

lines = []


def stamp(label, t0):
    dt = time.time() - t0
    lines.append("%-28s %8.3f s" % (label, dt))
    return dt


try:
    lines.append("python %s" % sys.version.split()[0])
    lines.append("numpy %s (solver.HAS_NUMPY=%s)"
                 % ("있음" if sv.HAS_NUMPY else "**없음**", sv.HAS_NUMPY))
    lines.append("target=%s edge_mm=%.1f iters=%d" % (TARGET, EDGE_MM, ITERS))
    lines.append("")

    doc = Rhino.RhinoDoc.ActiveDoc
    st = Rhino.DocObjects.ObjectEnumeratorSettings()
    st.HiddenObjects = True
    st.NormalObjects = True
    st.LockedObjects = True
    brep = None
    for o in doc.Objects.GetObjectList(st):
        if o.Attributes.Name == TARGET:
            brep = o.Geometry
    if brep is None:
        raise RuntimeError("Rhino 에 '%s' 가 없다" % TARGET)

    t_all = time.time()

    t0 = time.time()
    verts, faces, notes = rio.mesh_from_brep(brep, EDGE_MM)
    stamp("1 mesh_from_brep", t0)
    lines.append("   정점 %d 삼각형 %d" % (len(verts), len(faces)))

    t0 = time.time()
    topo = tp.build(len(verts), faces)
    stamp("2 topology.build", t0)

    # flatten 안을 쪼개 잰다 — 사전계산 / local-global 반복이 갈린다
    import element as el
    t0 = time.time()
    el.prepare(verts, faces)
    stamp("3 element.prepare", t0)

    # flatten 안을 local / 조립 / CG 로 갈라 잰다 — 어느 쪽을 고쳐야 하는지가
    # 여기서 갈린다. 감싸기만 하고 계산은 원본 그대로 돈다.
    prof = {"local": 0.0, "assemble": 0.0, "cg": 0.0, "cg_calls": 0, "cg_iters": 0,
            "per_call": []}
    _orig_local, _orig_global, _orig_cg = fl._local_step, fl._global_step, sv.cg

    def timed_local(*a, **kw):
        t = time.time()
        try:
            return _orig_local(*a, **kw)
        finally:
            prof["local"] += time.time() - t

    def timed_cg(*a, **kw):
        t = time.time()
        try:
            sol, used = _orig_cg(*a, **kw)
            prof["cg_calls"] += 1
            prof["cg_iters"] += used
            prof["per_call"].append(used)
            return sol, used
        finally:
            prof["cg"] += time.time() - t

    def timed_global(*a, **kw):
        t = time.time()
        try:
            return _orig_global(*a, **kw)
        finally:
            prof["assemble"] += time.time() - t

    fl._local_step, fl._global_step, sv.cg = timed_local, timed_global, timed_cg
    try:
        t0 = time.time()
        res = fl.run(verts, faces, topo, mt.DEFAULT, iters=ITERS)
        dt_flat = stamp("4 flatten.run (전체)", t0)
    finally:
        fl._local_step, fl._global_step, sv.cg = _orig_local, _orig_global, _orig_cg

    lines.append("   반복 %d회, 수렴=%s, 반복당 %.3f s"
                 % (res.iterations, res.converged,
                    dt_flat / max(res.iterations, 1)))
    lines.append("   4a local 단계        %8.3f s" % prof["local"])
    lines.append("   4b global 단계(전체)  %8.3f s   그중 CG %.3f s, 조립 %.3f s"
                 % (prof["assemble"], prof["cg"], prof["assemble"] - prof["cg"]))
    lines.append("   4c CG 호출 %d회, 반복 합계 %d회 (호출당 %.0f회, 반복당 %.2f ms)"
                 % (prof["cg_calls"], prof["cg_iters"],
                    prof["cg_iters"] / max(prof["cg_calls"], 1),
                    1000.0 * prof["cg"] / max(prof["cg_iters"], 1)))

    lines.append("   4d CG 호출별 반복 수: %s" % prof["per_call"])

    t0 = time.time()
    m = mx.evaluate(res, mt.DEFAULT)
    stamp("5 metrics.evaluate", t0)

    t0 = time.time()
    bl = bk.build(res.uv, topo, allow_mm=15.0)
    stamp("6 blank.build", t0)

    t0 = time.time()
    rio.to_mesh(res.uv, res.faces)
    rio.to_strain_mesh(res.uv, res.faces, res.sigmas)
    rio.to_curve(bl.curve)
    stamp("7 결과 지오메트리", t0)

    lines.append("")
    stamp("합계", t_all)
    lines.append("σ %.6f ~ %.6f" % (m.sigma_min, m.sigma_max))

    # ── 안쪽 선형해 허용치 쓸기 ────────────────────────────────────────
    #
    # 가설: 바깥 루프는 에너지 상대변화 1e-6 에서 멈추는데 안쪽 CG 는 1e-11 까지
    # 푼다. 그만큼이 통째로 낭비라면 허용치를 풀었을 때 **시간만 줄고 σ 는 안
    # 바뀌어야** 한다. 안 바뀌는지를 같이 재지 않으면 그냥 대충 푼 것이 된다.
    base_rel = fl.CG_REL
    lines.append("")
    lines.append("── CG 허용치 쓸기 (기준 CG_REL=%g) ──" % base_rel)
    lines.append("%-10s %8s %8s %10s  %s" % ("CG_REL", "시간", "CG반복", "에너지", "σ 범위"))
    ref = None
    for rel in (1e-11, 1e-9, 1e-7, 1e-5, 1e-3):
        fl.CG_REL = rel
        prof["cg_iters"] = 0
        prof["cg_calls"] = 0
        prof["per_call"] = []
        sv.cg = timed_cg
        try:
            t0 = time.time()
            r2 = fl.run(verts, faces, topo, mt.DEFAULT, iters=ITERS)
            dt2 = time.time() - t0
        finally:
            sv.cg = _orig_cg
        m2 = mx.evaluate(r2, mt.DEFAULT)
        if ref is None:
            ref = (m2.sigma_min, m2.sigma_max)
        lines.append("%-10g %7.2fs %8d %10.4g  %.6f ~ %.6f  (기준대비 Δσmax %.2e)"
                     % (rel, dt2, prof["cg_iters"], r2.energy_history[-1],
                        m2.sigma_min, m2.sigma_max, abs(m2.sigma_max - ref[1])))
    fl.CG_REL = base_rel
except Exception:
    lines.append(traceback.format_exc())

with open(LOG, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

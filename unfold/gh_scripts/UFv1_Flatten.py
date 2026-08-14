# -*- coding: utf-8 -*-
# UFv1 Flatten — 복곡면 한 장을 성형 전 블랭크로 편다
#
# **판단은 여기서 하지 않는다.** pipeline.run() 이 끝낸 결과를 화면에 옮기기만
# 한다. 어댑터가 판단을 시작하면 같은 판단이 두 곳에 생기고, 둘이 어긋나는 날
# 화면과 숫자가 다른 말을 하게 된다.
#
# **run 토글이 있는 이유**: GH 스크립트 컴포넌트는 Rhino UI 스레드에서 돈다.
# 5초 걸리는 계산은 5초 동안 Rhino 를 얼린다. 슬라이더를 만질 때마다 도는 것을
# 막아야 한다.
#
# ── 입력 (Rhino 8 스크립트 에디터에서 이 순서대로 만든다) ──────────────
#   platform_path  str     repo root (필수)
#   srf            Brep    전개할 곡면 한 장
#   props          object  UFv1 Material 출력. 없으면 기본 물성 + 경고
#   edge_mm        float   목표 요소 크기 (기본 40)
#   allow_mm       float   트림 여유 (기본 15)
#   iters          int     최대 반복 (기본 30)
#   max_verts      int     정점 상한 (기본 5000). 넘으면 계산하지 않는다
#   run            bool    계산 스위치
#
# ── 출력 ────────────────────────────────────────────────────────────
#   flat    Mesh    평면 메쉬
#   blank   Curve   재단 외곽 (여유 포함)
#   strain  Mesh    σ 색칠 — 파랑 σ<1(성형에서 인장), 빨강 σ>1(주름 위험)
#   warn    str*    경고·판정. **통과한 것도 적는다**
#   info    str     요약

import os
import sys

flat = None
blank = None
strain = None
warn = []
info = ""

root = str(platform_path or "").strip().strip('"').strip("'")

if not root or not os.path.isdir(root):
    warn = ["platform_path 가 필요하다 (repo root 폴더)"]
elif not run:
    # **미판정이지 통과가 아니다.** 빈 결과를 통과로 읽으면 안 된다.
    warn = ["run 이 꺼져 있다 — 계산하지 않았다. 미판정이지 통과가 아니다"]
elif srf is None:
    warn = ["srf 가 비어 있다"]
else:
    src = os.path.join(root, "unfold", "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    # Rhino 모듈 캐시를 지운다 — 안 지우면 저장소 코드를 고쳐도 옛 모듈이 돈다.
    _norm = os.path.normcase(os.path.normpath(src))
    for _n in [n for n in list(sys.modules)
               if getattr(sys.modules.get(n), "__file__", None)
               and os.path.normcase(
                   os.path.normpath(sys.modules[n].__file__)).startswith(_norm)]:
        del sys.modules[_n]

    import material as mt
    import pipeline as pl
    import rhino_io as rio

    use = props if props is not None else mt.DEFAULT
    if props is None:
        warn.append("[참고] props 가 없어 기본 물성으로 돌았다 — "
                    "찢어짐 판정은 미판정이다")

    verts, faces, notes = rio.mesh_from_brep(srf, float(edge_mm or 40.0))
    if not faces:
        warn.extend("[경고] " + n for n in notes)
        info = "\n".join(notes)
    else:
        out = pl.run(verts, faces, use,
                     allow_mm=float(allow_mm if allow_mm is not None else 15.0),
                     iters=int(iters or 30),
                     max_verts=int(max_verts or 5000))
        warn.extend(out.warn)
        info = "\n".join(notes) + "\n" + out.info
        if out.ok:
            flat = rio.to_mesh(out.uv, out.faces)
            strain = rio.to_strain_mesh(out.uv, out.faces, out.sigmas)
            blank = rio.to_curve(out.curve)

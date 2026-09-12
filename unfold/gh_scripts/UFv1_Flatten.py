# r: numpy
# -*- coding: utf-8 -*-
# UFv1 Flatten — 복곡면 한 장을 성형 전 블랭크로 편다
#
# **첫 줄의 `# r: numpy` 가 이 컴포넌트에서 가장 값이 큰 한 줄이다.**
# 이게 없으면 Rhino 8 의 py39 는 numpy 를 못 보고 solver 가 순수 파이썬으로
# 돈다 — 실측 2026-08-14, 돔 2049정점: 10.28 s → 0.50 s (20.6배). GH 스크립트
# 컴포넌트는 Rhino UI 스레드에서 돌기 때문에 그 시간이 그대로 **화면이 얼어붙는
# 시간**이다. numpy 를 못 끌어오는 환경에서도 solver 는 순수 경로로 계산은 하고,
# 그때는 info 에 "numpy 없음"이 찍힌다 — 느린 이유가 화면에 남아야 한다.
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
#   max_verts      int     정점 상한. 비워 두면 이 환경 속도로 자동 계산한다
#                          (numpy 있으면 ≈8000, 없으면 ≈600). 넘으면 계산하지 않는다
#   run            bool    계산 스위치
#
# ── 출력 ────────────────────────────────────────────────────────────
#   flat    Mesh    평면 메쉬
#   blank   Curve   재단 외곽 (여유 포함)
#   strain  Mesh    σ 색칠 — 파랑 σ<1(성형에서 인장), 빨강 σ>1(주름 위험)
#   warn    str     경고·판정 한 줄씩 (\n 으로 이은 문자열). **통과한 것도 적는다**
#   info    str     요약
#
# **warn 이 목록이 아니라 문자열인 이유** (실측 2026-08-14): Rhino 8 의 새
# Script 컴포넌트는 파이썬 리스트를 GH 항목으로 갈라주지 않는다. 출력
# 파라미터를 list 접근으로 만들어도 `GH_ObjectWrapper(PyObject)` 하나로 나오고,
# string 힌트를 걸면 리스트를 통째로 `['...', '...']` 로 문자열화한다. 그대로 두면
# 패널에 대괄호와 따옴표가 찍혀 판정을 읽을 수가 없다. 그래서 여기서 잇는다.

import os
import sys
import time

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
    import solver as sv

    use = props if props is not None else mt.DEFAULT
    if props is None:
        warn.append("[참고] props 가 없어 기본 물성으로 돌았다 — "
                    "찢어짐 판정은 미판정이다")

    verts, faces, notes = rio.mesh_from_brep(srf, float(edge_mm or 40.0))
    if not faces:
        warn.extend("[경고] " + n for n in notes)
        info = "\n".join(notes)
    else:
        # **걸린 시간을 적는다.** 이 컴포넌트는 UI 스레드에서 도니까 이 숫자가
        # 곧 Rhino 가 멈춰 있던 시간이다. 화면에 안 적으면 "느리다"가 느낌으로만
        # 남아 정점 수·요소 크기 중 무엇을 줄여야 하는지 판단할 수가 없다.
        _t0 = time.time()
        # max_verts 를 안 주면 pipeline 이 **이 환경의 속도로부터** 상한을
        # 계산한다. 여기서 숫자를 박으면 numpy 유무를 모르는 채로 정하게 된다.
        out = pl.run(verts, faces, use,
                     allow_mm=float(allow_mm if allow_mm is not None else 15.0),
                     iters=int(iters or 30),
                     max_verts=int(max_verts) if max_verts else None)
        _dt = time.time() - _t0
        _engine = "numpy %s" % (sv.numpy.__version__ if sv.HAS_NUMPY
                                else "없음 — 순수 파이썬 (수십 배 느리다)")
        warn.extend(out.warn)
        # 거부된 경우(정점 상한 등)에는 시간을 적지 않는다 — "계산 0.00 s" 는
        # 빨랐다는 뜻이 아니라 계산을 안 했다는 뜻인데, 그렇게 읽히지 않는다.
        took = ("계산 %.2f s — 그동안 Rhino 는 멈춰 있다 (%s)\n" % (_dt, _engine)
                if out.ok else "")
        info = "\n".join(notes) + "\n" + took + out.info
        if out.ok:
            flat = rio.to_mesh(out.uv, out.faces)
            strain = rio.to_strain_mesh(out.uv, out.faces, out.sigmas)
            blank = rio.to_curve(out.curve)

# 판정을 한 줄씩 잇는다 (위 머리말 참고). 목록으로 두면 패널이 못 읽는다.
warn = "\n".join(warn)

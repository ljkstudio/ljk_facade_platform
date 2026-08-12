# -*- coding: utf-8 -*-
# AMv1 PathFrames — 툴패스 타겟을 눈으로 읽을 수 있게 벡터로 펼친다
#
# targets 는 Plane 목록이라 화면에서 자세가 보이지 않는다. 각 타겟의
# 법선·롤러축·진행방향을 선으로 뽑아 경로가 곡면을 어떻게 따라가는지,
# 공구가 어디를 향하는지 확인한다.
#
# Inputs:
#   targets     Plane*  RollerPath 의 targets (list)
#   move_kind   str*    같은 순서의 구간 종류 (선택). 패스 분할에도 쓴다
#   pick        int     이 패스만 표시. -1(기본)이면 전체
#   every       int     N개마다 하나만 표시, 없으면 5
#   n_len       float   법선·진행 표시 길이, 없으면 60
#   roller_w    float   롤러 축 표시 길이, 없으면 80
#
# Outputs:
#   path        표시 대상 타겟을 순서대로 이은 폴리라인 — 로봇이 지나는 궤적
#   pts         타겟 원점 (= 롤러 중심)
#   normal      곡면 법선 방향 선 (바깥쪽) — 타겟의 -Z
#   tool_axis   공구 접근 방향 선 (곡면 쪽) — 타겟의 +Z
#   roller      롤러 축 선 (타겟의 Y, 길이 roller_w)
#   travel      진행 방향 선 (타겟의 X)
#   pts_form    성형 구간 점만
#   pts_air     공중 구간 점만 (approach/retract/link)
#   info        요약
#
# 전 구간(1,175개)을 한 번에 그리면 40mm 간격 패스 26본이 붉은 덩어리가 되어
# 아무것도 읽히지 않는다. pick 으로 한 패스씩 보는 것이 기본 사용법이다.

import Rhino.Geometry as rg


def _default(name, value, positive=False):
    g = globals()
    v = g.get(name)
    if v is None or (positive and v <= 0):
        g[name] = value


_default("every", 5, positive=True)
_default("n_len", 60.0, positive=True)
_default("roller_w", 80.0, positive=True)
_default("pick", -1)


path = None
pts = []
normal = []
tool_axis = []
roller = []
travel = []
pts_form = []
pts_air = []
info = ""


if targets:
    tg = list(targets)
    mk = [str(k) for k in move_kind] if move_kind else []
    n = int(every)

    # 패스 분할 — approach 가 새 패스의 시작이다. move_kind 가 없으면 전체 1개.
    bounds = [i for i, k in enumerate(mk) if k == "approach"]
    if not bounds:
        bounds = [0]
    spans = []
    for a, b in zip(bounds, bounds[1:] + [len(tg)]):
        spans.append((a, b))

    pi = int(pick)
    if 0 <= pi < len(spans):
        lo, hi = spans[pi]
        idx_all = list(range(lo, hi))
    else:
        pi = -1
        idx_all = list(range(len(tg)))

    idx = idx_all[::n]
    # 마지막 타겟은 항상 포함 — 경로 끝이 잘려 보이면 오해를 만든다
    if idx and idx_all and idx[-1] != idx_all[-1]:
        idx.append(idx_all[-1])

    for i in idx:
        pl = tg[i]
        o = pl.Origin
        z = rg.Vector3d(pl.ZAxis)          # 공구가 내려누르는 방향
        out = rg.Vector3d(z)
        out.Reverse()                      # 곡면 법선(바깥쪽)

        pts.append(o)
        normal.append(rg.Line(o, o + out * n_len))
        tool_axis.append(rg.Line(o, o + z * n_len))
        roller.append(rg.Line(o - pl.YAxis * (roller_w / 2.0),
                              o + pl.YAxis * (roller_w / 2.0)))
        travel.append(rg.Line(o, o + pl.XAxis * (n_len * 0.6)))

        kind = mk[i] if i < len(mk) else "form"
        if kind == "form":
            pts_form.append(o)
        else:
            pts_air.append(o)

    # 표시 대상을 순서대로 이은 궤적 — 이것이 "로봇이 지나는 경로"다
    if len(idx) > 1:
        path = rg.PolylineCurve([tg[i].Origin for i in idx])

    counts = {}
    for k in mk:
        counts[k] = counts.get(k, 0) + 1

    info = "\n".join([
        "AMv1 PathFrames",
        "=" * 40,
        "패스 {}개  |  선택 {}".format(
            len(spans), "전체" if pi < 0 else "#{} (타겟 {}~{})".format(
                pi, spans[pi][0], spans[pi][1] - 1)),
        "타겟 {}개 중 {}개 표시 (every {})".format(len(tg), len(pts), n),
        "성형 {} / 공중 {}".format(len(pts_form), len(pts_air)),
        "구간 구성(전체): {}".format(counts if counts else "move_kind 미연결"),
        "",
        "표시 규약:",
        "  path      = 표시 타겟을 순서대로 이은 궤적",
        "  normal    = 타겟 -Z, 곡면 바깥쪽 (길이 {:.0f})".format(n_len),
        "  tool_axis = 타겟 +Z, 공구가 내려누르는 방향",
        "  roller    = 타겟 Y, 접촉선 (길이 {:.0f})".format(roller_w),
        "  travel    = 타겟 X, 진행 방향",
        "",
        "** pick 에 0~{} 를 넣어 한 패스씩 볼 것.".format(max(0, len(spans) - 1)),
        "   전 구간을 한 번에 그리면 40mm 간격 패스가 겹쳐 덩어리로 보인다.",
    ])
else:
    info = "RollerPath 의 targets 를 연결하세요."

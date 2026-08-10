#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""AdaptiveMold 테스트용 곡면 패널을 .3dm으로 생성한다.

**Rhino 없이** rhino3dm으로 만든다 (pip install rhino3dm).

    python adaptive_mold/tools/make_test_panels.py

기본 몰드(1000x1000, 간격 200, stroke 0~400)를 기준으로 크기를 잡았다.
패널은 1200x1200으로 몰드보다 조금 크게 만들어 그리드 전체를 덮는다
(확장영역 판정을 섞지 않고 순수하게 높이 계산만 보기 위함).

각 패널이 드러내는 것:

  panel_flat      기준선. 모든 핀이 같은 높이여야 한다.
  panel_tilt10    10도 기울어진 평면. **지금 조사 중인 T2 케이스.**
                  제대로 정렬되면 높이가 균일해져야 한다.
  panel_cylinder  단곡(한 방향). 핀 몰드가 잘 재현해야 하는 형상.
  panel_saddle    안장형(역방향 이중곡). 재현이 어려운 형상 —
                  클램핑이 아니라 '이탈량'이 커지는지 봐야 한다.
  panel_dome      돔(동방향 이중곡). 중앙이 높아 stroke 상한에 걸리기 쉽다.
"""

import os
import sys
import math

import rhino3dm as r3

# 한국어 Windows 콘솔의 기본 인코딩은 cp949라 em dash 같은 문자에서 죽는다.
# 파일 쓰기(open의 encoding)뿐 아니라 stdout도 같은 함정에 걸린다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(REPO_ROOT, "adaptive_mold", "grasshopper")
OUT_3DM = os.path.join(OUT_DIR, "test_panels.3dm")

# 몰드 기준 (adaptive_mold 기본값과 동일)
MOLD_W = 1000.0
MOLD_L = 1000.0
STROKE_MIN = 0.0
STROKE_MAX = 400.0

# 패널은 몰드보다 조금 크게 — 그리드 전체를 덮도록
PAD = 100.0
X0, X1 = -PAD, MOLD_W + PAD
Y0, Y1 = -PAD, MOLD_L + PAD
CX, CY = MOLD_W / 2.0, MOLD_L / 2.0

MID = (STROKE_MIN + STROKE_MAX) / 2.0   # 200


def line_curve(p0, p1):
    return r3.NurbsCurve.Create(False, 1, [r3.Point3d(*p0), r3.Point3d(*p1)])


def arc_curve(p0, pmid_cp, p1):
    """degree 2 제어점 곡선. pmid_cp는 제어점이라 실제 중점 높이는 그 절반."""
    return r3.NurbsCurve.Create(
        False, 2, [r3.Point3d(*p0), r3.Point3d(*pmid_cp), r3.Point3d(*p1)])


def ruled(a, b):
    return r3.NurbsSurface.CreateRuledSurface(a, b)


def make_flat():
    z = MID
    a = line_curve((X0, Y0, z), (X1, Y0, z))
    b = line_curve((X0, Y1, z), (X1, Y1, z))
    return ruled(a, b)


def make_tilt(deg):
    """중앙(CX,CY,MID)을 지나며 Y축 둘레로 deg 만큼 기운 평면."""
    t = math.tan(math.radians(deg))
    z0 = MID + (X0 - CX) * t
    z1 = MID + (X1 - CX) * t
    a = line_curve((X0, Y0, z0), (X1, Y0, z1))
    b = line_curve((X0, Y1, z0), (X1, Y1, z1))
    return ruled(a, b)


def make_cylinder(rise):
    """X 방향으로 휜 단곡. 실제 중앙 상승량이 rise가 되도록 제어점을 2배로."""
    z_edge = MID - rise / 2.0
    z_cp = z_edge + 2.0 * rise
    a = arc_curve((X0, Y0, z_edge), (CX, Y0, z_cp), (X1, Y0, z_edge))
    b = arc_curve((X0, Y1, z_edge), (CX, Y1, z_cp), (X1, Y1, z_edge))
    return ruled(a, b)


def make_saddle(amp):
    """두 모서리는 올라가고 두 모서리는 내려간 안장형(hypar).
    직선 두 개를 꼬아 이으면 정확한 쌍곡포물면이 된다."""
    a = line_curve((X0, Y0, MID + amp), (X1, Y0, MID - amp))
    b = line_curve((X0, Y1, MID - amp), (X1, Y1, MID + amp))
    return ruled(a, b)


def make_dome(radius, top_z):
    """구면. 중심을 아래로 내려 상단 캡이 몰드 위에 오게 한다.
    ruled surface로는 동방향 이중곡을 만들 수 없어 구를 쓴다."""
    center = r3.Point3d(CX, CY, top_z - radius)
    sphere = r3.Sphere(center, radius)
    return r3.NurbsSurface.CreateFromSphere(sphere)


def z_range(srf, n=41):
    """몰드 영역(0~1000, 0~1000) 위쪽 면의 높이 범위.

    돔은 구 전체라 아랫면까지 재면 -2150 같은 값이 나온다. 핀은 위에서
    만나는 면만 보므로, 몰드 발자국 안에 들어오는 점 중 **위쪽 면**만 잰다.
    """
    du, dv = srf.Domain(0), srf.Domain(1)
    cell = {}
    for i in range(n):
        for j in range(n):
            u = du.T0 + (du.T1 - du.T0) * i / (n - 1.0)
            v = dv.T0 + (dv.T1 - dv.T0) * j / (n - 1.0)
            p = srf.PointAt(u, v)
            if not (0.0 <= p.X <= MOLD_W and 0.0 <= p.Y <= MOLD_L):
                continue
            key = (round(p.X / 25.0), round(p.Y / 25.0))
            if key not in cell or p.Z > cell[key]:
                cell[key] = p.Z
    zs = list(cell.values())
    return (min(zs), max(zs)) if zs else (0.0, 0.0)


PANELS = [
    ("panel_flat",     (200, 200, 200), make_flat(),
     "기준선 — 모든 핀이 같은 높이여야 함"),
    ("panel_tilt10",   (255, 140, 0),   make_tilt(10.0),
     "10도 기울어진 평면 — 조사 중인 T2 케이스"),
    ("panel_cylinder", (60, 160, 255),  make_cylinder(150.0),
     "단곡(한 방향) — 핀 몰드가 잘 재현해야 함"),
    ("panel_saddle",   (220, 60, 160),  make_saddle(120.0),
     "안장형 — 재현이 어려움. 이탈량을 볼 것"),
    ("panel_dome",     (80, 200, 120),  make_dome(1200.0, 250.0),
     "돔 — 중앙이 높아 stroke 상한에 걸리기 쉬움"),
]


def main():
    model = r3.File3dm()
    model.Settings.ModelUnitSystem = r3.UnitSystem.Millimeters
    model.ApplicationName = "make_test_panels.py"
    model.ApplicationDetails = "AdaptiveMold 테스트 패널"

    print("몰드 {:.0f}x{:.0f}, stroke {:.0f}~{:.0f}".format(
        MOLD_W, MOLD_L, STROKE_MIN, STROKE_MAX))
    print("패널 {:.0f}x{:.0f} (몰드보다 {:.0f}mm 여유)".format(
        X1 - X0, Y1 - Y0, PAD))
    print("")
    print("{:<16} {:>12} {:>12}  {}".format("패널", "z 최소", "z 최대", "비고"))
    print("-" * 76)

    for name, rgb, srf, note in PANELS:
        if srf is None or not srf.IsValid:
            print("[실패] {}".format(name))
            continue

        layer = r3.Layer()
        layer.Name = name
        layer.Color = (rgb[0], rgb[1], rgb[2], 255)
        li = model.Layers.Add(layer)

        attr = r3.ObjectAttributes()
        attr.Name = name
        attr.LayerIndex = li
        model.Objects.AddSurface(srf, attr)

        zmin, zmax = z_range(srf)
        warn = ""
        if zmin < STROKE_MIN or zmax > STROKE_MAX:
            warn = "  <- stroke 범위 벗어남(클램핑 예상)"
        print("{:<16} {:>12.1f} {:>12.1f}  {}{}".format(
            name, zmin, zmax, note, warn))

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    ok = model.Write(OUT_3DM, 7)
    print("")
    print("저장 {}: {}".format("성공" if ok else "실패", OUT_3DM))
    print("객체 {}개 / 레이어 {}개".format(len(model.Objects), len(model.Layers)))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
# AMv1 Base — 로봇 베이스 평면을 **한 곳에서** 정한다
#
# ──────────────────────────────────────────────────────────
# 왜 컴포넌트를 따로 두는가
# ──────────────────────────────────────────────────────────
#
# 베이스 평면은 Robot(계산)·Play(그림)·Check(판정)가 전부 필요하다. 각자
# `resolve_base_plane()` 을 부르면 코드는 한 곳이어도 **입력을 셋에 똑같이
# 물려야 하는 부담**이 남는다. 하나만 빼먹으면 오류가 나지 않고 **로봇이
# 계산된 위치와 다른 곳에 그려진다**(J-006 TRAP-03). 화면은 그럴듯한데
# 숫자가 다른 자리를 말하는, 가장 찾기 어려운 종류의 버그다.
#
# 그래서 여기서 한 번 정해 **Plane 하나로 내보낸다.** 받는 쪽은 판단하지 않는다.
# 이 컴포넌트를 안 물리면 아무것도 안 나오므로 빼먹으면 바로 드러난다.
#
# 우선순위는 robot.resolve_base_plane() 이 정한다:
#   robot_base(평면) > base_pt/base_dir(점·선) > 자동(타겟에서 유도)
#
# **로봇은 언제나 똑바로 선다.** 방향 벡터를 월드 XY 로 투영하므로 기울어진 선을
# 그어도 베이스가 눕지 않는다. 투영이 걸리면 info 에 적어 돌려준다.
#
# Inputs:
#   platform_path  str      repo root (필수)
#   targets        Plane*   AMv1 RollerPath 의 targets — 자동 방향·자동 위치용
#   robot_base     Plane    평면을 직접 줄 때. 최우선
#   base_pt        Point    베이스 원점 (Rhino 에서 점을 찍어 물린다)
#   base_dir       Curve    바라보는 방향 (Rhino 에서 선을 그어 물린다)
#                           **Curve 다.** Param_Line 은 Rhino 객체를 참조하지
#                           못해 값이 박히고, 선을 돌려도 방향이 안 바뀐다
#   pin_tops       Point3d* 핀 상단 — 몰드 발자국과의 겹침을 보기 위해 (list)
#
# Outputs:
#   plane      로봇 베이스 평면. Robot·Play·Check 에 **같은 것을** 물릴 것
#   circle     베이스 원통 발자국 (반경 630 mm 실측) — 배치 확인용
#   overlap    몰드 영역과의 겹침 깊이 (mm). 양수면 세울 수 없는 자리다
#   info       무엇으로 정했는지 + 겹침 판정

import sys
import os

import Rhino.Geometry as rg


_src = os.path.join(platform_path, "adaptive_mold", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

_norm = os.path.normcase(os.path.normpath(_src))
for _name in list(sys.modules.keys()):
    _p = getattr(sys.modules.get(_name), "__file__", None)
    if _p and os.path.normcase(os.path.normpath(_p)).startswith(_norm):
        del sys.modules[_name]

import robot as rb


tgts = [t for t in (targets or []) if t is not None]
pins = [p for p in (pin_tops or []) if p is not None]

plane, src = rb.resolve_base_plane(
    robot_base=robot_base, base_pt=base_pt, base_dir=base_dir,
    targets=tgts if tgts else None)

circle = rg.Circle(rg.Plane(plane.Origin, rg.Vector3d.ZAxis),
                   rb.BASE_RADIUS_MM)

# 겹침은 여기서 한 번만 본다 — IK 는 간섭을 모르므로, 겹치는 자리에서도
# 팔이 몰드를 통과해 닿는 것을 "도달 성공"으로 센다.
overlap = rb.base_overlap(plane, pins) if pins else None

lines = [
    "AMv1 Base",
    "=" * 44,
    "원점:        ({:.0f}, {:.0f}, {:.0f})".format(
        plane.Origin.X, plane.Origin.Y, plane.Origin.Z),
    "방향:        ({:+.3f}, {:+.3f})".format(plane.XAxis.X, plane.XAxis.Y),
    "출처:        {}".format(src),
    "발자국:      반경 {:.0f} mm (실측)".format(rb.BASE_RADIUS_MM),
]

if overlap is None:
    lines.append("몰드 겹침:   판정 못 함 — pin_tops 를 연결하세요")
elif overlap > 0:
    lines.append("몰드 겹침:   ** {:.0f} mm 겹친다 — 세울 수 없는 자리다".format(
        overlap))
    lines.append("             IK 는 간섭을 모르므로 팔이 몰드를 통과해 닿는")
    lines.append("             것을 '도달 성공'으로 센다. 베이스를 옮길 것")
else:
    lines.append("몰드 겹침:   없음 — {:.0f} mm 여유".format(-overlap))

lines.append("")
lines.append("이 plane 을 Robot 의 robot_base, Play·Check 에 **같이** 물릴 것.")
lines.append("각자 따로 정하면 오류 없이 서로 다른 자리를 계산한다.")

info = "\n".join(lines)

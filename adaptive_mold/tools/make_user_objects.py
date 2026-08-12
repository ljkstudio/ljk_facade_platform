#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""컴포넌트를 LJKSTUDIO 탭의 User Object(.ghuser)로 등록한다.

**왜 User Object인가:** GhPython 컴포넌트의 `Icon_24x24`는 읽기 전용이라 캔버스
위의 컴포넌트에 아이콘을 직접 넣을 수 없다(실측). 리본 탭에 올리고 아이콘을
붙이는 정식 경로는 `GH_UserObject`이고, 그쪽의 `Icon`은 쓰기 가능하다.

**아이콘은 코드로 그린다.** 외부 이미지 파일을 두면 저장소와 어긋나기 시작한다.
GDI+로 24x24를 그리므로 이 파일이 곧 아이콘의 정본이다.

**주의 — 스냅샷이다.** .ghuser 는 컴포넌트(코드 포함)를 복사해 담는다.
`gh_scripts/*.py` 를 고치면 이 도구를 다시 돌려야 리본의 것도 갱신된다.
캔버스의 것은 apply 계열 도구로, 리본의 것은 이 도구로 — 경로가 둘이다.

선결 조건: Rhino 8 + `mcpstart`, 그리고 대상 컴포넌트가 캔버스에 있어야 한다.

사용:
    python adaptive_mold/tools/make_user_objects.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


TAB = "LJKSTUDIO"

# (닉네임, 서브카테고리, 아이콘 그리기 함수 이름)
# 번호를 붙여야 리본에서 파이프라인 순서대로 정렬된다 (GH는 알파벳순).
COMPONENTS = [
    ("AMv1 Inspect",    "1 Mold",     "draw_mold"),
    ("AMv1 RollerPath", "2 Toolpath", "draw_path"),
    ("AMv1 PathFrames", "3 Display",  "draw_frames"),
    ("AMv1 Robot",      "4 Robot",    "draw_robot"),
]


# 브리지 안(IronPython)에서 실행되는 아이콘 드로잉 + 등록 코드.
# 비ASCII를 넣지 않는다 — 응답 JSON 인코더가 죽는다.
BRIDGE_CODE = u'''
import System
import System.Drawing as sd
import System.Drawing.Drawing2D as d2
import Grasshopper as ghk

TAB = "{tab}"
SPEC = {spec}

INK = sd.Color.FromArgb(255, 40, 44, 52)
ACC = sd.Color.FromArgb(255, 200, 60, 50)
SOFT = sd.Color.FromArgb(255, 130, 140, 150)


def _canvas():
    bmp = sd.Bitmap(24, 24)
    g = sd.Graphics.FromImage(bmp)
    g.SmoothingMode = d2.SmoothingMode.AntiAlias
    g.Clear(sd.Color.Transparent)
    return bmp, g


def draw_mold():
    """핀 격자 위에 곡면 — 몰드."""
    bmp, g = _canvas()
    pen = sd.Pen(INK, 1.6)
    g.DrawArc(pen, 1.0, 4.0, 22.0, 16.0, 200.0, 140.0)     # 곡면
    pin = sd.Pen(SOFT, 1.5)
    xs = [4, 8, 12, 16, 20]
    tops = [12, 9, 8, 9, 12]
    for x, ty in zip(xs, tops):
        g.DrawLine(pin, float(x), float(ty), float(x), 21.0)
    g.Dispose()
    return bmp


def draw_path():
    """왕복 지그재그 경로 + 롤러."""
    bmp, g = _canvas()
    pen = sd.Pen(ACC, 1.7)
    pts = System.Array[sd.PointF]([
        sd.PointF(3, 6), sd.PointF(20, 6),
        sd.PointF(20, 12), sd.PointF(3, 12),
        sd.PointF(3, 18), sd.PointF(20, 18)])
    g.DrawLines(pen, pts)
    rp = sd.Pen(INK, 1.6)
    g.DrawEllipse(rp, 13.0, 1.0, 7.0, 7.0)                 # 롤러
    g.Dispose()
    return bmp


def draw_frames():
    """경로 위의 법선 프레임 — 표시용."""
    bmp, g = _canvas()
    pen = sd.Pen(INK, 1.6)
    g.DrawCurve(pen, System.Array[sd.PointF]([
        sd.PointF(2, 17), sd.PointF(8, 13), sd.PointF(16, 13), sd.PointF(22, 17)]))
    np_ = sd.Pen(ACC, 1.5)
    np_.EndCap = d2.LineCap.ArrowAnchor
    for x, y in ((5, 15), (11, 13), (18, 14)):
        g.DrawLine(np_, float(x), float(y), float(x), float(y - 9))
    g.Dispose()
    return bmp


def draw_robot():
    """3절 로봇암."""
    bmp, g = _canvas()
    base = sd.Pen(INK, 2.0)
    g.DrawLine(base, 4.0, 21.0, 4.0, 15.0)
    g.DrawLine(base, 4.0, 15.0, 12.0, 6.0)
    g.DrawLine(base, 12.0, 6.0, 20.0, 10.0)
    jp = sd.Pen(ACC, 1.6)
    for x, y in ((4, 15), (12, 6), (20, 10)):
        g.DrawEllipse(jp, float(x - 2), float(y - 2), 4.0, 4.0)
    g.FillRectangle(sd.SolidBrush(INK), 1, 21, 7, 2)
    g.Dispose()
    return bmp


DRAW = {{"draw_mold": draw_mold, "draw_path": draw_path,
        "draw_frames": draw_frames, "draw_robot": draw_robot}}

folder = ghk.Folders.DefaultUserObjectFolder
lines.append("folder: %s" % folder)

found = {{}}
for _d in [d for d in ghk.Instances.DocumentServer]:
    for _o in _d.Objects:
        found[_o.NickName] = _o

for nick, sub, fn in SPEC:
    comp = found.get(nick)
    if comp is None:
        lines.append("%-18s NOT ON CANVAS" % nick)
        continue

    comp.Category = TAB
    comp.SubCategory = sub

    uo = ghk.Kernel.GH_UserObject()
    uo.Icon = DRAW[fn]()
    uo.SetDataFromObject(comp)

    # SetDataFromObject 는 Data만 채우고 Description은 비워둔다(실측).
    # 여기를 채우지 않으면 리본에 이름 없이 뜨고 카테고리도 안 잡힌다.
    uo.Description.Name = nick
    uo.Description.NickName = comp.NickName
    uo.Description.Category = TAB
    uo.Description.SubCategory = sub
    if not uo.Description.Description:
        uo.Description.Description = nick
    uo.Exposure = ghk.Kernel.GH_Exposure.primary

    # **BaseGuid 를 설정하지 않으면 SaveToFile 이 조용히 False 를 돌려준다**(실측).
    # 예외도 메시지도 없다. 어떤 컴포넌트 타입을 되살릴지 모르기 때문.
    # GhPython 컴포넌트는 클래스 GUID가 같으므로 넷이 같은 BaseGuid를 갖는다 —
    # 정상이다. 개별 식별은 uo.Guid 가 한다.
    uo.BaseGuid = comp.ComponentGuid

    uo.CreateDefaultPath(False)
    ok = uo.SaveToFile()
    size = 0
    if uo.Path and System.IO.File.Exists(uo.Path):
        size = System.IO.FileInfo(uo.Path).Length
    lines.append("%-18s %-11s saved=%s %d bytes  %s" % (
        nick, sub, ok, size, uo.Path))

# 리본 갱신 방법이 있는지 확인 (없으면 재시작이 필요하다)
srv = ghk.Instances.ComponentServer
names = sorted(set(m.Name for m in srv.GetType().GetMethods()
                   if "User" in m.Name or "Refresh" in m.Name
                   or "Load" in m.Name))
lines.append("ComponentServer 후보 메서드: %s" % ", ".join(names))
'''


def main():
    spec = repr([(a, b, c) for a, b, c in COMPONENTS])
    code = BRIDGE_CODE.format(tab=TAB, spec=spec)
    with Bridge() as b:
        print(remote(b, code))
    return 0


if __name__ == "__main__":
    sys.exit(main())

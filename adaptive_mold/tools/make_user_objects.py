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

**`ComponentServer.LoadExternalFiles()` 를 호출하지 말 것.** Grasshopper가
UserObjects 폴더 변경을 스스로 반영하므로 불필요하고, 호출하면 **모든 User
Object가 새 GUID로 다시 등록되어 팔레트에 중복으로 쌓인다**(실측: LJKS 6 → 12,
사용자 소유 항목까지 복제됨).

**중복은 세션 안에서 지울 수 없다 (실측).** `ClearStaleUserObjects()` 는 듣지
않고, `ObjectProxies`(List)에서 `Remove` 하면 그 순간엔 줄지만 잠시 뒤 다시
2배로 돌아온다(12초 간격 3회 관찰에서 12개로 고정). 팔레트가 별도 레지스트리를
갖고 다시 채우는 것으로 보인다.
→ **디스크가 정본이다.** 파일이 맞으면 Rhino를 다시 켜면 정상으로 돌아온다.
이 도구의 정리 단계는 "가능하면 치우는" 보조 수단이고 보장 수단이 아니다.

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


# 이 PC에는 이미 LJKS 탭이 있고 사용자 User Object 2개가 들어 있다.
# 별도 탭을 만들면 리본에 비슷한 이름이 둘로 보이므로 여기에 합친다.
TAB = "LJKS"

# (닉네임, 서브카테고리, 아이콘 그리기 함수 이름)
# 전부 한 그룹(AMv1)에 둔다 — 개수가 적어 나누면 리본이 오히려 흩어진다.
# 늘어나면 그때 쪼갠다.
SUB = "AMv1"
COMPONENTS = [
    ("AMv1 Inspect",    SUB, "draw_mold"),
    ("AMv1 RollerPath", SUB, "draw_path"),
    ("AMv1 PathFrames", SUB, "draw_frames"),
    ("AMv1 Robot",      SUB, "draw_robot"),
    ("AMv1 Play",       SUB, "draw_play"),
    ("AMv1 Base",       SUB, "draw_base"),
    ("AMv1 Check",      SUB, "draw_check"),
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


def draw_play():
    """재생 삼각형 + 움직임 호."""
    bmp, g = _canvas()
    tri = System.Array[sd.PointF]([
        sd.PointF(7, 3), sd.PointF(7, 21), sd.PointF(20, 12)])
    g.FillPolygon(sd.SolidBrush(ACC), tri)
    mp = sd.Pen(SOFT, 1.6)
    for x in (1.0, 4.0):                                   # 속도선
        g.DrawLine(mp, x, 8.0, x, 16.0)
    g.Dispose()
    return bmp


def draw_base():
    """베이스 원 + 방향 화살 — 위치와 방향을 정한다는 뜻."""
    bmp, g = _canvas()
    p = sd.Pen(SOFT, 1.8)
    g.DrawEllipse(p, 3.0, 8.0, 12.0, 12.0)                 # 발자국
    ap = sd.Pen(ACC, 2.0)
    g.DrawLine(ap, 9.0, 14.0, 21.0, 6.0)                   # 방향
    g.FillEllipse(sd.SolidBrush(ACC), 7.5, 12.5, 3.0, 3.0)  # 원점
    g.Dispose()
    return bmp


def draw_check():
    """체크 표시 + 눈금 — 판정한다는 뜻."""
    bmp, g = _canvas()
    p = sd.Pen(ACC, 2.6)
    g.DrawLine(p, 4.0, 13.0, 9.0, 18.0)
    g.DrawLine(p, 9.0, 18.0, 20.0, 5.0)
    sp = sd.Pen(SOFT, 1.4)
    for y in (20.0, 22.0):                                 # 여유 눈금
        g.DrawLine(sp, 3.0, y, 21.0, y)
    g.Dispose()
    return bmp


DRAW = {{"draw_mold": draw_mold, "draw_path": draw_path,
        "draw_frames": draw_frames, "draw_robot": draw_robot,
        "draw_play": draw_play, "draw_base": draw_base,
        "draw_check": draw_check}}

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

# ── 프록시 정리 ──────────────────────────────────────────
#
# 파일을 다시 저장하면 Grasshopper의 폴더 감시가 **새 프록시를 추가**한다.
# 교체가 아니라 추가라서, 카테고리를 바꿔 저장하면 옛 항목이 팔레트에 남아
# 같은 이름이 둘로 보인다. ClearStaleUserObjects() 는 이것을 정리하지 못한다.
#
# 그래서 의도한 (Category, SubCategory) 를 가진 쪽만 남기고 지운다.
# 이름이 같은 옛 프록시는 내용이 같거나 구버전이므로 버려도 잃을 것이 없다.

srv = ghk.Instances.ComponentServer
coll = srv.ObjectProxies
want = dict((nick, sub) for nick, sub, fn in SPEC)

mine = []
for p in coll:
    try:
        if p.Desc.Name in want:
            mine.append(p)
    except Exception:
        pass

keep = {{}}
drop = []
for p in mine:
    nm = p.Desc.Name
    ok = (p.Desc.Category == TAB and p.Desc.SubCategory == want[nm])
    if ok and nm not in keep:
        keep[nm] = p
    else:
        drop.append(p)

# 의도한 것을 못 찾았으면(아직 감시가 반영 안 됨) 지우지 않는다 — 다 날리면 안 된다
for p in list(drop):
    if p.Desc.Name not in keep:
        drop.remove(p)

for p in drop:
    try:
        coll.Remove(p)
    except Exception as ex:
        lines.append("프록시 제거 실패 %s: %s" % (p.Desc.Name, ex))

lines.append("프록시 정리: 유지 %d, 제거 %d" % (len(keep), len(drop)))

final = []
for p in coll:
    try:
        if p.Desc.Category == TAB:
            final.append("%s / %s" % (p.Desc.SubCategory, p.Desc.Name))
    except Exception:
        pass
lines.append("%s 탭 %d개:" % (TAB, len(final)))
for f in sorted(final):
    lines.append("  %s" % f)
'''


def main():
    spec = repr([(a, b, c) for a, b, c in COMPONENTS])
    code = BRIDGE_CODE.format(tab=TAB, spec=spec)
    with Bridge() as b:
        print(remote(b, code))
    return 0


if __name__ == "__main__":
    sys.exit(main())

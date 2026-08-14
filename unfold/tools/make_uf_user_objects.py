#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""UFv1 컴포넌트를 LJKS 탭의 `Unfold` 그룹에 User Object(.ghuser)로 올린다.

    python unfold/tools/make_uf_user_objects.py

`adaptive_mold/tools/make_user_objects.py` 와 같은 경로다. 다른 것은 탭 안의
그룹(SubCategory)이 `AMv1` 이 아니라 `Unfold` 라는 것뿐이다.

**주의 — `.ghuser` 는 스냅샷이다.** 컴포넌트를 코드까지 통째로 복사해 담는다.
`gh_scripts/*.py` 를 고치면 경로가 **둘로 갈린다**:

    캔버스의 것  → build_uf_components.py  (+ apply_uf_param_docs.py)
    리본의 것    → 이 도구

한쪽만 돌리면 팔레트에서 꺼낸 컴포넌트가 옛 코드로 돈다. 증상이 "저장소는
고쳤는데 안 고쳐졌다"로 나타나는데, 캔버스에 이미 있던 것은 멀쩡해서 원인을
찾기가 특히 어렵다.

**`ComponentServer.LoadExternalFiles()` 를 부르지 말 것** (실측, AMv1). 불필요하고,
부르면 모든 User Object 가 새 GUID 로 재등록되어 팔레트에 중복으로 쌓인다
(LJKS 6 → 12, 사용자 소유 항목까지 복제). 중복은 세션 안에서 지울 수 없다 —
**디스크가 정본이므로** 파일이 맞으면 Rhino 를 다시 켜면 정상으로 돌아온다.

**아이콘은 코드로 그린다.** 외부 이미지 파일을 두면 저장소와 어긋나기 시작한다.
GDI+ 로 24x24 를 그리므로 이 파일이 곧 아이콘의 정본이다.

선결 조건: Rhino 8 + `mcpstart`, 그리고 두 컴포넌트가 캔버스에 있을 것.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))

from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# AMv1 과 같은 탭에 둔다. 탭을 따로 만들면 리본에 비슷한 이름이 둘로 보인다.
TAB = "LJKS"
SUB = "Unfold"

COMPONENTS = [
    ("UFv1 Material", SUB, "draw_material"),
    ("UFv1 Flatten",  SUB, "draw_flatten"),
]


# 브리지 안(IronPython 2.7)에서 도는 코드. **비ASCII 를 넣지 않는다** —
# 응답 JSON 인코더가 죽는다. 한글이 필요하면 파일 경유로 주고받아야 한다.
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


def draw_material():
    """판재 단면 + 양방향 화살 — 늘어나는 재료라는 뜻."""
    bmp, g = _canvas()
    stretch = sd.Pen(ACC, 1.6)
    stretch.StartCap = d2.LineCap.ArrowAnchor
    stretch.EndCap = d2.LineCap.ArrowAnchor
    g.DrawLine(stretch, 3.0, 6.0, 21.0, 6.0)               # 연신
    g.FillRectangle(sd.SolidBrush(INK), 3, 12, 18, 4)      # 판재 단면
    tp = sd.Pen(SOFT, 1.3)
    g.DrawLine(tp, 3.0, 19.0, 3.0, 22.0)                   # 두께 눈금
    g.DrawLine(tp, 21.0, 19.0, 21.0, 22.0)
    g.DrawLine(tp, 3.0, 20.5, 21.0, 20.5)
    g.Dispose()
    return bmp


def draw_flatten():
    """곡면이 아래로 펴져 재단 외곽선이 된다."""
    bmp, g = _canvas()
    arc = sd.Pen(INK, 1.8)
    g.DrawArc(arc, 2.0, 2.0, 20.0, 12.0, 200.0, 140.0)     # 곡면
    dn = sd.Pen(SOFT, 1.5)
    dn.EndCap = d2.LineCap.ArrowAnchor
    g.DrawLine(dn, 12.0, 10.0, 12.0, 15.0)                 # 편다
    cut = sd.Pen(ACC, 1.6)
    cut.DashStyle = d2.DashStyle.Dash                      # 재단선
    g.DrawRectangle(cut, 3, 17, 18, 5)
    g.Dispose()
    return bmp


DRAW = {{"draw_material": draw_material, "draw_flatten": draw_flatten}}

folder = ghk.Folders.DefaultUserObjectFolder
lines.append("folder: %s" % folder)

found = {{}}
for _d in [d for d in ghk.Instances.DocumentServer]:
    for _o in _d.Objects:
        found[_o.NickName] = _o

for nick, sub, fn in SPEC:
    comp = found.get(nick)
    if comp is None:
        lines.append("%-14s NOT ON CANVAS" % nick)
        continue

    # 새 Script 컴포넌트에서 Category/SubCategory 가 쓰기 가능한지는 미검증이었다.
    # 막히면 그 사실을 적고 계속 간다 — 리본 등록은 uo.Description 쪽이 정한다.
    try:
        comp.Category = TAB
        comp.SubCategory = sub
        cat_ok = "comp.Category=ok"
    except Exception as ex:
        cat_ok = "comp.Category 쓰기 실패(%s)" % type(ex).__name__

    uo = ghk.Kernel.GH_UserObject()
    uo.Icon = DRAW[fn]()
    uo.SetDataFromObject(comp)

    # SetDataFromObject 는 Data 만 채우고 Description 은 비워 둔다(실측, AMv1).
    # 여기를 채우지 않으면 리본에 이름 없이 뜨고 그룹도 안 잡힌다.
    uo.Description.Name = nick
    uo.Description.NickName = comp.NickName
    uo.Description.Category = TAB
    uo.Description.SubCategory = sub
    if not uo.Description.Description:
        uo.Description.Description = nick
    uo.Exposure = ghk.Kernel.GH_Exposure.primary

    # **BaseGuid 가 없으면 SaveToFile 이 조용히 False 를 돌려준다**(실측, AMv1).
    # 예외도 메시지도 없다 — 어떤 컴포넌트 타입을 되살릴지 모르기 때문이다.
    uo.BaseGuid = comp.ComponentGuid

    uo.CreateDefaultPath(False)
    ok = uo.SaveToFile()
    size = 0
    if uo.Path and System.IO.File.Exists(uo.Path):
        size = System.IO.FileInfo(uo.Path).Length
    lines.append("%-14s %-8s saved=%s %d bytes  %s  [%s]"
                 % (nick, sub, ok, size, uo.Path, cat_ok))

    # 저장했다고 믿지 않는다 — 되읽어 컴포넌트 타입과 코드 길이를 센다.
    # 스냅샷이 옛 코드를 담고 있으면 팔레트에서 꺼낸 것만 다르게 돈다.
    if ok and size:
        try:
            back = ghk.Kernel.GH_UserObject(uo.Path)
            obj = back.InstantiateObject()
            code = None
            try:
                got, code = obj.TryGetSource()
            except Exception:
                code = getattr(obj, "Code", None)
            lines.append("  되읽기: %s  code=%s자"
                         % (obj.GetType().Name,
                            len(code) if code else "읽지 못함"))
        except Exception as ex:
            lines.append("  되읽기 실패: %r" % (ex,))

# ── 프록시 정리 ──────────────────────────────────────────
#
# 파일을 다시 저장하면 Grasshopper 의 폴더 감시가 **새 프록시를 추가**한다.
# 교체가 아니라 추가라서, 그룹을 바꿔 저장하면 옛 항목이 팔레트에 남아 같은
# 이름이 둘로 보인다. 의도한 (Category, SubCategory) 쪽만 남긴다.
# **못 찾았으면 아무것도 지우지 않는다** — 다 날리는 것보다 중복이 낫다.

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
    good = (p.Desc.Category == TAB and p.Desc.SubCategory == want[nm])
    if good and nm not in keep:
        keep[nm] = p
    else:
        drop.append(p)

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
        text = remote(b, code)
    print(text)
    return 1 if ("NOT ON CANVAS" in text or "saved=False" in text) else 0


if __name__ == "__main__":
    sys.exit(main())

#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rhino 프로세스에 남아 있는 재생 컨듀잇을 끈다.

    python adaptive_mold/tools/teardown_conduits.py          # 목록만
    python adaptive_mold/tools/teardown_conduits.py --kill   # 끈다

**증상:** AMv1 컴포넌트를 지웠는데(또는 다른 문서를 열었는데) 로봇암·경로선이
뷰포트에 계속 그려진다. GH 문서에는 그런 컴포넌트가 없다.

**원인:** `AMv1 Play` 는 계산을 한 번만 하고 그림은 `Rhino.Display.DisplayConduit`
으로 그린다. 컨듀잇과 타이머는 솔루션 사이에 살아남아야 하므로
`scriptcontext.sticky` 에 담기는데, **sticky 는 GH 문서가 아니라 Rhino 프로세스에
붙어 있다.** 그래서 컴포넌트를 지워도 컨듀잇은 계속 등록된 채 남아 마지막
프레임을 영원히 그린다. 정리(`teardown`)는 그 컴포넌트가 **다시 실행될 때만**
돌기 때문에, 컴포넌트가 사라지면 정리할 주체도 같이 사라진다.

**같이 새는 것 하나 더:** 재생 중에는 GH 프리뷰를 꺼 두는데(움직이는 그림 위에
고정된 프리뷰가 겹치면 틀린 그림이 된다), 그 "끈 것을 되돌리는" 일도 teardown 의
몫이다. 컨듀잇만 끄고 이걸 빠뜨리면 **화면에서 사라져야 할 것이 아니라 보여야
할 것이 안 보이는** 상태가 남는다.

**재발 조건:** 재생을 켜 둔 채 컴포넌트를 지우거나, 문서를 닫거나, 다른 `.gh`
문서로 갈아탈 때마다. Rhino 를 다시 켜면 없어진다(프로세스 수명이라서).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser(r"~\.claude\skills\rhino-bridge\scripts"))

from rhino_bridge import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BODY = u'''
import scriptcontext as sc

kill = KILLFLAG
found = 0

for k in sorted(sc.sticky.keys()):
    v = sc.sticky.get(k)
    if not isinstance(v, dict) or "conduit" not in v:
        continue
    found += 1
    c = v.get("conduit")
    t = v.get("timer")
    hp = v.get("hidden_prev") or []
    lines.append("%s" % k)
    lines.append("   conduit %s Enabled=%s / timer %s / 프리뷰 끈 객체 %d개"
                 % (type(c).__name__, getattr(c, "Enabled", "?"),
                    "없음" if t is None else "Enabled=%s" % getattr(t, "Enabled", "?"),
                    len(hp)))
    if not kill:
        continue

    try:
        c.Enabled = False
        lines.append("   컨듀잇을 껐다")
    except Exception as ex:
        lines.append("   컨듀잇 끄기 실패: %r" % (ex,))
    if t is not None:
        try:
            t.Stop(); t.Dispose()
            lines.append("   타이머를 멈췄다")
        except Exception as ex:
            lines.append("   타이머 정리 실패: %r" % (ex,))

    # **끈 프리뷰를 되돌린다.** 컨듀잇만 끄고 여기를 빠뜨리면 보여야 할 것이
    # 계속 숨어 있게 된다 — 증상이 반대로 나타나 원인을 찾기 어렵다.
    back = 0
    for obj, was in hp:
        try:
            obj.Hidden = was
            back += 1
        except Exception:
            pass
    if hp:
        lines.append("   프리뷰 %d/%d개 되돌렸다" % (back, len(hp)))

    sc.sticky.pop(k, None)
    lines.append("   sticky 에서 제거했다")

if not found:
    lines.append("남아 있는 재생 컨듀잇이 없다")

for d in [x for x in gh.Instances.DocumentServer]:
    try:
        d.ExpirePreview(True)
    except Exception:
        pass
Rhino.RhinoDoc.ActiveDoc.Views.Redraw()
lines.append("")
lines.append("컨듀잇 %d개 %s" % (found, "정리함" if kill else "발견 (끄려면 --kill)"))
'''


def main(argv):
    kill = "--kill" in argv
    body = BODY.replace("KILLFLAG", "True" if kill else "False")
    with Bridge(timeout=180) as b:
        print(remote(b, body))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""`unfold/gh_scripts/param_docs.py` 의 설명을 캔버스 컴포넌트에 밀어넣는다.

    python unfold/tools/apply_uf_param_docs.py
    python unfold/tools/apply_uf_param_docs.py --check    # 쓰지 않고 대조만

정본은 저장소이고 캔버스는 단방향 반영이다.

**설명은 두 경로로 사라진다. 둘 다 실측이다.**

  ① `.gh` 가 설명을 보관하지 못한다. 저장하고 Rhino 를 다시 켜면 비어 있다
     (AMv1 에서 125개 중 120개 소실). 파라미터 개수·배선·코드는 살아남는다.
     → **문서를 열 때마다 이 도구를 한 번 돌리는 것이 정상 절차다.**

  ② 코드를 push 하면 그 컴포넌트의 설명이 지워진다. `build_uf_components.py`
     는 파라미터를 지우고 다시 만들기 때문에 설명이 기본값으로 돌아간다.
     → **빌더 뒤에는 항상 이 도구를 이어서 돌린다.**

**이 손실이 특히 위험한 이유:** 코드 push 는 성공으로 보고되고, 캔버스도 정상이며,
계산 결과도 맞는다. 잃은 것은 마우스를 올렸을 때만 보이므로 며칠 뒤에 발견된다.
로그에 아무 흔적이 없다 — 그래서 `--check` 로 상시 대조한다. 0 차이가 정상 상태다.

**한글을 브리지 JSON 에 태우지 않는다.** IronPython 2.7 의 json 인코더가
비ASCII 에서 죽으므로, `ensure_ascii=True`(기본)로 임시 파일에 덤프해
(\\uXXXX 이스케이프 = 순수 ASCII 파일) 브리지 쪽이 그 파일을 읽게 한다.

선결 조건: Rhino 8 이 떠 있고 명령창에 `mcpstart` 로 포트 1999 가 열려 있을 것.
"""

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))

sys.path.insert(0, os.path.join(REPO, "adaptive_mold", "tools"))
sys.path.insert(0, os.path.join(REPO, "unfold", "gh_scripts"))

from param_docs import PARAM_DOCS  # noqa: E402
from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BRIDGE_CODE = u'''
import io, json


def _tip(p):
    """`ToolTip` 은 새 Script 파라미터에만 있다 — 구형에는 없으므로 없으면 통과."""
    try:
        return p.ToolTip
    except Exception:
        return None


def _set_tip(p, text):
    try:
        p.ToolTip = text
    except Exception:
        pass          # 구형 파라미터. Description 만으로 충분하다


f = io.open(r"{spec}", "r", encoding="utf-8")
try:
    spec = json.loads(f.read())
finally:
    f.close()

check_only = {check}

for nick in spec:
    docs = spec[nick]
    target = None
    parent = None
    for _doc in [d for d in gh.Instances.DocumentServer]:
        for _obj in _doc.Objects:
            if _obj.NickName == nick:
                target = _obj
                parent = _doc
    if target is None:
        lines.append("NOT_FOUND: %s — 캔버스에 그 이름의 컴포넌트가 없다" % nick)
        continue

    changed = 0
    same = 0
    missing = []
    for kind, params in (("inputs", target.Params.Input),
                         ("outputs", target.Params.Output)):
        want = docs.get(kind, {{}})
        seen = []
        for p in params:
            seen.append(p.NickName)
            if p.NickName not in want:
                continue
            text = want[p.NickName]
            tip = _tip(p)
            if p.Description == text and (tip is None or tip == text):
                same += 1
                continue
            changed += 1
            if not check_only:
                # **둘 다 채운다.** 새 Script 컴포넌트의 파라미터에는
                # `Description` 말고 `ToolTip` 이 따로 있고(구형 GhPython 에는
                # 없다), 화면이 어느 쪽을 그리는지는 밖에서 단정할 수 없다.
                # 둘을 채우는 비용은 없고, 한쪽만 채웠다가 안 뜨면 원인이
                # 여기라는 것을 알아내는 데 시간이 든다.
                p.Description = text
                _set_tip(p, text)
        for nm in want:
            if nm not in seen:
                missing.append("%s/%s" % (kind, nm))

    lines.append("%-14s %s %d개 (이미 같음 %d개)"
                 % (nick, "차이" if check_only else "적용", changed, same))
    if missing:
        lines.append("  설명은 있는데 파라미터가 없다: %s" % ", ".join(missing))
    if not check_only and changed:
        target.Params.OnParametersChanged()
        target.ExpireSolution(True)
        parent.NewSolution(False)

    # **넣었다고 믿지 않는다.** 되읽어 대조한다 — 새 Script 컴포넌트의
    # 파라미터가 Description 을 실제로 들고 있는지는 여기서만 확인된다.
    if not check_only:
        bad = 0
        tips = 0
        for kind, params in (("inputs", target.Params.Input),
                             ("outputs", target.Params.Output)):
            want = docs.get(kind, {{}})
            for p in params:
                if p.NickName not in want:
                    continue
                if p.Description != want[p.NickName]:
                    bad += 1
                if _tip(p) == want[p.NickName]:
                    tips += 1
        lines.append("  되읽기 검증: %s (ToolTip 도 채워진 것 %d개)"
                     % ("OK" if bad == 0 else "FAIL %d개가 안 남았다" % bad, tips))
'''


def main(argv):
    check = "--check" in argv

    spec_path = os.path.join(tempfile.gettempdir(), "uf_param_docs.json")
    with io.open(spec_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(PARAM_DOCS, indent=1))   # ensure_ascii=True → 순수 ASCII

    total = sum(len(v.get("inputs", {})) + len(v.get("outputs", {}))
                for v in PARAM_DOCS.values())
    print("정본: unfold/gh_scripts/param_docs.py  (설명 %d개)" % total)

    code = BRIDGE_CODE.format(spec=spec_path.replace("\\", "\\\\"),
                              check="True" if check else "False")
    with Bridge() as b:
        text = remote(b, code)
    print(text)
    return 1 if ("NOT_FOUND" in text or "FAIL" in text) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

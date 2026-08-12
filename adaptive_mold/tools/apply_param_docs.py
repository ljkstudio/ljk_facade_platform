#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""gh_components/param_docs.py의 설명을 캔버스 컴포넌트에 밀어넣는다.

정본은 저장소이고 캔버스는 단방향 반영이다.

**처음 생각보다 강한 이유가 실측으로 나왔다 — `.gh` 는 설명을 보관하지 못한다.**
설명 85개를 적용하고 저장한 뒤 Rhino를 재시작해 다시 열었더니 **81개가 사라져
있었다**(Inspect 32 / RollerPath 21 / Robot 14 / PathFrames 14).
Category·SubCategory 도 클래스 기본값(Maths/Script)으로 돌아온다.
파라미터 개수·배선·코드는 살아남는다.

그래서 **문서를 열 때마다 이 도구를 한 번 돌리는 것이 정상 절차다.**
편의 도구가 아니라 필수 절차다.
(2026-08-13 재확인: Rhino를 새로 켠 뒤 81개가 다시 비어 있었다.)

**코드를 밀어넣으면 그 컴포넌트의 설명이 지워진다** (실측 2026-08-13).
`comp.Code = ...` 직전에 `--check`가 0 차이였던 컴포넌트가 push 직후 14개 차이로
돌아왔고, **코드를 넣은 컴포넌트만** 그랬다. GhPython이 코드를 파싱해 파라미터를
정비하면서 Description을 기본값으로 되돌리는 것으로 보인다.
→ `gh-set-code` 뒤에는 **항상** 이 도구를 다시 돌린다.

**한글을 브리지 JSON에 태우지 않는다.** IronPython 2.7의 json 인코더가
비ASCII에서 죽으므로, 설명을 `ensure_ascii=True`로 임시 파일에 덤프해
(\\uXXXX 이스케이프 = 순수 ASCII 파일) 브리지 쪽이 그 파일을 읽게 한다.

선결 조건: Rhino 8이 떠 있고 명령창에 `mcpstart`로 포트 1999가 열려 있어야 한다.

사용:
    python adaptive_mold/tools/apply_param_docs.py
    python adaptive_mold/tools/apply_param_docs.py --check   # 쓰지 않고 대조만
"""

import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "gh_components"))

from param_docs import PARAM_DOCS  # noqa: E402
from rhino_cli import Bridge, remote  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


BRIDGE_CODE = u'''
import io, json
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
        lines.append("NOT_FOUND: %s" % nick)
        continue

    changed = 0
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
            if p.Description == text:
                continue
            changed += 1
            if not check_only:
                p.Description = text
        for nm in want:
            if nm not in seen:
                missing.append("%s/%s" % (kind, nm))

    lines.append("%s: %s %d개" % (nick, "차이" if check_only else "적용", changed))
    if missing:
        lines.append("  설명은 있는데 파라미터가 없음: %s" % ", ".join(missing))
    if not check_only and changed:
        target.Params.OnParametersChanged()
        target.ExpireSolution(True)
        parent.NewSolution(False)
'''


def main(argv):
    check = "--check" in argv

    spec_path = os.path.join(tempfile.gettempdir(), "am_param_docs.json")
    # ensure_ascii=True(기본) → 파일이 순수 ASCII가 되어 IronPython이 안전하게 읽는다
    with io.open(spec_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(PARAM_DOCS, indent=1))

    total = sum(len(v.get("inputs", {})) + len(v.get("outputs", {}))
                for v in PARAM_DOCS.values())
    print("정본: gh_components/param_docs.py  (설명 {}개)".format(total))

    code = BRIDGE_CODE.format(spec=spec_path.replace("\\", "\\\\"),
                              check="True" if check else "False")
    with Bridge() as b:
        print(remote(b, code))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

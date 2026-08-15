#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""픽스처의 `expected`·`summary` 가 불변인지 확인한다.

파이썬 쪽을 고칠 때마다 "계산을 건드리지 않았다"를 증명하는 게이트다.
진단 출력·메시지·지문을 늘리는 것은 허용되지만, 계산 결과는 한 글자도
바뀌면 안 된다.

    python adaptive_mold/tools/check_fixture_invariance.py --save   # 기준 저장
    python adaptive_mold/tools/check_fixture_invariance.py          # 대조

`expected` 에 키가 **늘어나는** 것은 정상이다(진단 추가). 그래서 기본 대조는
"기준에 있던 키가 그대로인가"만 본다. 기준에 없던 키가 생기면 목록으로
보여주고, 사람이 확인한 뒤 `--save` 로 기준을 갱신한다.

    --strict  기준과 완전히 같아야 통과 (키가 늘어나도 실패)
"""

import argparse
import glob
import json
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(REPO, "plugin", "fixtures")
BASELINE = os.path.join(FIXTURES, "_baseline")

# 계산 결과를 담는 절. 여기 있던 키의 값이 바뀌면 실패다.
GUARDED = ("expected", "summary")

# 입력 스펙. 지문·메타는 늘어도 되지만 이 셋은 그대로여야 한다.
GUARDED_INPUT = ("surface", "base_plane", "params")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save():
    if os.path.isdir(BASELINE):
        shutil.rmtree(BASELINE)
    os.makedirs(BASELINE)
    n = 0
    for f in sorted(glob.glob(os.path.join(FIXTURES, "T*.json"))):
        shutil.copy(f, BASELINE)
        n += 1
    print("baseline saved: {} files".format(n))
    return 0


def check(strict=False):
    if not os.path.isdir(BASELINE):
        print("[FAIL] no baseline. run with --save first")
        return 2

    bad = []
    added = []
    new_cases = []

    for f in sorted(glob.glob(os.path.join(FIXTURES, "T*.json"))):
        name = os.path.basename(f)
        b = os.path.join(BASELINE, name)
        if not os.path.isfile(b):
            new_cases.append(name)
            continue

        old = _load(b)
        new = _load(f)

        for section in GUARDED:
            o = old.get(section) or {}
            n = new.get(section) or {}
            for key, val in o.items():
                if key not in n:
                    bad.append("{} {}.{} 사라짐".format(name, section, key))
                elif n[key] != val:
                    bad.append("{} {}.{} 바뀜".format(name, section, key))
            for key in n:
                if key not in o:
                    added.append("{} {}.{}".format(name, section, key))

        for key in GUARDED_INPUT:
            if old["input"].get(key) != new["input"].get(key):
                bad.append("{} input.{} 바뀜".format(name, key))

    for name in new_cases:
        print("[NEW] {} (기준에 없음 — 새 케이스라면 정상)".format(name))

    if added:
        print("[ADDED] 기준에 없던 키 {}개:".format(len(added)))
        for a in sorted(set(a.split(" ", 1)[1] for a in added)):
            print("        " + a)
        print("        (진단 추가라면 정상. 확인 후 --save 로 기준 갱신)")

    if bad:
        print("[FAIL] 계산 결과가 바뀌었다:")
        for x in bad[:20]:
            print("       " + x)
        if len(bad) > 20:
            print("       ... 외 {}건".format(len(bad) - 20))
        return 1

    if strict and added:
        print("[FAIL] --strict: 키가 늘어났다")
        return 1

    print("[PASS] 기준에 있던 expected/summary/input 이 전부 그대로다")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="현재 상태를 기준으로 저장")
    ap.add_argument("--strict", action="store_true", help="키가 늘어나도 실패로 본다")
    args = ap.parse_args()
    return save() if args.save else check(strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())

#! /usr/bin/env python3
# -*- coding: utf-8 -*-
"""AMv1 Pins 아이콘을 생성한다 — 손으로 그리지 않는다.

그림: 어두운 바탕 위에 높이가 다른 핀 다섯 개, 그 위를 지나는 목표 곡선.
그것이 이 컴포넌트가 하는 일 전부다(곡면 -> 핀 높이).

    python adaptive_mold/tools/make_icons.py

출력: plugin/AdaptiveMold.GH/Resources/icon24.png (컴포넌트)
      plugin/AdaptiveMold.GH/Resources/icon64.png (Yak 매니페스트)
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "plugin", "AdaptiveMold.GH", "Resources")

BG = (32, 38, 46, 255)
PIN = (150, 160, 172, 255)
CURVE = (255, 176, 59, 255)

# 핀 5개의 상대 높이 (0~1). 가운데가 높은 완만한 곡면.
HEIGHTS = [0.30, 0.62, 0.86, 0.66, 0.34]


def draw(size):
    """size 배수로 그린 뒤 줄인다 — 24px 에 직접 그리면 계단이 심하다."""
    ss = 8
    n = size * ss
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = int(n * 0.18)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=r, fill=BG)

    pad = n * 0.16
    inner = n - 2 * pad
    base_y = n - pad
    pin_w = max(2, int(inner / (len(HEIGHTS) * 2.2)))

    tops = []
    for i, h in enumerate(HEIGHTS):
        cx = pad + inner * (i + 0.5) / len(HEIGHTS)
        top_y = base_y - inner * h
        d.rectangle([cx - pin_w / 2.0, top_y, cx + pin_w / 2.0, base_y], fill=PIN)
        tops.append((cx, top_y))

    d.line(tops, fill=CURVE, width=max(2, int(n * 0.045)), joint="curve")

    return img.resize((size, size), Image.LANCZOS)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    for size in (24, 64):
        p = os.path.join(OUT, "icon%d.png" % size)
        draw(size).save(p, "PNG", optimize=True)
        print("%s  %d bytes" % (p, os.path.getsize(p)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

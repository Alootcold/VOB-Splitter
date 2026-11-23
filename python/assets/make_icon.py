#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 VOB Splitter 的应用图标（Windows .ico）。

图形含义：一条被从中间切开的胶片 —— 即「无损分割」。
配色沿用界面色板（暗底 + 唯一强调色）。

    python assets/make_icon.py
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'vobsplit.ico')

BG = (13, 14, 17, 255)        # surface
BORDER = (42, 46, 55, 255)    # outline
ACCENT = (90, 169, 184, 255)  # primary
HOLE = (13, 14, 17, 255)     # 胶片孔用底色

SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw_icon(size):
    s = size
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    u = s / 256.0                      # 以 256 为设计基准

    # 底板：圆角方块
    d.rounded_rectangle(
        [4 * u, 4 * u, (s - 4) * u, (s - 4) * u],
        radius=48 * u, fill=BG, outline=BORDER, width=max(1, int(2 * u)))

    # 被切开的胶片：左右两半，中间留一道缝
    half_w = 72 * u
    top, bottom = 64 * u, 192 * u
    gap = 12 * u
    left_x0, left_x1 = 40 * u, 40 * u + half_w
    right_x0, right_x1 = 256 * u - 40 * u - half_w, 256 * u - 40 * u

    for x0, x1 in ((left_x0, left_x1), (right_x0, right_x1)):
        d.rounded_rectangle([x0, top, x1, bottom], radius=8 * u, fill=ACCENT)
        # 胶片孔
        holes = 4
        span = (bottom - top) - 24 * u
        step = span / (holes - 1)
        for i in range(holes):
            cy = top + 12 * u + i * step
            for hx in (x0 + 10 * u, x1 - 10 * u - 8 * u):
                r = 4 * u
                d.rounded_rectangle([hx, cy - r, hx + 2 * r, cy + r],
                                    radius=r, fill=HOLE)

    # 切线：两半之间的虚线
    cx = s / 2.0
    y = top - 14 * u
    while y < bottom + 10 * u:
        d.rectangle([cx - 1.5 * u, y, cx + 1.5 * u, y + 8 * u], fill=ACCENT)
        y += 14 * u

    return img


def main():
    base = draw_icon(256)
    base.save(OUT, format='ICO',
              sizes=[(s, s) for s in SIZES])
    # 顺带存一张 PNG，文档里可以用
    base.save(os.path.join(HERE, 'vobsplit.png'))
    print('icon written: %s' % OUT)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 NSIS 安装/卸载程序皮肤（Duilib XML 里引用的位图）。

界面本体是 Duilib 的 XML（布局 + 颜色 + 文字），只有少数字体位图需要自己画：
复选框、标题条的最小化/关闭、进度条前景、完成页的对勾徽章。

**图标不能靠缩放**：1024px 的光盘缩到 24px 就糊成一团。
所以图标是「按小尺寸重新处理」过的 —— 线稿提亮、底板抬亮，
让光盘和那块青色切块在 24px 也分得出来。原始图标仍用在 exe 和任务栏上。

配色跟应用本身对齐：
    surface  #141418   背景
    surface2 #17171C   底部栏
    raised   #1C1C21   控件底
    border   #2A2E37   描边
    border2  #3A3F4B   描边（hover）
    text     #E9E9EE   正文
    dim      #9A9AA6   次要文字
    accent   #45C7DE   唯一强调色
    onaccent #0F1013   强调色上的字

    python tools/build_skin_assets.py
"""
import os

from PIL import Image, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'flutter', 'app', 'installer', 'skin', 'assets')
APP_ICON = os.path.join(ROOT, 'assets', 'icon-disc.png')

SURFACE = (20, 20, 24, 255)
RAISED = (28, 28, 33, 255)
BORDER = (42, 46, 55, 255)
TEXT = (233, 233, 238, 255)
DIM = (154, 154, 166, 255)
ACCENT = (69, 199, 222, 255)

# 图标处理用的颜色
ICON_LINE = (122, 130, 146)   # 光盘线稿提亮后的颜色
ICON_PLATE_LIFT = 22          # 底板抬亮的幅度
ICON_PLATE = (38, 38, 46, 255)   # 24px 手绘版的底板
ICON_RING = (78, 86, 100, 255)   # 24px 手绘版的光盘环
ICON_WEDGE = (22, 54, 62, 255)   # 24px 手绘版的切块填充


SS = 8  # 超采样倍数：小图标先按 8 倍画，再缩回来，边缘才不毛


def _canvas(size):
    img = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _down(img, size):
    return img.resize((size, size), Image.LANCZOS)


def app_icon(size):
    """应用图标（光盘 + 切块），按小尺寸重新处理过。

    原图的问题是：底板跟界面背景几乎同色，线稿又太暗，
    直接缩到 24px 就是一个黑疙瘩。这里做两件事：
      * 底板整体抬亮 —— 图标的轮廓在深色背景上分得出来
      * 光盘的灰色线稿提亮成 #7A8292 —— 48px 也看得见是张光盘
    青色切块原样保留。
    """
    src = Image.open(APP_ICON).convert('RGBA')
    r, g, b, a = src.split()
    gray = src.convert('L')
    mx = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    sat = ImageChops.subtract(mx, mn)

    low_sat = sat.point(lambda v: 255 if v < 30 else 0)
    plate_mask = ImageChops.multiply(
        gray.point(lambda v: 255 if v < 30 else 0), low_sat)
    line_mask = ImageChops.multiply(
        gray.point(lambda v: 255 if 30 <= v <= 95 else 0), low_sat)

    body = src.convert('RGB')
    bright = Image.new('RGB', src.size, ICON_LINE)
    body = Image.composite(bright, body, line_mask)
    lifted = ImageChops.add(body, Image.new('RGB', src.size,
                                            (ICON_PLATE_LIFT,) * 3))
    body = Image.composite(lifted, body, plate_mask)

    out = body.convert('RGBA')
    out.putalpha(a)
    return out.resize((size, size), Image.LANCZOS)


def app_icon_small(size):
    """24px 用的图标：按原图构图手绘。

    原图在 1024px 上的光盘线稿只有 5px 宽、青色切块描边只有 22px，
    缩到 24px 分别是 0.12px 和 0.5px —— 缩出来就是一团灰雾加一道糊边。
    所以这一档是照着原图构图（深色底板 + 光盘环 + 青色切块）重新画的，
    线宽按目标尺寸给足，24px 也认得出是哪个图标。
    """
    s = size * 8
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.21),
                        fill=ICON_PLATE)
    c = s * 0.5
    r = s * 0.34
    d.ellipse([c - r, c - r, c + r, c + r], outline=ICON_RING,
              width=max(2, int(s * 0.045)))
    wr = s * 0.40
    box = [c - wr, c - wr, c + wr, c + wr]
    d.pieslice(box, -55, 55, fill=ICON_WEDGE)
    d.pieslice(box, -55, 55, outline=ACCENT, width=max(2, int(s * 0.07)))
    return img.resize((size, size), Image.LANCZOS)


def check_box(size, checked, hot=False):
    """复选框。

    16px 这种尺寸上不能直接画描边：PIL 的 rounded_rectangle(width=1)
    在圆角处会把顶边吃掉，出来是个断头的「凵」，根本不像勾选框。
    所以统一 8 倍超采样画、最后缩回来，描边用「填外框 + 挖内框」实现，
    四个角一定闭合。
    选中态的勾是一笔画的（带圆角折点），不是两段线拼的 —— 后者在小尺寸上
    折点会糊成一个钩子。
    """
    s = size * SS
    img, d = _canvas(size)
    u = s / float(size)          # 一个最终像素等于多少超采样像素
    outer = [u, u, s - 1 - u, s - 1 - u]
    inner = [u * 2, u * 2, s - 1 - u * 2, s - 1 - u * 2]
    radius = u * 3.5

    if checked:
        d.rounded_rectangle(outer, radius=radius, fill=ACCENT)
        pts = [(s * 0.285, s * 0.515), (s * 0.425, s * 0.655),
               (s * 0.715, s * 0.305)]
        d.line(pts, fill=SURFACE, width=max(2, int(u * 1.6)), joint='curve')
    else:
        edge = (152, 160, 178, 255) if hot else (112, 120, 136, 255)
        d.rounded_rectangle(outer, radius=radius, fill=edge)
        d.rounded_rectangle(inner, radius=radius - u, fill=(0, 0, 0, 0))
    return _down(img, size)


def close_glyph(size, hot=False):
    """标题条的关闭叉。"""
    s = size * 8
    img, d = _canvas(size)
    color = TEXT if hot else DIM
    w = max(2, int(round(s * 0.11)))
    m = s * 0.24
    d.line([(m, m), (s - m, s - m)], fill=color, width=w)
    d.line([(s - m, m), (m, s - m)], fill=color, width=w)
    return _down(img, size)


def min_glyph(size, hot=False):
    """标题条的最小化横线。"""
    s = size * 8
    img, d = _canvas(size)
    color = TEXT if hot else DIM
    w = max(2, int(round(s * 0.11)))
    m = s * 0.22
    y = s * 0.66
    d.line([(m, y), (s - m, y)], fill=color, width=w)
    return _down(img, size)


def done_badge(size):
    """完成页的圆形对勾徽章。"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size * 0.06
    d.ellipse([pad, pad, size - 1 - pad, size - 1 - pad],
              outline=ACCENT, width=max(2, size // 22))
    d.line([(size * 0.30, size * 0.52), (size * 0.44, size * 0.66)],
           fill=ACCENT, width=max(2, size // 18))
    d.line([(size * 0.44, size * 0.66), (size * 0.70, size * 0.34)],
           fill=ACCENT, width=max(2, size // 18))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    written = []

    def save(name, img):
        path = os.path.join(OUT, name)
        img.save(path)
        written.append((name, os.path.getsize(path)))

    save('appicon_24.png', app_icon_small(24))
    save('appicon_40.png', app_icon(40))
    save('appicon_48.png', app_icon(48))

    save('check_off.png', check_box(16, False))
    save('check_off_hot.png', check_box(16, False, hot=True))
    save('check_on.png', check_box(16, True))

    save('close.png', close_glyph(12))
    save('close_hot.png', close_glyph(12, hot=True))
    save('min.png', min_glyph(12))
    save('min_hot.png', min_glyph(12, hot=True))

    save('done.png', done_badge(56))

    # 进度条前景：一小块纯色，Duilib 会拉伸到进度区，
    # 再由控件的 borderround 裁成圆角。
    fg = Image.new('RGBA', (4, 4), ACCENT[:3] + (255,))
    save('progress_fg.png', fg)

    for name, size in written:
        print('  %-20s %5d bytes' % (name, size))
    print('共 %d 个文件 -> %s' % (len(written), OUT))


if __name__ == '__main__':
    main()

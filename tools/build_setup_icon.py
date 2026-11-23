#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 Windows 安装程序（Inno Setup 产出的 setup.exe）专用图标。

源图：assets/icon-frames.png —— 深色圆角底板 + 双帧字形（光盘框 → 箭头 → 播放框）。

为什么和应用自身的图标分开：
  * 应用图标 python/assets/vobsplit.ico 是**透明底**字形，贴在应用自己的深色
    标题栏 / 任务栏上才不违和；
  * 安装程序的图标是独立显示的（资源管理器、「应用和功能」列表、桌面快捷方式），
    带底板才像一个正经应用图标，而不是一枚悬空的线框。

小尺寸策略（每个尺寸单独画，不靠缩放糊）：
  * ≤24px：实心青块 + 反白三角 —— 描边框在这个尺寸只剩 1px 空壳，
    三角画出来是一团乱麻，反白才认得出是「播放」；
  * 25~32px：底板 + 放大居中的青色描边播放框；
  * ≥40px：直接对 1024px 源图做 LANCZOS 缩放（源图矢量级清晰度，缩放不糊）。

    python tools/build_setup_icon.py
"""
import os
import struct
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'icon-frames.png')
OUT_ICO = os.path.join(ROOT, 'python', 'assets', 'vobsplit-setup.ico')
OUT_PREVIEW = os.path.join(ROOT, 'docs', 'icon-setup-sizes-preview.png')

# 底板渐变（取自源图实测：顶 → 底）
GRAD_TOP = (26, 26, 31, 255)
GRAD_BOTTOM = (13, 13, 17, 255)
TILE_RADIUS = 0.125          # 底板圆角半径占边长比例（实测源图约 130/1024）
TEAL = (69, 199, 222, 255)

# 字形几何（源图 1024 画布实测）
FRAME_BOX = (554, 350, 802, 674)   # 青色播放框外接矩形
FRAME_STROKE = 22                  # 描边宽度
TRI = (641, 460, 723, 563)         # 播放三角外接矩形

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SOLID_LIMIT = 24                # ≤ 此尺寸走「实心块 + 反白三角」
OUTLINE_LIMIT = 32              # ≤ 此尺寸走「描边播放框」；更大直接缩放源图


def gradient_at(t):
    """按归一化高度取底板渐变色。"""
    return tuple(
        int(round(GRAD_TOP[i] + (GRAD_BOTTOM[i] - GRAD_TOP[i]) * t))
        for i in range(4)
    )


def vertical_gradient(size):
    """底板：竖向线性渐变的圆角方块。"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    grad = Image.new('RGBA', (1, size))
    gp = grad.load()
    for y in range(size):
        gp[0, y] = gradient_at(y / max(1, size - 1))
    grad = grad.resize((size, size), Image.BILINEAR)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=TILE_RADIUS * size, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def render_solid(size):
    """极小尺寸版：实心青色圆角块 + 反白三角。

    16px 里描边框只剩 1px 宽的空壳，三角只有 2~3 个像素，画出来是一团乱麻。
    所以最小尺寸直接反白——实心块配一个暗三角，一眼就是「播放」。
    """
    img = vertical_gradient(size)
    d = ImageDraw.Draw(img)

    box = size * 0.62
    x0 = (size - box) / 2.0
    y0 = (size - box) / 2.0
    d.rounded_rectangle([x0, y0, x0 + box, y0 + box],
                        radius=box * 0.22, fill=TEAL)

    tw = box * 0.40
    th = box * 0.46
    lx = (size - tw) / 2.0
    d.polygon([(lx, (size - th) / 2.0),
               (lx, (size + th) / 2.0),
               (lx + tw, size / 2.0)], fill=gradient_at(0.5))
    return img


def render_outline(size):
    """小尺寸版：底板 + 放大居中的青色描边播放框。

    比整张图放大更清楚——16px 里塞「光盘框 + 箭头 + 播放框」三个物体必然糊，
    这里只留最醒目的青色播放框，描边加粗到 ≥1.5px。
    """
    img = vertical_gradient(size)
    d = ImageDraw.Draw(img)

    # 以 1024 为基准换算几何
    k = size / 1024.0
    fx0, fy0, fx1, fy1 = FRAME_BOX

    target_h = size * 0.60
    frame_h = (fy1 - fy0) * k
    scale = target_h / frame_h

    fw = (fx1 - fx0) * k * scale
    fh = (fy1 - fy0) * k * scale
    cx = cy = size / 2.0
    x0, y0 = cx - fw / 2.0, cy - fh / 2.0
    x1, y1 = cx + fw / 2.0, cy + fh / 2.0

    stroke = max(1.5, FRAME_STROKE * k * scale)
    radius = min(fw, fh) * 0.22
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                        outline=TEAL, width=int(round(stroke)))

    # 播放三角：源图里是等腰三角形，垂直居中
    tx0, ty0, tx1, ty1 = TRI
    tw = (tx1 - tx0) * k * scale
    th = (ty1 - ty0) * k * scale
    left = cx - tw / 2.0
    d.polygon([(left, cy - th / 2.0),
               (left, cy + th / 2.0),
               (left + tw, cy)], fill=TEAL)
    return img


def render_small(size):
    if size <= SOLID_LIMIT:
        return render_solid(size)
    return render_outline(size)


def render_full(size, source):
    """大尺寸版：直接对 1024 源图做 LANCZOS 缩放。"""
    return source.resize((size, size), Image.LANCZOS)


def dib_bytes(img):
    """RGBA 图 → ICO 里的 32bpp DIB（含 AND 掩码）。"""
    w, h = img.size
    rgba = img.convert('RGBA')
    pixels = rgba.load()
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            xor += bytes((b, g, r, a))
    mask_row = ((w + 31) // 32) * 4
    and_mask = bytes(mask_row * h)
    header = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + and_mask


def write_ico(path, images):
    """手写 ICO 容器，每个尺寸用各自那张图。

    PIL 的 save(format='ICO') 只认「一张底图 + sizes 列表」，会把底图缩小去填
    各个尺寸——我们按尺寸单独画好的简化版根本进不去。
    """
    datas = [dib_bytes(im) for im in images]
    out = bytearray(struct.pack('<HHH', 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for im, data in zip(images, datas):
        w, h = im.size
        out += struct.pack('<BBBBHHII', w if w < 256 else 0, h if h < 256 else 0,
                           0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for data in datas:
        out += data
    with open(path, 'wb') as f:
        f.write(out)


def main():
    if not os.path.isfile(SRC):
        raise SystemExit('找不到源图：%s' % SRC)
    source = Image.open(SRC).convert('RGBA')

    rendered = {}
    for s in SIZES:
        rendered[s] = render_small(s) if s <= OUTLINE_LIMIT else render_full(s, source)

    os.makedirs(os.path.dirname(OUT_ICO), exist_ok=True)
    write_ico(OUT_ICO, [rendered[s] for s in SIZES])

    # 预览：上排浅底（资源管理器 / 「应用和功能」列表），下排深底（任务栏）
    pad = 20
    w = sum(s + pad for s in SIZES) + pad
    sheet = Image.new('RGB', (w, 320), (32, 32, 38))
    d = ImageDraw.Draw(sheet)
    d.rectangle([0, 0, w, 160], fill=(243, 243, 243))
    x = pad
    for s in SIZES:
        im = rendered[s]
        sheet.paste(im, (x, (160 - s) // 2), im)
        d.text((x, 168), str(s), fill=(110, 110, 120))
        sheet.paste(im, (x, 190 + (120 - s) // 2), im)
        d.text((x, 292), str(s), fill=(200, 200, 210))
        x += s + pad
    os.makedirs(os.path.dirname(OUT_PREVIEW), exist_ok=True)
    sheet.save(OUT_PREVIEW)

    print('ico :', OUT_ICO, '(%d bytes)' % os.path.getsize(OUT_ICO))
    print('prev:', OUT_PREVIEW)


if __name__ == '__main__':
    main()

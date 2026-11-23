#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按尺寸矢量重绘 Python 版图标，并手写 ICO 容器（每尺寸各存一份自己画的图）。

为什么不用 PIL 的 save(format='ICO')：它只认「一张底图 + sizes 列表」，
会把你那张底图缩小去填各个尺寸 —— 小尺寸就会糊，
我们按尺寸单独画好的简化版根本进不去。

ICO 结构：
  ICONDIR            6 字节：reserved=0, type=1, count
  ICONDIRENTRY       每项 16 字节：宽/高/色数/保留/平面/位深/大小/偏移
  每项的数据         32bpp DIB（含 BITMAPINFOHEADER + 像素 + AND 掩码）
"""
import os
import struct

from PIL import Image, ImageDraw

ROOT = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter"
OUT_ICO = os.path.join(ROOT, 'python', 'assets', 'vobsplit.ico')
OUT_PNG = os.path.join(ROOT, 'python', 'assets', 'vobsplit.png')
OUT_PREVIEW = os.path.join(ROOT, 'docs', 'icon-sizes-preview.png')

DARK = (58, 58, 67, 255)
TEAL = (69, 199, 222, 255)

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]

# 原图 512 画布上的几何（实测自用户提供的字形）
GEO = dict(
    lx0=110, lx1=235, ly0=174, ly1=337,
    disc_cx=172.5, disc_cy=256, disc_r=29.5,
    arrow_x0=228, arrow_x1=269,
    rx0=276, rx1=401, ry0=174, ry1=337,
    tri_x0=322, tri_x1=361, tri_y0=238, tri_y1=274,
)


def render_full(size):
    """完整字形：胶片框 + 光盘 + 箭头 + 播放框 + 播放三角。"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    content_w = GEO['rx1'] - GEO['lx0']
    k = size * 0.94 / content_w
    ox = (size - content_w * k) / 2 - GEO['lx0'] * k
    oy = (size - 164 * k) / 2 - GEO['ly0'] * k

    def X(v):
        return v * k + ox

    def Y(v):
        return v * k + oy

    lw = max(1.0, 8 * k)
    radius = 22 * k

    d.rounded_rectangle([X(GEO['lx0']), Y(GEO['ly0']), X(GEO['lx1']), Y(GEO['ly1'])],
                        radius=radius, outline=DARK, width=int(round(lw)))
    d.rounded_rectangle([X(GEO['rx0']), Y(GEO['ry0']), X(GEO['rx1']), Y(GEO['ry1'])],
                        radius=radius, outline=TEAL, width=int(round(lw)))

    r = GEO['disc_r'] * k
    cx, cy = X(GEO['disc_cx']), Y(GEO['disc_cy'])
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=DARK,
              width=int(round(max(1.0, 6 * k))))
    ri = 7.5 * k
    d.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=DARK)

    ay = Y(256)
    shaft_x1 = X(252)
    d.line([X(GEO['arrow_x0']), ay, shaft_x1, ay], fill=DARK, width=int(round(lw)))
    head = 18 * k
    d.polygon([(shaft_x1, ay - head), (shaft_x1, ay + head),
               (X(GEO['arrow_x1']), ay)], fill=DARK)

    d.polygon([(X(GEO['tri_x0']), Y(GEO['tri_y0'])),
               (X(GEO['tri_x0']), Y(GEO['tri_y1'])),
               (X(GEO['tri_x1']), Y(256))], fill=TEAL)
    return img


def render_small(size):
    """小尺寸版：只保留最醒目的青色播放框（一个物体），描边加粗到 ≥1px。

    16px 里塞两个物体必然糊成一团，所以小尺寸只上一个主体，
    大尺寸（资源管理器 48px+）用完整字形。
    """
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = size * 0.74
    x0 = (size - box) / 2
    y0 = (size - box) / 2
    lw = max(1.0, size * 0.10)
    d.rounded_rectangle([x0, y0, x0 + box, y0 + box], radius=box * 0.22,
                        outline=TEAL, width=int(round(lw)))
    cx, cy = x0 + box * 0.5, y0 + box * 0.5
    tri = box * 0.24
    d.polygon([(cx - tri * 0.5, cy - tri), (cx - tri * 0.5, cy + tri),
               (cx + tri * 0.85, cy)], fill=TEAL)
    return img


def dib_bytes(img):
    """把 RGBA 图转成 ICO 里的 32bpp DIB（含 AND 掩码）。"""
    w, h = img.size
    rgba = img.convert('RGBA')
    pixels = rgba.load()
    # 像素自下而上，BGRA
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            xor += bytes((b, g, r, a))
    # AND 掩码：1bpp，每行按 4 字节对齐；alpha 已写在像素里，掩码全 0
    mask_row = ((w + 31) // 32) * 4
    and_mask = bytes(mask_row * h)
    header = struct.pack('<IiiHHIIiiII', 40, w, h * 2, 1, 32, 0,
                         len(xor) + len(and_mask), 0, 0, 0, 0)
    return header + bytes(xor) + and_mask


def write_ico(path, images):
    """手写 ICO 容器，每个尺寸用各自那张图。"""
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
    rendered = {}
    for s in SIZES:
        rendered[s] = render_small(s) if s <= 32 else render_full(s)

    os.makedirs(os.path.dirname(OUT_ICO), exist_ok=True)
    write_ico(OUT_ICO, [rendered[s] for s in SIZES])
    rendered[256].save(OUT_PNG)

    # 预览：上排浅底（标题栏/资源管理器），下排深底（任务栏）
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
    sheet.save(OUT_PREVIEW)
    print('ico :', OUT_ICO, '(%d bytes)' % os.path.getsize(OUT_ICO))
    print('png :', OUT_PNG)
    print('prev:', OUT_PREVIEW)


if __name__ == '__main__':
    main()

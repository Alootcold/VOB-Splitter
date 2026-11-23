#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从仓库根的两张源图生成各平台所需的图标资源。

    assets/icon-disc.png     → Flutter 版（Windows .ico / macOS appiconset / Linux png）

    Python 版的图标由 tools/build_python_icon.py 按尺寸矢量重绘（16px 用单体播放键，
    40px+ 用完整双帧字形），本脚本不碰它。

    python tools/install_icons.py
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DISC = os.path.join(ROOT, 'assets', 'icon-disc.png')
SRC_FRAMES = os.path.join(ROOT, 'assets', 'icon-frames.png')

FLUTTER_APP = os.path.join(ROOT, 'flutter', 'app')
WIN_ICO = os.path.join(FLUTTER_APP, 'windows', 'runner', 'resources', 'app_icon.ico')
MAC_SET = os.path.join(FLUTTER_APP, 'macos', 'Runner', 'Assets.xcassets',
                       'AppIcon.appiconset')
LINUX_PNG = os.path.join(FLUTTER_APP, 'linux', 'runner', 'resources', 'app_icon.png')
PY_ICO = os.path.join(ROOT, 'python', 'assets', 'vobsplit.ico')

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
MAC_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def save_ico(src_path, ico_path, sizes=ICO_SIZES):
    img = Image.open(src_path).convert('RGBA')
    os.makedirs(os.path.dirname(ico_path), exist_ok=True)
    img.save(ico_path, format='ICO', sizes=[(s, s) for s in sizes])
    print('  ICO  %-52s %s' % (os.path.relpath(ico_path, ROOT), sizes))


def save_png(src_path, png_path, size):
    img = Image.open(src_path).convert('RGBA')
    img = img.resize((size, size), Image.LANCZOS)
    os.makedirs(os.path.dirname(png_path), exist_ok=True)
    img.save(png_path, format='PNG')
    return png_path


def main():
    for src in (SRC_DISC, SRC_FRAMES):
        if not os.path.isfile(src):
            raise SystemExit('缺少源图: %s' % src)

    print('Flutter 版图标（光盘/章节）:')
    save_ico(SRC_DISC, WIN_ICO)
    for size in MAC_SIZES:
        save_png(SRC_DISC, os.path.join(MAC_SET, 'app_icon_%d.png' % size), size)
    save_png(SRC_DISC, LINUX_PNG, 512)

    print('Python 版图标（双帧）:')
    # Python 侧的图标是按尺寸矢量重绘的（16px 用单体播放键，40px+ 用完整字形），
    # 单独由 build_python_icon.py 生成，不要在这里覆盖。
    py_ico = os.path.join(ROOT, 'python', 'assets', 'vobsplit.ico')
    print('  (由 tools/build_python_icon.py 生成：%s)' % os.path.relpath(py_ico, ROOT))
    print('done.')


if __name__ == '__main__':
    main()

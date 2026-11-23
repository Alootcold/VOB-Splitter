#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成软著（计算机软件著作权登记）要交的两份材料：

  1. 源程序文档 —— 前 30 页 + 后 30 页，每页 50 行，页眉带软件名与版本号
  2. 软件说明书 —— 封面、目录、运行环境、安装、功能与操作、常见问题

两份都输出成 PDF（A4，150 dpi），直接能传到中国版权保护中心。

    python tools/make_copyright_materials.py

产物：
    release/copyright/VOB-Splitter-V1.0.0-源程序.pdf
    release/copyright/VOB-Splitter-V1.0.0-说明书.pdf
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'release', 'copyright')

SOFTWARE = 'VOB Splitter'
VERSION = 'V1.0.0'

# 著作权人 —— 必须与软著申请表、联想商店实名认证主体完全一致。
# 这里是唯一出处，别再在封面里写占位符。
COPYRIGHT_HOLDER = '任新文'

# A4 @ 150dpi
DPI = 150
PW, PH = 1240, 1754
MARGIN_X = 78
CODE_TOP = 104
LINE_H = 30
LINES_PER_PAGE = 50

FONT_PATH = r'C:\Windows\Fonts\simsun.ttc'      # 宋体：软著材料的标准字体
FONT_BOLD = r'C:\Windows\Fonts\simhei.ttf'      # 黑体：标题
DUMP_PNG = bool(os.environ.get('COPYRIGHT_DUMP_PNG'))   # 调试/需要逐页 PNG 时用
CODE_FONT_SIZE = 17        # 8pt @150dpi 的等效像素
TEXT_FONT_SIZE = 21        # 10.5pt @150dpi
TITLE_FONT_SIZE = 34

# 源程序的文件顺序：先核心算法，再 CLI/图形界面，最后 Flutter 那一套。
# 顺序决定了「前 30 页」和「后 30 页」分别覆盖什么，所以刻意排过。
SOURCE_FILES = [
    ('python/vobsplit/__init__.py',        '版本信息与导出'),
    ('python/vobsplit/ps.py',              'MPEG-2 Program Stream 解析'),
    ('python/vobsplit/chapters.py',        '章节检测'),
    ('python/vobsplit/splitter.py',        '字节级切分'),
    ('python/vobsplit/runner.py',         '流程编排'),
    ('python/vobsplit/remux.py',           '转封装（MKV）'),
    ('python/vobsplit/cli.py',             '命令行界面'),
    ('python/vobsplit/gui.py',             'Tkinter 图形界面'),
    ('flutter/packages/vobsplit_core/lib/src/ps.dart',        'MPEG-2 PS 解析（Dart）'),
    ('flutter/packages/vobsplit_core/lib/src/chapters.dart',  '章节检测（Dart）'),
    ('flutter/packages/vobsplit_core/lib/src/splitter.dart',  '字节级切分（Dart）'),
    ('flutter/packages/vobsplit_core/lib/src/remux.dart',      '转封装（Dart）'),
    ('flutter/app/lib/main.dart',          'Flutter 应用入口'),
    ('flutter/app/lib/theme.dart',         '深色主题'),
    ('flutter/app/lib/controller.dart',     '流程控制'),
    ('flutter/app/lib/ui/side_panel.dart', '左侧控制栏'),
    ('flutter/app/lib/ui/chapter_table.dart', '章节表格'),
    ('flutter/app/lib/ui/console_log.dart', '日志面板'),
    ('flutter/app/lib/ui/verify_badge.dart', '校验徽章'),
]


def _font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.truetype(path, size)


def _load_lines():
    """按 SOURCE_FILES 的顺序把源码拼成一份总清单。"""
    blocks = []
    total = 0
    for rel, desc in SOURCE_FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            print('  跳过（找不到）：%s' % rel)
            continue
        blocks.append(('// ===== %s —— %s =====' % (rel, desc), 'head'))
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n').replace('\t', '    ')
                blocks.append((line, 'code'))
        blocks.append(('', 'code'))
        total += 1
    return blocks, total


def _fit(text, font, max_w):
    """超宽的代码行按字符折行（打印源码清单的常规做法）。"""
    if font.getlength(text) <= max_w:
        return [text]
    out = []
    cur = ''
    for ch in text:
        if font.getlength(cur + ch) > max_w:
            out.append(cur)
            cur = '    ' + ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def build_source_pdf():
    print('== 源程序文档 ==')
    blocks, nfiles = _load_lines()
    # 展开折行后的实际行
    code_font = _font(FONT_PATH, CODE_FONT_SIZE)
    text_w = PW - 2 * MARGIN_X
    flat = []
    for text, kind in blocks:
        if kind == 'head':
            flat.append((text, True))
        else:
            for part in _fit(text, code_font, text_w):
                flat.append((part, False))

    total_lines = len(flat)
    need = LINES_PER_PAGE * 60
    if total_lines < need:
        print('  !! 源码只有 %d 行，不足 %d 行（60 页 x 50 行）' % (total_lines, need))
    head = flat[:LINES_PER_PAGE * 30]
    tail = flat[-LINES_PER_PAGE * 30:]
    pages = []
    for chunk in (head, tail):
        for i in range(0, len(chunk), LINES_PER_PAGE):
            pages.append(chunk[i:i + LINES_PER_PAGE])

    pages = [p for p in pages if p]
    print('  拼接后 %d 行，取前 30 页 + 后 30 页 = %d 页（%d 个文件）'
          % (total_lines, len(pages), nfiles))

    header_font = _font(FONT_PATH, 18)
    code_font = _font(FONT_PATH, CODE_FONT_SIZE)
    foot_font = _font(FONT_PATH, 18)

    imgs = []
    for pno, chunk in enumerate(pages, 1):
        img = Image.new('RGB', (PW, PH), (255, 255, 255))
        d = ImageDraw.Draw(img)
        # 页眉：软件名 + 版本（软著要求页眉标明软件名称和版本号）
        d.text((MARGIN_X, 52), '%s %s' % (SOFTWARE, VERSION), fill=(0, 0, 0), font=header_font)
        d.text((PW - MARGIN_X - 190, 52), '源程序', fill=(0, 0, 0), font=header_font)
        d.line([(MARGIN_X, 84), (PW - MARGIN_X, 84)], fill=(0, 0, 0), width=1)
        y = CODE_TOP
        for text, is_head in chunk:
            if y > PH - 120:
                break
            if is_head:
                d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=code_font)
            else:
                d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=code_font)
            y += LINE_H
        # 页脚：页码
        foot = '第 %d 页  共 %d 页' % (pno, len(pages))
        d.text((PW // 2 - foot.getlength() // 2 if hasattr(foot, 'getlength')
                else 0, PH - 90), foot, fill=(0, 0, 0), font=foot_font)
        imgs.append(img)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, '%s-%s-源程序.pdf' % (SOFTWARE, VERSION))
    imgs[0].save(path, 'PDF', resolution=DPI, save_all=True, append_images=imgs[1:])
    print('  -> %s  (%.1f KB, %d 页)' % (path, os.path.getsize(path) / 1024.0, len(imgs)))
    if DUMP_PNG:
        png_dir = os.path.join(OUT, 'png')
        os.makedirs(png_dir, exist_ok=True)
        for i, im in enumerate(imgs, 1):
            im.save(os.path.join(png_dir, 'src-%02d.png' % i))
        print('  -> %s（逐页 PNG）' % png_dir)
    return path


# ---------------------------------------------------------------------------
#  软件说明书
# ---------------------------------------------------------------------------
MANUAL = [
    ('h1', 'VOB Splitter 软件说明书'),
    ('cover', '版本：V1.0.0'),
    ('cover', '著作权人：' + COPYRIGHT_HOLDER),
    ('cover', '申请日期：2026 年 11 月'),

    ('h1', '目录'),
    ('toc', '一、软件概述'),
    ('toc', '二、运行环境'),
    ('toc', '三、安装与卸载'),
    ('toc', '四、图形界面使用说明'),
    ('toc', '五、命令行使用说明'),
    ('toc', '六、无损校验原理'),
    ('toc', '七、常见问题'),
    ('toc', '八、版权声明'),

    ('h1', '一、软件概述'),
    ('p', 'VOB Splitter 是一款 DVD VOB 无损分割工具。它把一张 DVD（或一份 VOB 文件）'
          '里的视频码流，按照 DVD 内置的章节表切成多个独立的视频文件，'
          '输出的每一个字节都来自原始码流 —— 不重新编码、不重新封装，画质零损失。'),
    ('h2', '1.1 解决的问题'),
    ('p', '想把 DVD 上的某一集单独拿出来，市面上的工具通常只有两种做法：'
          '一是重新编码，画质掉一档；二是按固定时长粗切一刀，章边界对不上。'
          '本软件只做字节级切片，不碰码流本身，并给出可复核的哈希证据。'),
    ('h2', '1.2 主要功能'),
    ('li', '按 DVD 内置章节表切分 VOB，切点精确到 pack 边界'),
    ('li', '按等长时长切分、按指定时间点切分（用于没有章节表的素材）'),
    ('li', '字节级无损：每次运行都用 SHA-256 比对源流与各章拼接结果'),
    ('li', '可选用 ffmpeg 转换为 MKV 容器（只换容器，不重编码）'),
    ('li', '图形界面与命令行两种用法，结果完全一致'),
    ('li', '全程离线运行，不联网、不上传、不收集任何信息'),
    ('h2', '1.3 技术特点'),
    ('p', 'DVD 的每一章都是一条独立的 MPEG-2 sequence，章首会把时间戳（PTS）归零。'
          '因此在码流里「时间戳回落」就精确对应一个章边界，而且那个位置天然是一个'
          '随机访问点（序列头 + I 帧），可以安全切入。切点因此不是靠猜的。'),
    ('p', '软件提供两套完全独立的实现：Python 版（零第三方依赖，含图形界面）'
          '与 Flutter 桌面版（纯 Dart 核心库 + 图形界面）。两套实现的核心算法逐行对应、'
          '测试用例一一对应，并有跨实现的交叉校验脚本自动比对结果。'),

    ('h1', '二、运行环境'),
    ('h2', '2.1 硬件要求'),
    ('li', '处理器：x86-64 架构，2.0 GHz 及以上'),
    ('li', '内存：2 GB 及以上'),
    ('li', '磁盘空间：安装后约 27 MB（安装包 12 MB）'),
    ('h2', '2.2 软件要求'),
    ('li', '操作系统：Windows 10（1809 及以上）或 Windows 11，64 位'),
    ('li', 'Python 版需 Python 3.8 及以上；Flutter 版为独立可执行文件'),
    ('li', '安装到 Program Files 目录需要管理员权限'),
    ('li', '「转 MKV」为可选功能，需使用者自行安装 ffmpeg，本版本不内置'),

    ('h1', '三、安装与卸载'),
    ('h2', '3.1 安装'),
    ('p', '双击安装包启动安装向导。安装界面为深色自绘风格，包含安装配置、'
          '正在安装、安装完成三个页面。'),
    ('li', '安装配置：可修改安装目录（默认 Program Files 下），可选择是否创建桌面快捷方式'),
    ('li', '正在安装：显示安装路径与进度条，文件写入过程中进度实时刷新'),
    ('li', '安装完成：显示安装路径，可选择是否立即启动软件'),
    ('p', '安装程序同时支持静默安装与自定义安装目录：'),
    ('code', 'VobSplit-Win-x64-Setup.exe /S'),
    ('code', 'VobSplit-Win-x64-Setup.exe /S /D=D:\\Apps\\VOB Splitter'),
    ('p', '其中 /S 表示静默安装（全程不出现界面，并在桌面创建快捷方式），'
          '/D= 用于指定安装目录（须为最后一个参数且不加引号）。'),
    ('h2', '3.2 卸载'),
    ('p', '在「控制面板 → 程序与卸载」中找到 VOB Splitter 即可卸载，'
          '卸载过程同样为自绘界面，卸载后不残留程序文件。'),

    ('h1', '四、图形界面使用说明'),
    ('h2', '4.1 界面布局'),
    ('p', '主界面分为左右两栏。左侧为控制栏，自上而下依次为：源、切分方式、输出、'
          '开始按钮。右侧为结果区，上方是章节表格，下方是运行日志；'
          '标题栏右侧显示当前状态与无损校验徽章。'),
    ('h2', '4.2 选择源'),
    ('p', '在左侧「VOB 文件或目录」一栏点「浏览」按钮，选中 DVD 的 VIDEO_TS 目录；'
          '「浏览」只能选目录，如果是单个 VOB 文件（VTS_xx_N.VOB），'
          '把它的完整路径直接粘贴进输入框即可。'
          '若目录中存在多个分卷，软件会按 VTS 序号自动排序，'
          '将它们视为一条连续的码流处理，无需手工合并。'),
    ('h2', '4.3 切分方式'),
    ('p', '切分方式有三种：'),
    ('li', '按章节：读取 DVD 内置章节表定位章边界，默认方式，不需要手工指定切点'),
    ('li', '等长：按固定时长分段，用于没有章节表的素材'),
    ('li', '指定点：手工输入以秒或分:秒表示的切点位置，多个切点用逗号分隔'),
    ('h2', '4.4 输出设置'),
    ('li', '输出目录：切分出的章节文件写入该目录'),
    ('li', '文件名前缀：默认 chapter，输出为 chapter_01.vob、chapter_02.vob …'),
    ('li', '输出格式：VOB 保持原样；MKV 调用 ffmpeg 以 -c copy 换容器；'
           '两者都保留则同时输出'),
    ('h2', '4.5 开始分割'),
    ('p', '点击「开始分割」后，软件依次完成扫描、切分与校验三个阶段。'
          '右侧表格会列出每一章的序号、起始时间、时长、大小与 GOP 数；'
          '日志区实时输出扫描与切分过程。'),
    ('h2', '4.6 校验结果'),
    ('p', '标题栏右侧的徽章显示校验状态：显示「无损校验通过」即代表输出与源流'
          '逐字节一致。校验详情写在日志中，同时会生成一份 vobsplit-manifest.json '
          '清单文件，记录源流与出流的字节数、SHA-256 值以及每一章的起止偏移，'
          '使用者可自行复核。'),

    ('h1', '五、命令行使用说明'),
    ('h2', '5.1 命令格式'),
    ('code', 'vobsplit scan  <源>                       扫描并列出章节，不做切分'),
    ('code', 'vobsplit split <源> -o <输出目录>          切分并自动校验'),
    ('code', 'vobsplit verify <输出目录> --source <源>   复核已有输出的哈希'),
    ('h2', '5.2 常用参数'),
    ('li', '-o / --output：输出目录'),
    ('li', '--mode auto|duration|times|whole：切分方式，默认 auto；whole 表示不切分、整段输出'),
    ('li', '--interval <秒>：等长切分的时长，默认 600'),
    ('li', '--times "0,218,489.28"：指定点切分的切点位置'),
    ('li', '--prefix <前缀>：输出文件名前缀，默认 chapter'),
    ('li', '--include-menu：把 DVD 菜单 VOB（VTS_xx_0.VOB）一并算进源'),
    ('h2', '5.3 使用示例'),
    ('code', 'vobsplit scan  "D:\\VIDEO_TS"'),
    ('code', 'vobsplit split "D:\\VIDEO_TS" -o "D:\\Split"'),
    ('code', 'vobsplit verify "D:\\Split" --source "D:\\VIDEO_TS"'),

    ('h1', '六、无损校验原理'),
    ('p', '切分只做一件事：把源文件的一段连续字节原样复制成新文件。'
          '为了证明这一点，每次运行都会计算两组哈希：'),
    ('li', '源流的 SHA-256'),
    ('li', '各章按顺序拼接后的 SHA-256'),
    ('p', '两组哈希相等、且字节总数相等，就说明输出的每一个字节都来自输入 —— '
          '没有重编码、没有重封装、没有丢帧。校验结果同时写入 '
          'vobsplit-manifest.json，使用者可以随时用 verify 子命令或任何 '
          'SHA-256 工具独立复核。'),

    ('h1', '七、常见问题'),
    ('h2', '7.1 提示检测不到章节边界'),
    ('p', '该 DVD 没有可用的章节表，或 VOB 经过了 CSS 加密（码流本身是密文，'
          '切点判定会失效）。此时改用「等长」或「指定点」方式切分。'),
    ('h2', '7.2 转 MKV 失败'),
    ('p', '本版本不内置 ffmpeg，需要使用者自行安装并确保 ffmpeg 在系统 PATH 中。'
          '不转 MKV 时切分功能不受任何影响。'),
    ('h2', '7.3 转成 MKV 后少了 DVD 的导航信息'),
    ('p', 'DVD 的 PCI/DSI 导航包装不进 Matroska 容器，会被丢弃。'
          '它与音视频码流无关，不影响播放与画质。'),
    ('h2', '7.4 每章时长和 DVD 章节表差一点'),
    ('p', '章内时长是从首个 GOP 起点量到末个 GOP 起点，不含末个 GOP 的长度，'
          '因此与 DVD 章节表存在最大约一个 GOP 的偏差，属于正常现象。'),

    ('h1', '八、版权声明'),
    ('p', 'VOB Splitter 采用 MIT 许可证发布，源代码公开。'),
    ('p', '本软件按「现状」提供，不附带任何明示或默示的担保。'
          '使用者需自行确认其使用行为符合当地法律法规。'),
    ('p', '软件内不包含任何第三方组件。「转 MKV」功能调用使用者自行安装的 ffmpeg，'
          '本软件不分发 ffmpeg。'),
]


def build_manual_pdf():
    print('== 软件说明书 ==')
    # 占位符自检：封面/正文里只要还留着「在此填…」这类模板字样就直接报错，
    # 免得又传一份带占位符的说明书上去被退正。
    # （命令行用法里的尖括号是参数占位写法，不算占位符。）
    for _kind, _text in MANUAL:
        if '在此填' in _text or '占位' in _text:
            raise SystemExit('说明书里还有占位符，先改掉：%s' % _text)
        if _kind == 'cover' and '<' in _text:
            raise SystemExit('封面上还有尖括号，先改掉：%s' % _text)
    body_font = _font(FONT_PATH, TEXT_FONT_SIZE)
    h1_font = _font(FONT_BOLD, TITLE_FONT_SIZE)
    h2_font = _font(FONT_BOLD, 25)
    li_font = _font(FONT_PATH, TEXT_FONT_SIZE)
    code_font = _font(FONT_PATH, CODE_FONT_SIZE)
    cover_font = _font(FONT_PATH, 24)

    text_w = PW - 2 * MARGIN_X
    pages = []
    img = Image.new('RGB', (PW, PH), (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 130

    def new_page():
        nonlocal img, d, y
        pages.append(img)
        img = Image.new('RGB', (PW, PH), (255, 255, 255))
        d = ImageDraw.Draw(img)
        y = 130

    def need(space):
        nonlocal y
        if y + space > PH - 110:
            new_page()

    for kind, text in MANUAL:
        if kind == 'cover':
            need(60)
            d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=cover_font)
            y += 56
            continue
        if kind == 'toc':
            need(40)
            d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=body_font)
            y += 38
            continue
        if kind == 'h1':
            need(120)
            if y > 140:
                new_page()
            d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=h1_font)
            y += 62
            d.line([(MARGIN_X, y - 16), (PW - MARGIN_X, y - 16)],
                   fill=(0, 0, 0), width=2)
            y += 12
            continue
        if kind == 'h2':
            need(70)
            d.text((MARGIN_X, y), text, fill=(0, 0, 0), font=h2_font)
            y += 48
            continue
        if kind == 'li':
            for i, part in enumerate(_wrap(text, li_font, text_w - 30)):
                need(38)
                d.text((MARGIN_X + 30 if i == 0 else MARGIN_X + 48, y),
                       ('· ' if i == 0 else '  ') + part,
                       fill=(0, 0, 0), font=li_font)
                y += 38
            continue
        if kind == 'code':
            for part in _wrap(text, code_font, text_w - 20):
                need(30)
                d.rectangle([MARGIN_X, y - 6, PW - MARGIN_X, y + 26],
                            outline=(180, 180, 180))
                d.text((MARGIN_X + 10, y), part, fill=(0, 0, 0), font=code_font)
                y += 34
            y += 12
            continue
        # 正文
        for part in _wrap(text, body_font, text_w):
            need(38)
            d.text((MARGIN_X, y), part, fill=(0, 0, 0), font=body_font)
            y += 38
        y += 10

    if y < PH - 110:
        pages.append(img)

    # 页码
    stamped = []
    for i, p in enumerate(pages, 1):
        dd = ImageDraw.Draw(p)
        foot = '第 %d 页  共 %d 页' % (i, len(pages))
        dd.text(((PW - dd.textlength(foot, font=body_font)) / 2, PH - 90),
                foot, fill=(0, 0, 0), font=body_font)
        stamped.append(p)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, '%s-%s-说明书.pdf' % (SOFTWARE, VERSION))
    stamped[0].save(path, 'PDF', resolution=DPI, save_all=True,
                    append_images=stamped[1:])
    print('  -> %s  (%.1f KB, %d 页)' % (path, os.path.getsize(path) / 1024.0, len(stamped)))
    if DUMP_PNG:
        png_dir = os.path.join(OUT, 'png')
        os.makedirs(png_dir, exist_ok=True)
        for i, im in enumerate(stamped, 1):
            im.save(os.path.join(png_dir, 'manual-%02d.png' % i))
        print('  -> %s（逐页 PNG）' % png_dir)
    return path


def _wrap(text, font, max_w):
    """按字符宽度折行（中文没有空格，按字折最稳）。

    顺手处理中文排版的一条忌讳：标点不能出现在行首，
    折行后如果下一行以标点开头，把它拉回上一行。
    """
    if font.getlength(text) <= max_w:
        return [text]
    out, cur = [], ''
    for ch in text:
        if font.getlength(cur + ch) > max_w:
            out.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        out.append(cur)
    # 行首标点回挂
    head_punct = '，。、；：？！）》」』】%…'
    for i in range(1, len(out)):
        while out[i] and out[i][0] in head_punct:
            out[i - 1] += out[i][0]
            out[i] = out[i][1:]
    return [o for o in out if o]


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if what in ('all', 'source'):
        build_source_pdf()
    if what in ('all', 'manual'):
        build_manual_pdf()
    print('\n产物目录：%s' % OUT)


if __name__ == '__main__':
    main()

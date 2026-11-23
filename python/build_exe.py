#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 VOB Splitter 打包成 Windows 桌面程序。

**刻意不用单文件（--onefile），只用目录版（--onedir）。**

为什么不要单文件版：
  * 单文件版运行时会把整个包解压到 %TEMP%\\_MEIxxxxx 再执行 ——
    解压出来的临时目录里的东西同样会被执行，注入面比普通目录大得多；
  * 单文件是一个自解压 blob，无法逐文件审计、无法给内部 dll 单独签名，
    杀毒软件也更容易误报；
  * 目录版是正常的文件夹结构（exe + _internal\\），一眼能看清带了什么，
    也方便按文件做白名单和哈希校验。

用法：
    python build_exe.py                # 只打图形界面
    python build_exe.py --with-cli    # 同时打一个命令行版
    python build_exe.py --clean-only  # 清理上次的构建产物
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, 'dist')
WORK = os.path.join(HERE, 'build')
ICON = os.path.join(HERE, 'assets', 'vobsplit.ico')
VERSION = '1.0.0'

# 这些包本项目用不到，打进包里只会白白变大
EXCLUDES = [
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
    'numpy', 'pandas', 'matplotlib', 'scipy', 'IPython',
    'notebook', 'pytest', 'tornado', 'sqlite3', 'pydoc_data',
    'unittest', 'doctest', 'distutils', 'setuptools',
]

VERSION_FILE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 0, 0), prodvers=(1, 0, 0, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'VOB Splitter contributors'),
         StringStruct('FileDescription', 'VOB Splitter - DVD VOB lossless splitter'),
         StringStruct('FileVersion', '%(version)s'),
         StringStruct('InternalName', 'vobsplit'),
         StringStruct('LegalCopyright', 'MIT License'),
         StringStruct('OriginalFilename', 'vobsplit.exe'),
         StringStruct('ProductName', 'VOB Splitter'),
         StringStruct('ProductVersion', '%(version)s')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ])
"""


def base_args(name, entry, console):
    args = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--onedir',                       # ← 目录版，绝不用 onefile
        '--name', name,
        '--paths', HERE,
        '--icon', ICON,
        '--distpath', DIST,
        '--workpath', os.path.join(WORK, name),
        '--specpath', os.path.join(WORK, name),
        '--version-file', os.path.join(WORK, '%s_version.txt' % name),
        '--hidden-import', 'vobsplit.gui',
        '--hidden-import', 'vobsplit.cli',
        # 窗口图标要一起打包
        '--add-data', os.path.join(HERE, 'assets') + os.pathsep + 'assets',
    ]
    args.append('--console' if console else '--windowed')
    for mod in EXCLUDES:
        args += ['--exclude-module', mod]
    args.append(entry)
    return args


def build(name, entry, console):
    os.makedirs(WORK, exist_ok=True)
    vf = os.path.join(WORK, '%s_version.txt' % name)
    with open(vf, 'w', encoding='utf-8') as f:
        f.write(VERSION_FILE % {'version': VERSION})
    cmd = base_args(name, entry, console)
    print('$ ' + ' '.join(cmd[:6]) + ' ...')
    proc = subprocess.run(cmd, cwd=HERE)
    if proc.returncode != 0:
        raise SystemExit('打包失败：退出码 %d' % proc.returncode)
    out = os.path.join(DIST, name)
    verify_output(out, name)
    return out


def verify_output(out, name):
    """确认产物是「目录 + exe」，而不是单文件。"""
    if not os.path.isdir(out):
        raise SystemExit('产物不是目录：%s' % out)
    exe = os.path.join(out, '%s.exe' % name)
    if not os.path.isfile(exe):
        raise SystemExit('找不到 exe：%s' % exe)
    total = 0
    count = 0
    for root, _dirs, files in os.walk(out):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
            count += 1
    exe_size = os.path.getsize(exe)
    print()
    print('产物目录 : %s' % out)
    print('主程序   : %s  (%.1f MB)' % (exe, exe_size / 1048576.0))
    print('目录内文件: %d 个，合计 %.1f MB' % (count, total / 1048576.0))
    print('版式     : 目录版（onedir）—— 可逐文件审计，无运行期解压')
    if count <= 2:
        raise SystemExit('看起来像单文件产物，已中止')


def main():
    ap = argparse.ArgumentParser(description='打包 VOB Splitter（目录版 exe）')
    ap.add_argument('--with-cli', action='store_true', help='同时打包命令行版')
    ap.add_argument('--clean-only', action='store_true', help='只清理构建产物')
    args = ap.parse_args()

    if args.clean_only:
        for d in (DIST, WORK):
            if os.path.isdir(d):
                shutil.rmtree(d)
                print('removed %s' % d)
        return

    os.makedirs(WORK, exist_ok=True)
    build('vobsplit', os.path.join(HERE, 'run_gui.py'), console=False)
    if args.with_cli:
        build('vobsplit-cli', os.path.join(HERE, 'run_cli.py'), console=True)


if __name__ == '__main__':
    main()

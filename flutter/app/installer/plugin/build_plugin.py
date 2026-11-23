#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
编译 VobSkin.dll —— NSIS 的 Duilib 皮肤插件。

插件把安装界面交给 Duilib 画，NSIS 脚本只负责逻辑。
Duilib 源码内嵌在 third_party/duilib（MIT + BSD 双许可，见那里的 LICENSE）。

依赖：Visual Studio 的 C++ 工具链（vcvarsall.bat）。
用法：
    python flutter/app/installer/plugin/build_plugin.py            # 编译 x86（默认 NSIS 安装程序）
    python flutter/app/installer/plugin/build_plugin.py --arch x64
"""
import argparse
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INSTALLER = os.path.dirname(HERE)
DUILIB = os.path.join(INSTALLER, 'third_party', 'duilib', 'DuiLib')
BUILD = os.path.join(HERE, 'build')

# 找一个能用的 vcvarsall.bat
VCVARS_CANDIDATES = [
    r'D:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat',
    r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat',
    r'C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat',
    r'C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat',
    r'C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat',
]


def find_vcvars():
    for p in VCVARS_CANDIDATES:
        if os.path.isfile(p):
            return p
    # 兜底：让 vswhere 找
    vswhere = r'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if os.path.isfile(vswhere):
        try:
            out = subprocess.check_output(
                [vswhere, '-latest', '-products', '*',
                 '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                 '-property', 'installationPath'],
                text=True, stderr=subprocess.DEVNULL).strip()
            if out:
                cand = os.path.join(out, 'VC', 'Auxiliary', 'Build', 'vcvarsall.bat')
                if os.path.isfile(cand):
                    return cand
        except Exception:
            pass
    return None


def duilib_sources():
    """Duilib 的 C++ 源文件（stb_image.c 单独按 C 编译）。"""
    files = []
    for root, _dirs, names in os.walk(DUILIB):
        for n in names:
            if n.lower().endswith('.cpp'):
                files.append(os.path.join(root, n))
    return sorted(files)


def run(cmdline, cwd):
    print('$ ' + cmdline)
    proc = subprocess.run(cmdline, cwd=cwd, shell=True)
    if proc.returncode != 0:
        raise SystemExit('失败：退出码 %d' % proc.returncode)


def fwd(p):
    """转成正斜杠。

    MSVC 的 /Fo 后面如果跟一个以反斜杠结尾的路径，Windows 的命令行解析会
    把结尾的引号当成转义，整条命令就废了。用正斜杠可以绕开这个问题。
    """
    return p.replace('\\', '/')


def ensure_utf8_bom(path):
    """保证源码是 UTF-8 with BOM。

    没有 BOM 时 MSVC 会按系统 ANSI（中文机 = GBK）解码，中文注释里的字节
    会把注释结构搞坏，编译出一堆看不懂的语法错误。这里直接补上。
    """
    with open(path, 'rb') as f:
        raw = f.read()
    if raw.startswith(b'\xef\xbb\xbf'):
        return
    with open(path, 'wb') as f:
        f.write(b'\xef\xbb\xbf' + raw)
    print('提示：已给 %s 补上 UTF-8 BOM' % os.path.basename(path))


def main():
    ap = argparse.ArgumentParser(description='编译 VobSkin.dll')
    ap.add_argument('--arch', default='x86', choices=['x86', 'x64'],
                    help='插件架构。默认 makensis 产出的是 32 位安装程序，插件要匹配。')
    args = ap.parse_args()

    vcvars = find_vcvars()
    if not vcvars:
        raise SystemExit('找不到 vcvarsall.bat，请先装 Visual Studio 的「使用 C++ 的桌面开发」')

    arch = args.arch
    plat = 'Win32' if arch == 'x86' else 'x64'
    objdir = os.path.join(BUILD, arch)
    if os.path.isdir(objdir):
        import shutil
        shutil.rmtree(objdir)
    os.makedirs(objdir)

    cpp = duilib_sources()
    stb = os.path.join(DUILIB, 'Utils', 'stb_image.c')
    plugin_cpp = os.path.join(HERE, 'VobSkin.cpp')
    if not os.path.isfile(stb) or not os.path.isfile(plugin_cpp):
        raise SystemExit('源码不全')
    ensure_utf8_bom(plugin_cpp)

    defines = '/DUILIB_STATIC /DUNICODE /D_UNICODE /D_CRT_SECURE_NO_WARNINGS'
    cflags = '/nologo /c /O2 /MT /EHsc %s /I"%s"' % (defines, fwd(DUILIB))
    objs = fwd(objdir) + '/'

    # 1) 编译 Duilib
    batch = 'call "%s" %s >nul 2>&1 || exit /b 1\n' % (vcvars, arch)
    batch += 'cl %s /Fo"%s" ' % (cflags, objs)
    batch += ' '.join('"%s"' % fwd(f) for f in cpp)
    batch += '\n'

    # 2) 编译 stb_image（C）
    batch += 'cl %s /Fo"%s" "%s"\n' % (cflags, objs, fwd(stb))

    # 3) 编译插件
    batch += 'cl %s /I"%s" /Fo"%s" "%s"\n' % (
        cflags, fwd(os.path.join(HERE, 'sdk')), objs, fwd(plugin_cpp))

    # 4) 打包静态库并链接 DLL
    lib_path = os.path.join(objdir, 'Duilib.lib')
    batch += 'lib /nologo /OUT:"%s" "%s*.obj"\n' % (fwd(lib_path), objs)
    dll_path = os.path.join(BUILD, 'VobSkin.dll')
    batch += ('link /nologo /DLL /OUT:"%s" "%s" "%s" '
              'user32.lib gdi32.lib comctl32.lib ole32.lib oleaut32.lib '
              'shell32.lib advapi32.lib winmm.lib uuid.lib\n'
              % (fwd(dll_path), objs + 'VobSkin.obj', fwd(lib_path)))
    bat_path = os.path.join(BUILD, 'build_%s.bat' % arch)
    with open(bat_path, 'w', encoding='ascii') as f:
        f.write('@echo off\r\n' + batch.replace('\n', '\r\n'))
    run('cmd.exe /c "%s"' % bat_path, HERE)

    if not os.path.isfile(dll_path):
        raise SystemExit('没有产出 DLL')
    print('\n产出：%s  (%.1f KB)' % (dll_path, os.path.getsize(dll_path) / 1024.0))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键构建 Windows 安装包。

    python tools/build_installers.py python              # PyInstaller 目录版 exe → Inno Setup 安装包
    python tools/build_installers.py python --chinese    # 同上，但安装界面为中文
    python tools/build_installers.py flutter             # flutter build windows → NSIS 安装包
    python tools/build_installers.py all

说明：
  * Python 版用 Inno Setup（编译期需要 iscc.exe）；
  * Flutter 版用 NSIS（编译期需要 makensis.exe，且需要先 flutter build windows --release）。
  * 两者都产出到 release/ 目录。
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE = os.path.join(ROOT, 'release')

ISCC_CANDIDATES = [
    r'C:\Program Files (x86)\Inno Setup 7\ISCC.exe',
    r'C:\Program Files\Inno Setup 7\ISCC.exe',
    r'D:\Program Files\Inno Setup 7\ISCC.exe',
    r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    r'C:\Program Files\Inno Setup 6\ISCC.exe',
    r'D:\Program Files\Inno Setup 6\ISCC.exe',
    r'C:\Program Files (x86)\Inno Setup 5\ISCC.exe',
]
MAKENSIS_CANDIDATES = [
    r'C:\Program Files (x86)\NSIS\makensis.exe',
    r'C:\Program Files\NSIS\makensis.exe',
    r'D:\Program Files\NSIS\makensis.exe',
]


def find_tool(candidates, name):
    for p in candidates:
        if os.path.isfile(p):
            return p
    found = shutil.which(name)
    return found


def find_iscc():
    """找 Inno Setup 编译器。

    候选路径覆盖不到的情况很常见（装在 D 盘、装的是 7.x），
    所以再查一次卸载注册表，最后才退回 PATH。
    """
    for p in ISCC_CANDIDATES:
        if os.path.isfile(p):
            return p
    try:
        import winreg
        base = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    except OSError:
                        continue
                    with sub:
                        try:
                            display = winreg.QueryValueEx(sub, 'DisplayName')[0]
                        except OSError:
                            continue
                        if 'Inno Setup' not in display:
                            continue
                        try:
                            loc = winreg.QueryValueEx(sub, 'InstallLocation')[0]
                        except OSError:
                            continue
                        cand = os.path.join(loc, 'ISCC.exe')
                        if os.path.isfile(cand):
                            return cand
    except Exception:
        pass
    return shutil.which('iscc')


def run(cmd, cwd=None):
    print('$ ' + ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=cwd)
    if proc.returncode != 0:
        raise SystemExit('失败：退出码 %d' % proc.returncode)


def build_python_installer(chinese=False):
    print('=== Python 版：PyInstaller 目录版 exe ===')
    run([sys.executable, os.path.join(ROOT, 'python', 'build_exe.py'), '--with-cli'],
        cwd=os.path.join(ROOT, 'python'))

    iscc = find_iscc()
    if not iscc:
        print('\n!! 找不到 Inno Setup 编译器（iscc.exe）。'
              '请安装 Inno Setup 6 或 7 后重试： https://jrsoftware.org/isdl.php')
        return
    print('\n=== Python 版：Inno Setup 安装包 ===')
    print('    编译器: %s' % iscc)
    os.makedirs(RELEASE, exist_ok=True)
    cmd = [iscc]
    if chinese:
        cmd += ['/DMyOutputBase=VobSplit-Setup-Python-zh', '/DUseChinese']
    else:
        cmd += ['/DMyOutputBase=VobSplit-Setup-Python']
    cmd.append(os.path.join(ROOT, 'python', 'installer', 'vobsplit.iss'))
    run(cmd, cwd=os.path.join(ROOT, 'python'))


def build_flutter_installer():
    app = os.path.join(ROOT, 'flutter', 'app')
    print('=== Flutter 版：flutter build windows --release ===')
    flutter = shutil.which('flutter')
    if not flutter:
        raise SystemExit('找不到 flutter 命令')
    run([flutter, 'build', 'windows', '--release'], cwd=app)

    # 皮肤位图是生成的（复选框、最小化/关闭、界面标记、进度条前景）
    print('=== 皮肤位图 ===')
    run([sys.executable, os.path.join(ROOT, 'tools', 'build_skin_assets.py')])

    # 自绘皮肤插件要先编出来（NSIS 的 !addplugindir 指向它的产物）
    plugin_dir = os.path.join(app, 'installer', 'plugin')
    if os.path.isdir(plugin_dir):
        print('=== Duilib 皮肤插件 ===')
        run([sys.executable, os.path.join(plugin_dir, 'build_plugin.py')], cwd=plugin_dir)

    makensis = find_tool(MAKENSIS_CANDIDATES, 'makensis')
    if not makensis:
        print('\n!! 找不到 NSIS（makensis.exe）。'
              '请安装 NSIS： https://nsis.sourceforge.io/Download')
        return
    print('\n=== Flutter 版：NSIS 安装包 ===')
    os.makedirs(RELEASE, exist_ok=True)
    # 文件名跟 release/ 里已有的产物保持一致：
    # Windows 不区分大小写，写错大小写不会报错，但换到区分大小写的系统上
    # 就会多出一个大小写不同的重复文件。
    out = os.path.join(RELEASE, 'VobSplit-Win-x64-Setup.exe')
    run([makensis, '/DMyOutFile=' + out,
         os.path.join(app, 'installer', 'vobsplit.nsi')], cwd=app)


def main():
    ap = argparse.ArgumentParser(description='构建 Windows 安装包')
    ap.add_argument('target', nargs='?', default='all',
                    choices=['python', 'flutter', 'all'], help='要构建哪一套')
    ap.add_argument('--chinese', action='store_true',
                    help='Python 版：生成中文安装界面的安装包')
    args = ap.parse_args()

    if args.target in ('python', 'all'):
        build_python_installer(chinese=args.chinese)
    if args.target in ('flutter', 'all'):
        build_flutter_installer()
    print('\nrelease/ 内容：')
    if os.path.isdir(RELEASE):
        for name in sorted(os.listdir(RELEASE)):
            p = os.path.join(RELEASE, name)
            if os.path.isfile(p):
                print('  %-40s %8.1f KB' % (name, os.path.getsize(p) / 1024.0))


if __name__ == '__main__':
    main()

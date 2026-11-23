#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回归测试：安装包的静默安装（/S）和选盘（/D=）是否真的有效。

联想应用商店《PC应用审核规范》要求：  * 安装包支持静默安装，且安装过程中不能出现任何界面
  * 静默安装必须在桌面创建快捷方式
  * 支持用户自选安装目录（快装功能的前提）

所以这两条必须随时能验，不能靠人肉点。跑法：

    python tools/test_silent_install.py

它会编译一个「用户级 + 测试目录」的临时安装包（不碰 HKLM、不需要管理员），
装到 %TEMP% 下再删掉，不影响系统。跑完会清理临时文件。
"""
import os
import shutil
import subprocess
import time

import winreg

REPO = r'D:\VOB-Splitter'
INST = os.path.join(REPO, 'flutter', 'app', 'installer')
TEST_NSI = os.path.join(INST, '_silent.nsi')
TEST_EXE = os.path.join(REPO, '_silent_test.exe')
TMP = os.environ['TEMP']
TARGET = os.path.join(TMP, 'vobsilent')
ALT = os.path.join(TMP, 'vobsilent_alt')


def desktop_dir():
    """桌面真实路径。

    别用 os.path.expanduser('~') + '\\Desktop' —— 桌面可能被重定向到
    OneDrive 或别的盘（这台机器就在 D:\\Users\\Lenovo\\Desktop）。
    """
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion'
                            r'\Explorer\User Shell Folders') as k:
            p = winreg.QueryValueEx(k, 'Desktop')[0]
        return os.path.expandvars(p)
    except OSError:
        return os.path.join(os.path.expanduser('~'), 'Desktop')


DESKTOP_LNK = os.path.join(desktop_dir(), 'VOB Splitter.lnk')


def make_nsi():
    raw = open(os.path.join(INST, 'vobsplit.nsi'), 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    t = raw.decode('utf-8-sig' if bom else 'utf-8')
    t = t.replace('RequestExecutionLevel admin', 'RequestExecutionLevel user')
    t = t.replace('InstallDir "$PROGRAMFILES64\\${APPNAME}"',
                  'InstallDir "$TEMP\\vobsilent"')
    t = t.replace('InstallDirRegKey HKLM "${APPREGKEY}" InstallDir\r\n', '')
    t = t.replace('InstallDirRegKey HKLM "${APPREGKEY}" InstallDir\n', '')
    t = t.replace('HKLM', 'HKCU')
    open(TEST_NSI, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + t.encode('utf-8'))


def build():
    r = subprocess.run(['C:\\Program Files (x86)\\NSIS\\makensis.exe',
                        '/DMyOutFile=' + TEST_EXE, '_silent.nsi'],
                       cwd=INST, capture_output=True, text=True)
    if 'Error' in r.stdout or 'rror' in r.stdout:
        print(r.stdout[-1500:])
        raise SystemExit('编译失败')
    print('测试包已编译')


def count(d):
    if not os.path.isdir(d):
        return 0
    return sum(len(f) for _, _, f in os.walk(d))


def cleanup():
    for d in (TARGET, ALT):
        shutil.rmtree(d, ignore_errors=True)
    if os.path.exists(DESKTOP_LNK):
        os.remove(DESKTOP_LNK)


def run(args, label, expect_dir):
    cleanup()
    print('\n=== %s ===' % label)
    print('命令:', ' '.join(args))
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, text=True, timeout=180)
    print('退出码:', r.returncode, ' 用时: %.1fs' % (time.time() - t0))
    if r.stdout.strip():
        print('stdout:', r.stdout.strip()[:400])
    n = count(expect_dir)
    print('目标目录:', expect_dir)
    print('  存在:', os.path.isdir(expect_dir), ' 文件数:', n)
    print('桌面快捷方式:', os.path.exists(DESKTOP_LNK))
    if os.path.isdir(expect_dir):
        for root, dirs, files in os.walk(expect_dir):
            for f in files:
                print('   ', os.path.relpath(os.path.join(root, f), expect_dir))
    return n


def main():
    make_nsi()
    build()

    n1 = run([TEST_EXE, '/S'], '静默安装 /S', TARGET)
    ok1 = (n1 > 0) and os.path.exists(DESKTOP_LNK)
    print('\n>>> 静默安装:', '通过' if ok1 else '!! 失败')

    n2 = run([TEST_EXE, '/S', '/D=' + ALT], '静默安装 + 选盘 /D=', ALT)
    ok2 = (n2 > 0)
    print('\n>>> /D= 选盘:', '通过' if ok2 else '!! 失败')

    cleanup()
    for p in (TEST_NSI, TEST_EXE):
        if os.path.exists(p):
            os.remove(p)
    print('\n清理完成')


if __name__ == '__main__':
    main()

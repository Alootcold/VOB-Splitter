#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证：安装（点真实按钮）→ 卸载（点真实按钮 + 静默两种）。

要点：
  * 点击前必须把窗口置顶，否则点击会落到前台的其它窗口上。
  * 按钮坐标不靠手算 —— 插件在运行时把可见控件的位置写进
    %VOB_SKIN_RECTS%，这里读最后一段。
  * 本进程要 DPI 感知：GetWindowRect 才是物理像素，跟截图对得上；
    插件报的是安装器进程的逻辑像素，两者差一个缩放比，
    缩放比 = 截图尺寸 / 皮肤 XML 里写的窗口尺寸。
"""
import ctypes
import ctypes.wintypes as w
import os
import re
import shutil
import subprocess
import time

from PIL import ImageGrab

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
except Exception:
    pass

REPO = r'D:\VOB-Splitter'
INST = os.path.join(REPO, 'flutter', 'app', 'installer')
TEST_NSI = os.path.join(INST, '_t.nsi')
TEST_EXE = os.path.join(REPO, '_utest.exe')
TARGET = os.path.join(os.environ['TEMP'], 'vobtest')
RECTS = os.path.join(os.environ['TEMP'], 'vobskin_rects.txt')
SHOTS = os.path.join(os.environ['TEMP'], 'vobshots')

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [('left', w.LONG), ('top', w.LONG),
                ('right', w.LONG), ('bottom', w.LONG)]


def skin_size(xml_name):
    """从皮肤 XML 里读窗口尺寸（逻辑像素）。"""
    text = open(os.path.join(INST, 'skin', xml_name), 'r', encoding='utf-8-sig').read()
    m = re.search(r'<Window[^>]*size="(\d+),(\d+)"', text)
    return int(m.group(1)), int(m.group(2))


def make_test_nsi():
    raw = open(os.path.join(INST, 'vobsplit.nsi'), 'rb').read()
    bom = raw.startswith(b'\xef\xbb\xbf')
    t = raw.decode('utf-8-sig' if bom else 'utf-8')
    t = t.replace('RequestExecutionLevel admin', 'RequestExecutionLevel user')
    t = t.replace('InstallDir "$PROGRAMFILES64\\${APPNAME}"',
                  'InstallDir "$TEMP\\vobtest"')
    t = t.replace('InstallDirRegKey HKLM "${APPREGKEY}" InstallDir\r\n', '')
    t = t.replace('InstallDirRegKey HKLM "${APPREGKEY}" InstallDir\n', '')
    t = t.replace('HKLM', 'HKCU')
    open(TEST_NSI, 'wb').write((b'\xef\xbb\xbf' if bom else b'') + t.encode('utf-8'))


def build():
    r = subprocess.run(['C:\\Program Files (x86)\\NSIS\\makensis.exe',
                        '/DMyOutFile=' + TEST_EXE, '_t.nsi'],
                       cwd=INST, capture_output=True, text=True)
    if 'Error' in r.stdout:
        print(r.stdout[-1500:])
        raise SystemExit('编译失败')
    print('测试包已编译')


def find_skin(pid=None):
    """找皮肤窗口。

    卸载器有个坑：NSIS 会把卸载器复制到临时目录（Un.exe）再运行，
    界面窗口属于**那个**进程，不是我们启动的那个 pid。
    所以先按 pid 找，找不到就退化成按窗口类名找可见窗口。
    EnumWindows 是按 Z 序枚举的，最新的窗口在最前面。
    """
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    res = []

    def cb(h, l):
        p = w.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        if cls.value == 'VobSkinWindowClass' and user32.IsWindowVisible(h):
            res.append((h, p.value))
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    if not res:
        return None
    if pid:
        for h, p in res:
            if p == pid:
                return h
    return res[0][0]


def kill_leftovers():
    """清掉上次跑剩下的卸载器进程（Un.exe 是 NSIS 的临时副本）。"""
    for name in ('Un.exe', 'uninstall.exe'):
        subprocess.run(['taskkill', '/F', '/IM', name], capture_output=True)
    time.sleep(1.0)


def count_files(d):
    return sum(len(f) for _, _, f in os.walk(d)) if os.path.isdir(d) else 0


def wait_skin(proc, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        hwnd = find_skin(proc.pid)
        if hwnd:
            # 等界面稳定下来（NSIS 卸载器会先复制自己再起界面）
            time.sleep(1.5)
            again = find_skin(proc.pid)
            return again or hwnd
        time.sleep(0.3)
    return None


def read_rects():
    """读插件导出的控件坐标，取最后一段（= 当前这一页）。"""
    try:
        with open(RECTS, 'rb') as f:
            raw = f.read()
    except OSError:
        return {}
    text = raw.decode('utf-16-le', errors='ignore')
    blocks = [b for b in text.split('###') if b.strip()]
    if not blocks:
        return {}
    out = {}
    for line in blocks[-1].splitlines():
        parts = line.split('\t')
        if len(parts) != 5:
            continue
        try:
            out[parts[0].strip()] = tuple(int(x) for x in parts[1:5])
        except ValueError:
            pass
    return out


def wait_rect(name, timeout=8):
    """等某个控件出现在坐标表里。"""
    end = time.time() + timeout
    while time.time() < end:
        r = read_rects()
        if name in r:
            return r[name]
        time.sleep(0.25)
    return None


def capture(hwnd, name, xml_name):
    """抓窗口区域存 PNG，返回 (图片路径, 缩放比)。"""
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)   # 置顶
    time.sleep(0.4)
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    img = ImageGrab.grab(bbox=(rc.left, rc.top, rc.right, rc.bottom))
    if not os.path.isdir(SHOTS):
        os.makedirs(SHOTS, exist_ok=True)
    path = os.path.join(SHOTS, name + '.png')
    img.save(path)
    lw, lh = skin_size(xml_name)
    print('    截图 %s (%dx%d, 逻辑 %dx%d)' % (path, img.width, img.height, lw, lh))
    return path, (img.width / float(lw), img.height / float(lh))


def wait_until(pred, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.25)
    return False


def click(hwnd, name, scale=(1.0, 1.0), after=None, expect_gone=None,
          expect_hidden=False):
    """按名字点按钮：坐标从插件的坐标表里取。

    只点一次 —— 第二次点下去可能落到别的页面的按钮上
    （卸载很快，点完「开始卸载」0.9 秒后就翻到完成页，
    第二次点击正好把「完成」也点了，窗口就没了）。
    点完检查状态：expect_gone 是「这个控件应该从坐标表里消失」，
    expect_hidden 是「窗口应该关掉」；没生效就再点一次。
    """
    rect = wait_rect(name)
    if not rect:
        raise SystemExit('找不到控件 %s 的坐标' % name)
    x, y, w, h = rect
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    sx = int(rc.left + (x + w / 2.0) * scale[0])
    sy = int(rc.top + (y + h / 2.0) * scale[1])
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
    time.sleep(0.3)
    saved = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(saved))
    try:
        for attempt in range(3):
            user32.SetCursorPos(sx, sy)
            time.sleep(0.25)
            user32.mouse_event(0x0002, 0, 0, 0, 0)   # 左键按下
            time.sleep(0.08)
            user32.mouse_event(0x0004, 0, 0, 0, 0)   # 左键抬起
            time.sleep(0.5)
            if after:
                after()
            if expect_gone:
                if wait_until(lambda: expect_gone not in read_rects(), 3.0):
                    break
            elif expect_hidden:
                if wait_until(lambda: not user32.IsWindowVisible(hwnd), 3.0):
                    break
            else:
                break
    finally:
        user32.SetCursorPos(saved.x, saved.y)
    print('    点击 %s @ (%d,%d)' % (name, sx, sy))


def check_minimize(hwnd, scale):
    """最小化按钮：点一下窗口应该变成最小化状态（任务栏上还在）。"""
    rect = wait_rect('btnMin')
    if not rect:
        raise SystemExit('找不到 btnMin 的坐标')
    x, y, w, h = rect
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    sx = int(rc.left + (x + w / 2.0) * scale[0])
    sy = int(rc.top + (y + h / 2.0) * scale[1])
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
    time.sleep(0.3)
    saved = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(saved))
    user32.SetCursorPos(sx, sy)
    time.sleep(0.25)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.8)
    user32.SetCursorPos(saved.x, saved.y)
    ok = user32.IsIconic(hwnd)
    print('    最小化按钮：IsIconic =', bool(ok))
    # 还原回去，后面的步骤还要用这个窗口
    user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    time.sleep(0.8)
    return bool(ok)


def run_install():
    print('\n--- 安装（点真实按钮）---')
    if os.path.exists(RECTS):
        os.remove(RECTS)
    proc = subprocess.Popen([TEST_EXE])
    try:
        hwnd = wait_skin(proc)
        if not hwnd:
            raise SystemExit('没找到安装界面')
        time.sleep(1.2)
        _, scale = capture(hwnd, 'install-1-config', 'setup.xml')
        check_minimize(hwnd, scale)
        click(hwnd, 'btnInstall', scale,
              after=lambda: capture(hwnd, 'install-2-progress', 'setup.xml'),
              expect_gone='btnInstall')
        wait_until(lambda: 'btnFinish' in read_rects(), 12)
        capture(hwnd, 'install-3-done', 'setup.xml')
        click(hwnd, 'btnFinish', scale, expect_hidden=True)
        time.sleep(1.5)
    finally:
        try:
            proc.kill()
        except Exception:
            pass
    # 完成页默认勾选「启动 VOB Splitter」，测试里这应用会被启动，
    # 它会锁住自己的 DLL，卸载就删不掉了 —— 先杀掉。
    subprocess.run(['taskkill', '/F', '/IM', 'vobsplit_gui.exe'],
                   capture_output=True)
    time.sleep(2)
    print('安装后文件数:', count_files(TARGET))


def run_uninstall_ui():
    print('\n--- 卸载（自绘界面，点真实按钮）---')
    kill_leftovers()
    if os.path.exists(RECTS):
        os.remove(RECTS)
    unin = os.path.join(TARGET, 'uninstall.exe')
    proc = subprocess.Popen([unin])
    try:
        hwnd = wait_skin(proc)
        if not hwnd:
            raise SystemExit('没找到卸载界面')
        time.sleep(1.0)
        _, scale = capture(hwnd, 'uninstall-1-confirm', 'uninstall.xml')
        click(hwnd, 'btnUninstall', scale,
              after=lambda: capture(hwnd, 'uninstall-2-progress', 'uninstall.xml'),
              expect_gone='btnUninstall')
        wait_until(lambda: 'btnFinish' in read_rects(), 12)
        capture(hwnd, 'uninstall-3-done', 'uninstall.xml')
        click(hwnd, 'btnFinish', scale, expect_hidden=True)
        time.sleep(2.5)
    finally:
        try:
            proc.kill()
        except Exception:
            pass
    kill_leftovers()
    time.sleep(1.0)
    print('卸载后文件数:', count_files(TARGET))
    print('目录还在:', os.path.isdir(TARGET))


def run_uninstall_silent():
    print('\n--- 卸载（/S 静默）---')
    unin = os.path.join(TARGET, 'uninstall.exe')
    print('卸载器存在:', os.path.isfile(unin))
    if os.path.isfile(unin):
        r = subprocess.run([unin, '/S'], capture_output=True, text=True, timeout=120)
        print('卸载器退出码:', r.returncode)
        time.sleep(2)
        print('卸载后文件数:', count_files(TARGET))
        print('目录还在:', os.path.isdir(TARGET))


def main():
    if os.path.isdir(TARGET):
        try:
            shutil.rmtree(TARGET)
        except Exception as e:
            print('旧目录清理不干净（忽略）:', e)
    make_test_nsi()
    build()

    run_install()
    run_uninstall_ui()

    # 再装一遍，验证静默卸载（/S 不走自绘界面，删除动作在卸载段里）
    print('\n--- 重装，验证静默卸载 ---')
    if os.path.isdir(TARGET):
        try:
            shutil.rmtree(TARGET)
        except Exception:
            pass
    run_install()
    run_uninstall_silent()


if __name__ == '__main__':
    os.environ['VOB_SKIN_RECTS'] = RECTS
    main()

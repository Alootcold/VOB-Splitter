#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
给联想应用商店准备截图：应用窗口的客户区固定 1280x720（商店要求）。

用法：
    python tools/shot_store_screens.py          # 跑一遍，产出到 release/store/
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

from PIL import ImageGrab

REPO = r'D:\VOB-Splitter'
EXE = os.path.join(REPO, 'flutter', 'app', 'build', 'windows', 'x64',
                   'runner', 'Release', 'vobsplit_gui.exe')
OUT = os.path.join(REPO, 'release', 'store')
# 演示目录放在 D 盘根下：路径短，截图里输入框能完整显示，不会被截断
DEMO = r'D:\vobdemo'
SAMPLE = os.path.join(DEMO, 's2.vob')
OUTDIR = os.path.join(DEMO, 'out')

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [('left', w.LONG), ('top', w.LONG),
                ('right', w.LONG), ('bottom', w.LONG)]


def find_window(title_part):
    res = []

    def cb(h, l):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        t = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, t, 256)
        if title_part in t.value and user32.IsWindowVisible(h):
            res.append(h)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
    return res[0] if res else None

def set_client_size(hwnd, cw, ch):
    """把客户区调整成 cw x ch（窗口还要加上标题栏和边框）。"""
    wr = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(wr))
    cr = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    dw = (wr.right - wr.left) - (cr.right - cr.left)
    dh = (wr.bottom - wr.top) - (cr.bottom - cr.top)
    user32.SetWindowPos(hwnd, 0, 0, 0, cw + dw, ch + dh, 0x0004 | 0x0010)
    time.sleep(0.6)


def client_box(hwnd):
    """客户区在屏幕上的位置和尺寸。"""
    cr = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cr))
    p = w.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return (p.x, p.y, p.x + cr.right, p.y + cr.bottom)


def capture_client(hwnd, name):
    box = client_box(hwnd)
    img = ImageGrab.grab(bbox=box)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    img.save(path)
    print('  %s  %dx%d' % (path, img.width, img.height))
    return path


def click_at(hwnd, x, y):
    """在客户区坐标 (x,y) 处点一下。"""
    box = client_box(hwnd)
    user32.SetCursorPos(box[0] + x, box[1] + y)
    time.sleep(0.2)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.4)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', w.WORD), ('wScan', w.WORD), ('dwFlags', w.DWORD),
                ('time', w.DWORD), ('dwExtraInfo', ctypes.POINTER(w.ULONG))]


class INPUTUNION(ctypes.Union):
    # x64 下 INPUT 必须是 40 字节：type(4) + padding(4) + union(32)。
    # ctypes.wintypes 里没有 MOUSEINPUT / HARDWAREINPUT，
    # 用 32 字节的 padding 占住 union 的尺寸。
    _fields_ = [('ki', KEYBDINPUT), ('pad', ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', w.DWORD), ('u', INPUTUNION)]


INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


def type_text(text):
    """用 SendInput 的 Unicode 通道逐字符输入。

    keybd_event + VkKeyScan 对非键盘字符（路径里的 : \\ .）不可靠，
    SendInput + KEYEVENTF_UNICODE 直接按码点送，不受键盘布局影响。
    """
    for ch in text:
        for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.ki = KEYBDINPUT(0, ord(ch), flags, 0, None)
            sent = user32.SendInput(1, ctypes.byref(inp),
                                    ctypes.sizeof(INPUT))
            if sent != 1:
                raise SystemExit('SendInput 失败（cbSize=%d，期望 40）'
                                 % ctypes.sizeof(INPUT))
        time.sleep(0.008)


def select_all_and_clear():
    """Ctrl+A 全选 + Delete（Flutter 的 TextField 支持）。"""
    for vk in (0x11, 0x41):        # Ctrl down, A down
        user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(0x41, 0, 0x0002, 0)
    user32.keybd_event(0x11, 0, 0x0002, 0)
    time.sleep(0.2)
    user32.keybd_event(0x2E, 0, 0, 0)          # Delete
    user32.keybd_event(0x2E, 0, 0x0002, 0)
    time.sleep(0.2)


def main():
    if not os.path.isfile(EXE):
        raise SystemExit('找不到 %s（先跑 flutter build windows --release）' % EXE)
    # 准备演示用的短路径目录
    os.makedirs(OUTDIR, exist_ok=True)
    if not os.path.isfile(SAMPLE):
        subprocess.run([sys.executable,
                        os.path.join(REPO, 'tools', 'make_sample_vob.py'),
                        SAMPLE], check=True)

    proc = subprocess.Popen([EXE])
    try:
        hwnd = None
        for _ in range(40):
            time.sleep(0.4)
            hwnd = find_window('VOB Splitter')
            if hwnd:
                break
        if not hwnd:
            raise SystemExit('找不到应用窗口')
        time.sleep(1.5)

        set_client_size(hwnd, 1280, 720)
        capture_client(hwnd, '01-main-empty.png')

        # 源路径、输出路径：都是可输入的文本框，直接敲进去
        # （坐标是客户区坐标，按 1280x720 的实际布局量的）
        click_at(hwnd, 100, 63)
        select_all_and_clear()
        type_text(SAMPLE)
        time.sleep(0.6)
        click_at(hwnd, 100, 356)
        select_all_and_clear()
        type_text(OUTDIR)
        time.sleep(0.6)
        capture_client(hwnd, '02-filled.png')

        # 切分方式：指定点 + 勾上「包含菜单 VOB」，展示另一种切分方式
        click_at(hwnd, 232, 205)
        time.sleep(0.4)
        click_at(hwnd, 33, 116)
        time.sleep(0.4)
        capture_client(hwnd, '03-modes.png')

        # 换回按章节，开始分割：先扫章节，再切分 + 校验
        click_at(hwnd, 62, 205)
        time.sleep(0.4)
        click_at(hwnd, 160, 679)
        time.sleep(1.4)
        capture_client(hwnd, '04-chapters.png')
        time.sleep(6.0)
        capture_client(hwnd, '05-verified.png')
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == '__main__':
    main()

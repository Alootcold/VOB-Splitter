#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动 NSIS 安装包并截图，用来人工核对自绘皮肤。

    python tools/shot_installer.py <installer.exe> <out.png> [等待秒数]

两种抓法：
  1) 先把窗口挪到屏幕左上、置前台，再按屏幕坐标截 —— 最直观；
  2) 抓不到就用 PrintWindow + 自建 DIB section —— 自绘窗口的兜底。
"""
import ctypes
import ctypes.wintypes as w
import subprocess
import sys
import time

from PIL import Image, ImageGrab

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# 让本进程自己感知 DPI：否则 GetWindowRect 给的是虚拟化坐标，
# 而 ImageGrab 抓的是物理像素，两边对不上（系统是 150% 缩放）。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_AWARE
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

PW_RENDERFULLCONTENT = 0x00000002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
RDW_UPDATENOW = 0x0100
RDW_ALLCHILDREN = 0x0080


class RECT(ctypes.Structure):
    _fields_ = [('left', w.LONG), ('top', w.LONG),
                ('right', w.LONG), ('bottom', w.LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', w.DWORD), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', w.WORD),
                ('biBitCount', w.WORD), ('biCompression', w.DWORD),
                ('biSizeImage', w.DWORD), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', w.DWORD),
                ('biClrImportant', w.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', w.DWORD * 3)]


def find_window(pid, timeout=20.0):
    """找该进程里面积最大的可见顶层窗口。

    NSIS 自己也有一个隐藏的主对话框（标题是 "<Name> Setup"），
    按面积挑才不会抓错。
    """
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = []

        def cb(hwnd, lparam):
            p = w.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid:
                rc = RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rc))
                area = (rc.right - rc.left) * (rc.bottom - rc.top)
                if area > 1000 and user32.IsWindowVisible(hwnd):
                    n = user32.GetWindowTextLengthW(hwnd)
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    hits.append((area, hwnd, buf.value))
            return True

        user32.EnumWindows(EnumProc(cb), 0)
        if hits:
            hits.sort(reverse=True)
            return hits[0][1], hits[0][2]
        time.sleep(0.3)
    return None


def capture_printwindow(hwnd, width, height):
    hdc = user32.GetWindowDC(hwnd)
    memdc = gdi32.CreateCompatibleDC(hdc)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = width
    bi.bmiHeader.biHeight = -height          # 负数 = 自上而下
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0           # BI_RGB
    bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(hdc, ctypes.byref(bi), 0,
                                 ctypes.byref(bits), None, 0)
    old = gdi32.SelectObject(memdc, hbm)
    user32.PrintWindow(hwnd, memdc, PW_RENDERFULLCONTENT)
    raw = ctypes.string_at(bits, width * height * 4)
    gdi32.SelectObject(memdc, old)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(memdc)
    user32.ReleaseDC(hwnd, hdc)
    return Image.frombytes('RGBA', (width, height), raw)


def capture(hwnd, path):
    # 置顶（但不移动！移动会让这个自绘窗口直接消失），屏幕截图就抓得到
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | 0x0002 | 0x0040)
    user32.SetForegroundWindow(hwnd)
    user32.RedrawWindow(hwnd, None, None, RDW_UPDATENOW | RDW_ALLCHILDREN)
    time.sleep(0.8)

    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    width, height = rc.right - rc.left, rc.bottom - rc.top
    if width <= 0 or height <= 0:
        raise SystemExit('窗口尺寸异常：%s' % ((rc.left, rc.top, rc.right, rc.bottom),))

    img = None
    try:
        img = ImageGrab.grab(bbox=(rc.left, rc.top, rc.right, rc.bottom),
                              all_screens=True)
    except Exception:
        img = None
    if img is None or img.width < 10:
        img = capture_printwindow(hwnd, width, height)

    if img.convert('RGB').getextrema()[0] == (255, 255):
        alt = capture_printwindow(hwnd, width, height)
        if alt.convert('RGB').getextrema()[0] != (255, 255):
            img = alt

    img.save(path)
    return img.size


def main():
    exe = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'installer-skin.png'
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 2.5

    proc = subprocess.Popen([exe])
    try:
        found = find_window(proc.pid)
        if not found:
            raise SystemExit('没找到安装器窗口')
        hwnd, title = found
        print('窗口标题: %r  hwnd=%s' % (title, hwnd))
        time.sleep(wait)
        size = capture(hwnd, out)
        print('截图: %s  (%dx%d)' % (out, size[0], size[1]))
    finally:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == '__main__':
    main()

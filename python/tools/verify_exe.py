"""验证打包出来的 exe：真的能启动（并截图），CLI 也能跑。"""
import ctypes
import ctypes.wintypes
import os
import subprocess
import sys
import time

from PIL import ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.dirname(HERE)
DIST = os.path.join(PY, 'dist')
GUI_EXE = os.path.join(DIST, 'vobsplit', 'vobsplit.exe')
CLI_EXE = os.path.join(DIST, 'vobsplit-cli', 'vobsplit-cli.exe')
SHOT = os.path.join(HERE, '..', '..', 'docs', 'gui-exe.png')

user32 = ctypes.windll.user32


def find_window(title_sub):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if title_sub in buf.value:
                found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found


def main():
    print('=== 1. 命令行版 exe ===')
    p = subprocess.run([CLI_EXE, '--version'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    print('exit=%d out=%s' % (p.returncode, p.stdout.strip() or p.stderr.strip()[:200]))

    print('\n=== 2. 图形界面 exe 启动 ===')
    proc = subprocess.Popen([GUI_EXE])
    try:
        win = None
        for _ in range(40):
            time.sleep(0.5)
            hits = find_window('VOB Splitter')
            if hits:
                win = hits[0]
                break
        if not win:
            print('!! 没找到窗口，exe 可能启动失败')
            proc.kill()
            return 1
        hwnd, title = win
        r = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        print('窗口标题: %s' % title)
        print('窗口位置: %d,%d  %dx%d' % (r.left, r.top, r.right - r.left, r.bottom - r.top))
        time.sleep(1.5)
        img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
        out = os.path.abspath(SHOT)
        img.save(out)
        print('截图: %s (%dx%d)' % (out, img.width, img.height))
        print('\nresult: exe launched OK')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    return 0


if __name__ == '__main__':
    sys.exit(main())

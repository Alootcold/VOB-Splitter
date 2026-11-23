"""复现用户的场景：GUI 里直接读 DVD，确认界面有反应（进度在动、日志在出）。

这是「读DVD直接未响应」的针对性验证 —— 修的正是 GUI 轮询链断掉那个 bug。
"""
import os
import sys
import time

sys.path.insert(0, r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter\python")

from vobsplit.gui import VobSplitterApp

DVD = r"G:\VIDEO_TS"
OUT = r"D:\DVD_Splitter_gui_test"

app = VobSplitterApp()
app.src_var.set(DVD)
app.out_var.set(OUT)

# 先让空闲轮询跑几轮 —— 旧版本就是在这里断链的
deadline = time.time() + 0.5
while time.time() < deadline:
    app.update()
    time.sleep(0.02)

print("空闲 0.5s 后，点「开始分割」…")
app._start()

# 观察 25 秒：进度条 / 日志是否在动
last = -1.0
moved = False
logged = False
deadline = time.time() + 25
while time.time() < deadline:
    app.update()
    value = float(app.progress["value"])
    if value > last + 0.001:
        moved = True
    last = value
    if len(app.log.get("1.0", "end").strip()) > 0:
        logged = True
    time.sleep(0.05)

print("进度条当前值 = %.4f" % last)
print("进度条有推进 = %s" % moved)
print("日志有内容   = %s" % logged)
print("状态文字     = %s" % app.status_label.cget("text"))
print("日志前 3 行：")
for line in app.log.get("1.0", "end").strip().splitlines()[:3]:
    print("   ", line)
app.destroy()
print("OK" if (moved and logged) else "FAIL: 界面没有反应")

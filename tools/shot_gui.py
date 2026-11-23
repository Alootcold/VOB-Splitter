"""启动 Python GUI 并截图，用于人工核对界面（不影响交付逻辑）。"""
import os
import sys
import time

sys.path.insert(0, r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter\python")

from PIL import ImageGrab

from vobsplit.chapters import Chapter
from vobsplit.gui import VobSplitterApp

OUT = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter\docs\gui-python.png"
SAMPLE = os.path.join(os.environ["TEMP"], "s2.vob")

app = VobSplitterApp()
app.src_var.set(SAMPLE)
app.out_var.set(r"D:\Split")
app.interval_var.set("600")

# 塞几行假数据，方便核对表格排版
app._set_chapters([
    Chapter(index=i, start_offset=0, end_offset=138842112, start_pts=0.367,
            end_pts=218.247, rap_count=455 + i * 12, global_start=i * 218.0,
            global_end=(i + 1) * 218.0)
    for i in range(6)
])
app.table_hint.configure(text="6 章")

app.update_idletasks()
app.update()

x, y = app.winfo_rootx(), app.winfo_rooty()
w, h = app.winfo_width(), app.winfo_height()
app.after(600, lambda: None)
app.update()
time.sleep(1.2)
app.update()

img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
img.save(OUT)
print("screenshot: %s  (%dx%d)" % (OUT, img.width, img.height))
app.destroy()

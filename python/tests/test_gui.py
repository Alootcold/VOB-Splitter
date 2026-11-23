"""Python 图形界面的端到端测试：真的在界面里点一次「开始分割」。

需要显示器；无图形环境时自动跳过。

    cd python && python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter  # noqa: F401
    HAS_TK = True
except Exception:                                    # pragma: no cover
    HAS_TK = False

if HAS_TK:
    from vobsplit.gui import VobSplitterApp
    import synth


@unittest.skipUnless(HAS_TK, "没有 tkinter，跳过图形界面测试")
class TestGui(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vobsplit-gui-")
        self.sample = os.path.join(self.tmp, "VTS_01_1.VOB")
        synth.write_vob(self.sample, [4.0, 3.0, 5.0])
        self.out = os.path.join(self.tmp, "out")
        self.app = VobSplitterApp()
        self.app.src_var.set(self.sample)
        self.app.out_var.set(self.out)

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pump_until(self, predicate, timeout=30.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.app.update_idletasks()
            self.app.update()
            if predicate():
                return True
            time.sleep(0.05)
        return False

    def test_end_to_end_split(self):
        """点一次开始分割，界面里应该出现章节表，且校验徽章变绿。"""
        self.app._start()
        ok = self._pump_until(lambda: not self.app._running and self.app._verdict is not None)
        self.assertTrue(ok, "切分没有在预期时间内结束")

        rows = self.app.tree.get_children()
        self.assertEqual(len(rows), 3)
        self.assertEqual(self.app.badge_label.cget("text"), "无损校验通过")

        files = sorted(f for f in os.listdir(self.out) if f.endswith(".vob"))
        self.assertEqual(len(files), 3)
        # 拼接后必须等于源文件
        joined = b""
        for name in files:
            with open(os.path.join(self.out, name), "rb") as fh:
                joined += fh.read()
        with open(self.sample, "rb") as fh:
            self.assertEqual(joined, fh.read())

    def test_split_after_idle_still_updates_ui(self):
        """回归：界面空闲一段时间后再点开始，界面必须照样刷新。

        之前轮询链只在「正在运行」时续期，空闲一次就断了 ——
        之后点开始分割，队列没人消费，日志/进度/表格全都不动，看起来就是「未响应」。
        """
        # 先让空闲轮询跑几轮，确保它有机会「断链」
        deadline = time.time() + 0.5
        while time.time() < deadline:
            self.app.update()
            time.sleep(0.02)

        self.app._start()
        ok = self._pump_until(lambda: not self.app._running and self.app._verdict is not None)
        self.assertTrue(ok, "空闲后再切分，界面没有刷新")
        self.assertEqual(len(self.app.tree.get_children()), 3)
        self.assertEqual(self.app.badge_label.cget("text"), "无损校验通过")
        # 日志里应该真的有内容（说明队列被消费了）
        self.assertGreater(len(self.app.log.get("1.0", "end").strip()), 0)

    def test_mode_switch_hides_parameters(self):
        """按章节模式下不该出现时间参数框；切到等长才出现。"""
        # 用 grid_info 而不是 winfo_ismapped —— 测试里窗口没有被真正映射
        self.assertEqual(self.app.param_frame.grid_info(), {})
        self.app.mode_var.set("duration")
        self.app._sync_mode()
        self.app.update_idletasks()
        self.assertNotEqual(self.app.param_frame.grid_info(), {})
        self.app.mode_var.set("auto")
        self.app._sync_mode()
        self.app.update_idletasks()
        self.assertEqual(self.app.param_frame.grid_info(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)

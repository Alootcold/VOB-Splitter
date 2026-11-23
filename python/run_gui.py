"""VOB Splitter 图形界面入口（PyInstaller 用这个当 entry script）。

单独放一个文件，是因为 PyInstaller 以脚本方式运行入口，
包内相对导入（from .xxx import）无法工作，这里改用绝对导入。
"""
import sys

from vobsplit.gui import main

if __name__ == '__main__':
    sys.exit(main())

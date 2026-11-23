"""VOB Splitter 命令行入口（PyInstaller 用这个当 entry script）。"""
import sys

from vobsplit.cli import main

if __name__ == '__main__':
    sys.exit(main())

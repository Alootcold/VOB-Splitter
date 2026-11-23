#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成一个合成的多章节 VOB 样例，方便没有 DVD 的朋友试用这个工具。

    python tools/make_sample_vob.py out.vob            # 默认 5 章
    python tools/make_sample_vob.py out.vob 8          # 8 章
    python tools/make_sample_vob.py out.vob 5 30       # 5 章，每章 30 秒

生成的码流符合 MPEG-2 Program Stream 结构（pack header / 视频 PES / 序列头），
章首时间戳归零 —— 和真实 DVD 分章 VOB 的结构一致，所以切分逻辑完全一致。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'python', 'tests'))

import synth  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = sys.argv[1]
    chapters = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 30.0

    durations = [seconds] * chapters
    paths = synth.write_vob(out, durations)
    size = os.path.getsize(paths[0])
    print('已生成 %s' % paths[0])
    print('  %d 章，每章约 %.1f 秒，合计 %d 字节 (%.1f MiB)'
          % (chapters, seconds, size, size / 1048576.0))
    print()
    print('试试：')
    print('  python -m vobsplit scan  "%s"' % paths[0])
    print('  python -m vobsplit split "%s" -o ./out' % paths[0])


if __name__ == '__main__':
    main()

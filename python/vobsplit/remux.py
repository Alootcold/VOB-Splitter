"""可选的 MKV 重封装（调用 ffmpeg，零重编码）。

VOB 切出来的每一章本身已经是无损的；转 MKV 只是换容器，方便播放。
这个步骤用 ffmpeg 的 stream copy，码流载荷不会被改动。
ffmpeg 不存在时会安静跳过 —— 纯 VOB 分割不依赖 ffmpeg。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional, Sequence


def find_ffmpeg(explicit: Optional[str] = None) -> Optional[str]:
    """找到 ffmpeg：优先用给定路径，其次 PATH，再试几个常见安装位置。"""
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        r"D:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def remux_to_mkv(ffmpeg: str, src: str, dst: str, title: Optional[str] = None,
                 log=None) -> bool:
    """把一个 VOB 重封装成 MKV。返回是否成功。

    -fflags +genpts：切片起点的音频 PES 本身不带时间戳，需要补齐，
    否则 Matroska 封装器会报 "Can't write packet with unknown timestamp"。
    """
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-nostdin", "-y",
           "-fflags", "+genpts", "-i", src,
           "-map", "0:v", "-map", "0:a?", "-c", "copy"]
    if title:
        cmd += ["-metadata", "title=%s" % title]
    cmd += ["-f", "matroska", dst]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if log and proc.stderr:
        log(proc.stderr.strip())
    return proc.returncode == 0


def remux_all(ffmpeg: str, output_dir: str, files: Sequence[str],
              log=None) -> List[str]:
    """批量把输出目录里的 .vob 转成同名 .mkv，返回成功生成的列表。"""
    made: List[str] = []
    for name in files:
        if not name.lower().endswith(".vob"):
            continue
        src = os.path.join(output_dir, name)
        dst = os.path.join(output_dir, name[:-4] + ".mkv")
        title = os.path.splitext(name)[0].replace("_", " ")
        if remux_to_mkv(ffmpeg, src, dst, title=title, log=log):
            made.append(os.path.basename(dst))
    return made

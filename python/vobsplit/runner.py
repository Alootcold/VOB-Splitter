"""切分流程编排（CLI 与 GUI 共用）。

把「扫描 → 推导章节 → 切分 → 可选转 MKV → 校验」这条链路抽出来，
CLI 和 Tkinter 图形界面都调它，保证两者行为一致。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .chapters import Chapter, ChapterSpec, detect_chapters
from .ps import VobSource, build_index
from .remux import find_ffmpeg, remux_all
from .splitter import split


@dataclass
class RunResult:
    """一次完整运行的结果。"""

    output_dir: str
    chapters: List[Chapter] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    mkv_files: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    source_bytes: int = 0
    output_bytes: int = 0
    source_sha256: str = ""
    output_sha256: str = ""
    verified: bool = False
    manifest_path: Optional[str] = None
    saw_no_chapters: bool = False


class Handlers:
    """流程回调。全部可选，未提供就安静地跑。"""

    def __init__(self,
                 log: Optional[Callable[[str], None]] = None,
                 progress: Optional[Callable[[float, str], None]] = None,
                 chapters: Optional[Callable[[List[Chapter]], None]] = None,
                 stats: Optional[Callable[[Dict[str, int]], None]] = None):
        self.log = log
        self.progress = progress
        self.chapters = chapters
        self.stats = stats

    def emit_log(self, message: str) -> None:
        if self.log:
            self.log(message)

    def emit_progress(self, value: float, message: str) -> None:
        if self.progress:
            self.progress(value, message)

    def emit_chapters(self, chapters: List[Chapter]) -> None:
        if self.chapters:
            self.chapters(chapters)

    def emit_stats(self, stats: Dict[str, int]) -> None:
        if self.stats:
            self.stats(stats)


def run_split(files: Sequence[str],
              spec: ChapterSpec,
              output_dir: str,
              prefix: str = "chapter",
              output_format: str = "vob",
              ffmpeg: Optional[str] = None,
              verify: bool = True,
              manifest: bool = True,
              handlers: Optional[Handlers] = None) -> RunResult:
    """跑完整条链路，返回结果。

    output_format: 'vob' | 'mkv' | 'both'
    """
    h = handlers or Handlers()
    result = RunResult(output_dir=output_dir)

    names = [os.path.basename(p) for p in files]
    h.emit_log("扫描: %s" % ", ".join(names))

    source = VobSource(list(files))
    h.emit_log("总大小: %d 字节 (%.2f GiB)"
               % (source.total_size, source.total_size / 1073741824.0))
    h.emit_progress(0.05, "正在扫描码流…")

    raps, stats = build_index(
        source,
        progress=lambda frac: h.emit_progress(
            0.02 + 0.30 * frac, "正在扫描码流… %d%%" % int(100 * frac)))
    result.stats = stats
    h.emit_log("pack=%d  非法pack=%d  视频PES=%d  随机访问点=%d"
               % (stats["packs"], stats["invalid_packs"], stats["video_pes"],
                  stats["raps"]))
    h.emit_stats(stats)

    chapters = detect_chapters(raps, source.total_size, spec)
    result.chapters = chapters
    h.emit_log("检测到 %d 章" % len(chapters))
    h.emit_chapters(chapters)
    if len(chapters) <= 1 and spec.mode == "auto":
        result.saw_no_chapters = True
        h.emit_log("提示: 没检测到章节边界（该 VOB 可能只有一段，或时间戳未重置）。"
                   "可以用 --interval 或 --times 指定切点。")
    h.emit_progress(0.35, "正在切分…")

    split_result = split(source, chapters, output_dir, prefix=prefix,
                         verify=verify, manifest=manifest,
                         progress=lambda done, total, name: h.emit_progress(
                             0.35 + 0.5 * (1 if total == 0 else done / total),
                             "正在切分 %d / %d" % (done, total)))
    result.files = split_result.files
    result.source_bytes = split_result.source_bytes
    result.output_bytes = split_result.output_bytes
    result.source_sha256 = split_result.source_sha256
    result.output_sha256 = split_result.output_sha256
    result.verified = split_result.verified
    result.manifest_path = split_result.manifest_path

    if output_format in ("mkv", "both"):
        h.emit_progress(0.9, "正在转 MKV…")
        exe = find_ffmpeg(ffmpeg)
        if not exe:
            h.emit_log("未找到 ffmpeg，跳过 MKV 转换（VOB 输出已经是无损的）")
        else:
            h.emit_log("用 ffmpeg 转 MKV: %s" % exe)
            result.mkv_files = remux_all(exe, output_dir, result.files, log=h.emit_log)
            h.emit_log("生成 %d 个 MKV" % len(result.mkv_files))

    h.emit_progress(1.0, "完成")
    return result


def fmt_time(seconds: Optional[float]) -> str:
    """秒 -> H:MM:SS.mmm。"""
    if seconds is None:
        return "-"
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return "%d:%02d:%06.3f" % (h, m, s)

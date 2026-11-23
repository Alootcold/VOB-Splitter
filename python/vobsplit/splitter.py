"""切分与校验。

切分是**字节级切片**：每个输出文件就是输入码流的一段连续字节，
原样复制，不重新编码、不重新封装、不改写任何字节。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Sequence

from .chapters import Chapter
from .ps import VobSource

_COPY_CHUNK = 1 << 22


@dataclass
class SplitResult:
    """一次切分的结果与证据。"""

    output_dir: str
    files: List[str] = field(default_factory=list)
    chapters: List[dict] = field(default_factory=list)
    source_bytes: int = 0
    output_bytes: int = 0
    source_sha256: str = ""
    output_sha256: str = ""
    verified: bool = False
    manifest_path: Optional[str] = None

    def summary(self) -> str:
        lines = [
            "输出目录: %s" % self.output_dir,
            "章节数  : %d" % len(self.files),
            "源字节  : %d" % self.source_bytes,
            "出字节  : %d" % self.output_bytes,
            "源SHA256: %s" % self.source_sha256,
            "出SHA256: %s" % self.output_sha256,
            "无损校验: %s" % ("通过（逐字节一致）" if self.verified else "未通过"),
        ]
        return "\n".join(lines)


def _copy_range(source: VobSource, start: int, end: int, dest_path: str,
                digest=None) -> int:
    """把 [start, end) 原样复制到 dest_path，返回写入字节数。

    digest 不为空时顺带把读到的字节累加进哈希 —— 这样校验源流不必再读一遍源
    （对光驱来说能省掉整整一趟读取）。
    """
    written = 0
    with open(dest_path, "wb") as out:
        pos = start
        while pos < end:
            take = min(_COPY_CHUNK, end - pos)
            data = source.read_at(pos, take)
            if not data:
                break
            out.write(data)
            if digest is not None:
                digest.update(data)
            written += len(data)
            pos += len(data)
    return written


def verify_outputs(output_dir: str, files: Sequence[str]) -> "tuple[str, int]":
    """把输出文件按顺序读回来算 SHA-256，用于和源流比对。"""
    digest = hashlib.sha256()
    total = 0
    for name in files:
        path = os.path.join(output_dir, name)
        with open(path, "rb") as fh:
            while True:
                data = fh.read(_COPY_CHUNK)
                if not data:
                    break
                digest.update(data)
                total += len(data)
    return digest.hexdigest(), total


def split(source: VobSource,
          chapters: Sequence[Chapter],
          output_dir: str,
          prefix: str = "chapter",
          suffix: str = ".vob",
          verify: bool = True,
          manifest: bool = True,
          progress=None) -> SplitResult:
    """按章节切分并写出文件。

    verify=True 时会用 SHA-256 证明「各章拼接 == 源流」。
    """
    os.makedirs(output_dir, exist_ok=True)
    result = SplitResult(output_dir=output_dir)

    files: List[str] = []
    src_digest = hashlib.sha256()
    for ch in chapters:
        name = "%s_%02d%s" % (prefix, ch.index + 1, suffix)
        path = os.path.join(output_dir, name)
        _copy_range(source, ch.start_offset, ch.end_offset, path, src_digest)
        files.append(name)
        result.chapters.append({
            "index": ch.index,
            "file": name,
            "start_offset": ch.start_offset,
            "end_offset": ch.end_offset,
            "bytes": ch.size,
            "start_pts": ch.start_pts,
            "end_pts": ch.end_pts,
            "duration": ch.duration,
            "rap_count": ch.rap_count,
        })
        if progress is not None:
            progress(ch.index + 1, len(chapters), name)

    result.files = files
    result.output_bytes = sum(c["bytes"] for c in result.chapters)
    result.source_bytes = source.total_size

    if verify:
        # 章节完整覆盖整条流时，切分过程中顺带算出的源流哈希就可以直接用；
        # 否则老老实实再读一遍源（宁可慢，也不能算错）。
        covered = sum(ch.size for ch in chapters)
        if (chapters and chapters[0].start_offset == 0
                and covered == source.total_size):
            result.source_sha256 = src_digest.hexdigest()
        else:
            result.source_sha256 = source.sha256()
        result.output_sha256, out_total = verify_outputs(output_dir, files)
        result.verified = (result.source_sha256 == result.output_sha256
                           and out_total == source.total_size)
    else:
        result.verified = False

    if manifest:
        manifest_path = os.path.join(output_dir, "vobsplit-manifest.json")
        payload = {
            "tool": "vobsplit",
            "source_files": [os.path.basename(p) for p in source.paths],
            "source_bytes": source.total_size,
            "source_sha256": result.source_sha256,
            "output_bytes": result.output_bytes,
            "output_sha256": result.output_sha256,
            "verified": result.verified,
            "chapters": result.chapters,
        }
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        result.manifest_path = manifest_path
    return result

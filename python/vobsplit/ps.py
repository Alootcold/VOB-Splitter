"""MPEG-2 Program Stream（DVD VOB）底层解析。

DVD VOB 是 MPEG-2 PS 的一个子集：
  * 整条流被切成固定 2048 字节的 pack
  * 每个 pack 以 pack header（00 00 01 BA）开头，其后是一个 PES
  * 视频在 stream id 0xE0 的 PES 里，PES 负载（ES）以序列头 00 00 01 B3 开头时
    表示一个新的 MPEG-2 sequence

几个容易踩错的常量（写解析器时反复踩过，记在这里）：

  picture_start_code = 00 00 01 00      ← 图像头是 0x00，不是 0xB2
  user_data         = 00 00 01 B2
  sequence_header   = 00 00 01 B3
  extension         = 00 00 01 B5
  group (GOP) header= 00 00 01 B8

PES 内 5 字节时间戳（MPEG-2 版式，marker 落在 byte0/byte2/byte4 的最低位）：
  byte0 = '001x' | PTS[32..30] | marker
  byte1-2 = PTS[29..15] | marker
  byte3-4 = PTS[14..0]  | marker
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

PACK_SIZE = 2048
START_CODE_PACK = b"\x00\x00\x01\xba"
START_CODE_SEQUENCE = b"\x00\x00\x01\xb3"
START_CODE_PICTURE = b"\x00\x00\x01\x00"
STREAM_ID_VIDEO = 0xE0

# PES header 各字段相对 PES 起始位置的偏移
_PES_LEN_OFF = 4
_PES_FLAGS1_OFF = 6
_PES_FLAGS2_OFF = 7
_PES_HDRLEN_OFF = 8
_PES_DATA_OFF = 9

_COPY_CHUNK = 1 << 22  # 4 MiB


def decode_timestamp(raw: bytes) -> Optional[float]:
    """解码 PES 内的 5 字节 PTS / DTS，返回秒；不是合法时间戳则返回 None。"""
    if len(raw) < 5:
        return None
    prefix = raw[0] & 0xF0
    if prefix not in (0x20, 0x30, 0x10, 0x11, 0x01):
        return None
    # marker_bit 必须为 1，用它剔除误命中的字节
    if not (raw[0] & 1) or not (raw[2] & 1) or not (raw[4] & 1):
        return None
    high = (raw[0] >> 1) & 0x07
    mid = (((raw[1] << 8) | raw[2]) >> 1) & 0x7FFF
    low = (((raw[3] << 8) | raw[4]) >> 1) & 0x7FFF
    return ((high << 30) | (mid << 15) | low) / 90000.0


@dataclass(frozen=True)
class RAP:
    """一个随机访问点（Random Access Point）。

    pack_index  该 RAP 所在 pack 在整条码流里的序号
    offset      该 RAP 的字节偏移（= pack_index * 2048）
    pts         该 RAP 视频 PES 的显示时间戳（秒）；没有则为 None
    sequence_start  该 PES 的 ES 是否以序列头开头
    """

    pack_index: int
    offset: int
    pts: Optional[float]
    sequence_start: bool


class VobSource:
    """一条 VOB 码流。

    DVD 把一个标题切成 VTS_xx_1.VOB .. VTS_xx_5.VOB（每个上限 1 GiB），
    它们在码流上是连续的，所以本类把多个文件视作一条流。
    """

    def __init__(self, paths: Sequence[str]):
        if not paths:
            raise ValueError("至少需要一个 VOB 文件")
        self.paths: List[str] = [os.path.abspath(p) for p in paths]
        for p in self.paths:
            if not os.path.isfile(p):
                raise FileNotFoundError(p)
        self.sizes: List[int] = [os.path.getsize(p) for p in self.paths]
        self.starts: List[int] = []
        acc = 0
        for size in self.sizes:
            self.starts.append(acc)
            acc += size
        self.total_size = acc

    def _locate(self, offset: int) -> Optional[Tuple[int, int]]:
        """把整条流的绝对偏移映射到 (文件序号, 文件内偏移)。"""
        for idx, (start, size) in enumerate(zip(self.starts, self.sizes)):
            if start <= offset < start + size:
                return idx, offset - start
        return None

    def read_at(self, offset: int, size: int) -> bytes:
        """从整条流的绝对偏移读出 size 字节。"""
        chunks: List[bytes] = []
        remaining = size
        pos = offset
        while remaining > 0:
            loc = self._locate(pos)
            if loc is None:
                break
            idx, inner = loc
            take = min(remaining, self.sizes[idx] - inner)
            with open(self.paths[idx], "rb") as fh:
                fh.seek(inner)
                chunks.append(fh.read(take))
            pos += take
            remaining -= take
        return b"".join(chunks)

    def iter_chunks(self, chunk_size: int = _COPY_CHUNK) -> Iterator[Tuple[int, bytes]]:
        """按顺序吐出 (绝对偏移, 数据块)。"""
        for idx, path in enumerate(self.paths):
            with open(path, "rb") as fh:
                offset = self.starts[idx]
                while True:
                    data = fh.read(chunk_size)
                    if not data:
                        break
                    yield offset, data
                    offset += len(data)

    def sha256(self) -> str:
        """整条流的 SHA-256。"""
        digest = hashlib.sha256()
        for _, data in self.iter_chunks():
            digest.update(data)
        return digest.hexdigest()


def _find_video_pes(pack: bytes) -> Optional[Tuple[int, Optional[float], bool]]:
    """在单个 pack 内找第一个视频 PES。

    返回 (PES 起始位置, PTS, ES 是否以序列头开头)；没有则 None。
    """
    q = -1
    for cand in range(14, min(27, len(pack) - 3)):
        if pack[cand:cand + 3] == b"\x00\x00\x01":
            q = cand
            break
    if q < 0:
        return None
    if pack[q + 3] != STREAM_ID_VIDEO:
        return None
    # MPEG-2 PES：byte6 高两位为 '10'
    if pack[q + _PES_FLAGS1_OFF] & 0xC0 != 0x80:
        return None
    hdr_len = pack[q + _PES_HDRLEN_OFF]
    es = q + _PES_DATA_OFF + hdr_len
    pts = None
    if pack[q + _PES_FLAGS2_OFF] & 0x80:
        pts = decode_timestamp(pack[q + _PES_DATA_OFF:q + _PES_DATA_OFF + 5])
    seq = es + 4 <= len(pack) and pack[es:es + 4] == START_CODE_SEQUENCE
    return q, pts, seq


def build_index(
    source: VobSource,
    progress=None,
) -> Tuple[List[RAP], dict]:
    """扫描整条码流，建立随机访问点索引。

    一个 pack 被记为 RAP，当且仅当它是某个视频 PES 的起点且该 PES 带 PTS
    （DVD 的 MPEG-2 每个 GOP 的视频 PES 都带 PTS），并且它的 ES 以序列头开头
    或者它紧跟在前一个 RAP 之后 —— 实际上 DVD 上每个带 PTS 的视频 PES 起点
    都是一个可安全切入的位置。

    返回 (RAP 列表, 统计信息)。
    """
    raps: List[RAP] = []
    stats = {"packs": 0, "invalid_packs": 0, "video_pes": 0}
    pack_index = 0
    carry = b""
    carry_abs = 0

    for base, data in source.iter_chunks():
        buf = carry + data
        n = (len(buf) // PACK_SIZE) * PACK_SIZE
        chunk = buf[:n]
        rest = buf[n:]
        for i in range(n // PACK_SIZE):
            off = i * PACK_SIZE
            pack = chunk[off:off + PACK_SIZE]
            stats["packs"] += 1
            if pack[:4] != START_CODE_PACK:
                stats["invalid_packs"] += 1
                pack_index += 1
                continue
            hit = _find_video_pes(pack)
            if hit is None:
                pack_index += 1
                continue
            _, pts, seq = hit
            stats["video_pes"] += 1
            if pts is None and not seq:
                pack_index += 1
                continue
            raps.append(RAP(pack_index=pack_index, offset=carry_abs + off,
                            pts=pts, sequence_start=seq))
            pack_index += 1
        carry = rest
        carry_abs += n
        if progress is not None:
            progress(min(1.0, (carry_abs + len(carry)) / max(source.total_size, 1)))
    stats["raps"] = len(raps)
    return raps, stats


def describe_picture_coding_type(pack: bytes, pic_at: int) -> Optional[int]:
    """读出图像头里的 picture_coding_type（1=I, 2=P, 3=B）。"""
    if pic_at + 6 > len(pack):
        return None
    word = (pack[pic_at + 4] << 8) | pack[pic_at + 5]
    return (word >> 3) & 0x07

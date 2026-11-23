"""合成 MPEG-2 PS (VOB) 测试夹具。

不依赖真实光盘：按 MPEG-2 规范生成 pack header / 视频 PES / 序列头，
可以精确控制「几章、每章多少 GOP、PTS 是否重置」，用来验证
章节检测与字节级无损切分。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

PACK_SIZE = 2048
GOP_INTERVAL = 0.48          # 秒（12 帧 @25fps，DVD 常见值）
FIRST_GOP_PTS = 0.367        # 真实 DVD 上首帧 GOP 的 PTS 量级


class _BitWriter:
    def __init__(self) -> None:
        self._bits: List[int] = []

    def write(self, value: int, count: int) -> None:
        for i in range(count - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def to_bytes(self) -> bytes:
        bits = self._bits[:]
        while len(bits) % 8:
            bits.append(0)
        out = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for b in bits[i:i + 8]:
                byte = (byte << 1) | b
            out.append(byte)
        return bytes(out)


def encode_timestamp(pts90k: int, prefix: int = 0x30) -> bytes:
    """把 90kHz 时间戳编码成 5 字节 PTS/DTS 字段。"""
    hi = (pts90k >> 30) & 0x07
    mid = (pts90k >> 15) & 0x7FFF
    lo = pts90k & 0x7FFF
    return bytes([
        prefix | (hi << 1) | 1,
        (mid >> 7) & 0xFF,
        ((mid & 0x7F) << 1) | 1,
        (lo >> 7) & 0xFF,
        ((lo & 0x7F) << 1) | 1,
    ])


def pack_header(scr90k: int, mux_rate: int = 0x3FFFF) -> bytes:
    """生成 14 字节 MPEG-2 pack header。"""
    w = _BitWriter()
    w.write((scr90k >> 30) & 0x07, 3)
    w.write(1, 1)
    w.write((scr90k >> 15) & 0x7FFF, 15)
    w.write(1, 1)
    w.write(scr90k & 0x7FFF, 15)
    w.write(1, 1)
    w.write(0, 9)          # SCR_ext
    w.write(1, 1)
    w.write(mux_rate, 22)
    w.write(1, 1)
    w.write(1, 1)
    w.write(0x1F, 5)       # reserved
    w.write(0, 3)          # pack_stuffing_length
    w.write(0, 2)          # 补齐到 14 字节
    return b"\x00\x00\x01\xba" + w.to_bytes()


def sequence_header() -> bytes:
    """720x576 / 25fps 的序列头。"""
    h = 0x2D02          # 720 x 576
    v = 0x0240          # 576
    ratio = 0x23        # 16:9, 25fps
    return b"\x00\x00\x01\xb3" + bytes([
        (h >> 4) & 0xFF, ((h & 0x0F) << 4) | ((v >> 8) & 0x0F), v & 0xFF, ratio,
    ])


def gop_header() -> bytes:
    return b"\x00\x00\x01\xb8" + b"\x00\x08\x45\x40"


def picture_header(is_i_frame: bool = True) -> bytes:
    coding_type = 1 if is_i_frame else 2
    temporal = 0x008C
    word = (temporal << 6) | (coding_type << 3)
    return b"\x00\x00\x01\x00" + bytes([(word >> 8) & 0xFF, word & 0xFF, 0x5A, 0x70])


def video_pes(pts90k: int, dts90k: int, es: bytes, length: int) -> bytes:
    """视频 PES（带 PTS 与 DTS），length = PES 包总长（含头部）。"""
    header_data = encode_timestamp(pts90k, 0x30) + encode_timestamp(dts90k, 0x10)
    pes = (b"\x00\x00\x01\xe0"
           + length.to_bytes(2, "big")
           + bytes([0x81, 0xC0, len(header_data)])
           + header_data
           + es)
    return pes


def build_pack(pts_seconds: float, fill: int = 0x55) -> bytes:
    """一个 pack：pack header + 一个视频 PES（PES 负载以序列头开头）。"""
    head = pack_header(int(pts_seconds * 90000))
    es = sequence_header() + gop_header() + picture_header()
    fixed = len(head) + 6 + 3 + 10          # pack header + PES 固定头 + 时间戳
    es_len = PACK_SIZE - fixed
    if es_len < len(es):
        raise ValueError("pack 太小")
    es = es + bytes([fill]) * (es_len - len(es))
    pes = video_pes(int(pts_seconds * 90000), int(pts_seconds * 90000) - 2700,
                    es, 6 + 3 + 10 + len(es))
    pack = head + pes
    assert len(pack) == PACK_SIZE, len(pack)
    return pack


def nav_pack() -> bytes:
    """真实 DVD 的第一个 pack 通常是导航包（stream id 0xBB），不是视频 PES。

    它不是随机访问点 —— 首章必须仍然从字节 0 开始，否则拼接哈希对不上源流。
    """
    head = pack_header(0)
    data = bytes([0x55]) * (PACK_SIZE - len(head) - 9)
    pes = (b"\x00\x00\x01\xbb"
           + (3 + len(data)).to_bytes(2, "big")
           + b"\x80\xc0\x00" + data)
    pack = head + pes
    assert len(pack) == PACK_SIZE, len(pack)
    return pack


def make_vob_bytes(chapter_durations: Sequence[float],
                   gop_interval: float = GOP_INTERVAL,
                   leading_nav: bool = True) -> bytes:
    """生成含若干章的 VOB 码流；每章的 PTS 从 0 重新开始。"""
    out = bytearray()
    if leading_nav:
        out += nav_pack()
    for duration in chapter_durations:
        count = max(1, int(round(duration / gop_interval)))
        for i in range(count):
            out += build_pack(FIRST_GOP_PTS + i * gop_interval)
    return bytes(out)


def write_vob(path: str, chapter_durations: Sequence[float],
              gop_interval: float = GOP_INTERVAL,
              split_at: int = 0,
              leading_nav: bool = True) -> List[str]:
    """写出一个（或按 split_at 切成多个）VOB 文件，返回文件路径列表。"""
    data = make_vob_bytes(chapter_durations, gop_interval, leading_nav)
    if split_at <= 0:
        with open(path, "wb") as fh:
            fh.write(data)
        return [path]
    chunk = (len(data) // split_at // PACK_SIZE) * PACK_SIZE
    paths: List[str] = []
    for i in range(split_at):
        piece = data[i * chunk:(i + 1) * chunk] if i < split_at - 1 else data[i * chunk:]
        p = "%s.%d" % (path, i + 1)
        with open(p, "wb") as fh:
            fh.write(piece)
        paths.append(p)
    return paths

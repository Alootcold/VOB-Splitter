"""vobsplit —— DVD VOB 无损分割工具（纯标准库实现）。

核心保证：输出文件是输入码流的连续字节区间，逐字节复制，
不重新编码、不重新封装、不改写任何一个字节。

公开 API：
    VobSource        把多个 VOB 文件当作一条连续码流
    build_index      扫描码流，建立随机访问点（RAP）索引
    detect_chapters  依据码流特征推导章节边界
    split            按章节切分并写出文件
    verify           用 SHA-256 证明切分无损
"""

from .ps import (
    PACK_SIZE,
    RAP,
    VobSource,
    build_index,
    decode_timestamp,
)
from .chapters import (
    Chapter,
    ChapterSpec,
    detect_chapters,
    parse_time_spec,
)
from .splitter import (
    SplitResult,
    split,
    verify_outputs,
)

__all__ = [
    "PACK_SIZE",
    "RAP",
    "VobSource",
    "build_index",
    "decode_timestamp",
    "Chapter",
    "ChapterSpec",
    "detect_chapters",
    "parse_time_spec",
    "SplitResult",
    "split",
    "verify_outputs",
]

__version__ = "1.0.0"

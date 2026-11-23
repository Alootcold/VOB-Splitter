"""章节边界推导。

DVD 的一个标题被切成若干 *program*（俗称章节），登记在 IFO 的 PGC program map 里，
播放器把它们显示成章节。

关键物理特征：**每一章都是一条独立的 MPEG-2 sequence**，章首会重置时间戳
（PTS 从 ~0 重新开始）。因此在码流里「PTS 回落」就精确对应一个章边界，
而且落点天然是一个随机访问点（序列头 + I 帧），可以安全切入。
这不是某张盘的特例，而是 DVD 通用结构，所以对任意多章节 VOB 都成立。

由此带来一个必须处理的问题：**每章的 PTS 是章内局部时间，不是全局时间**。
所以本模块会额外建立一条「全局时间轴」（章节首尾顺延累加），
用于 --times / --interval 这两种以秒为单位的切分方式。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence

from .ps import RAP

# 同一章内相邻 GOP 的 PTS 步进约 0.48s（12 帧 @25fps）。
# 章首回落幅度远大于此，用 1.0s 作为判定阈值足够安全。
DEFAULT_PTS_DROP = 1.0
# 小于这个长度的「章」视为噪声并合并进上一章
DEFAULT_MIN_CHAPTER = 2.0
# 没有 PTS 时用来估算的 GOP 间隔
FALLBACK_GOP_INTERVAL = 0.48

_TIME_HMS = re.compile(
    r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s?)?\s*$",
    re.IGNORECASE)
_TIME_CLOCK = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)\s*(?:[:：]\s*(\d+(?:\.\d+)?)\s*)?$")


@dataclass(frozen=True)
class Chapter:
    """一个章节：码流里的字节区间 + 时间信息。

    start_pts / end_pts 是**章内局部** PTS（每章都从 ~0 开始）；
    global_start / global_end 是拼起来的**全局**时间轴（秒），
    与播放器显示的章节时间一致。
    """

    index: int
    start_offset: int
    end_offset: int
    start_pts: Optional[float] = None
    end_pts: Optional[float] = None
    rap_count: int = 0
    global_start: float = 0.0
    global_end: float = 0.0

    @property
    def size(self) -> int:
        return self.end_offset - self.start_offset

    @property
    def duration(self) -> Optional[float]:
        """按章内 PTS 跨度估算时长（秒）。"""
        if self.start_pts is None or self.end_pts is None:
            return None
        return max(0.0, self.end_pts - self.start_pts)


@dataclass(frozen=True)
class ChapterSpec:
    """切分方式的描述。"""

    mode: str                        # auto | duration | times | whole
    times: Sequence[float] = ()      # mode=times 的切点（全局秒）
    interval: Optional[float] = None  # mode=duration 的间隔（秒）
    pts_drop: float = DEFAULT_PTS_DROP
    min_chapter: float = DEFAULT_MIN_CHAPTER

    @staticmethod
    def auto(pts_drop: float = DEFAULT_PTS_DROP,
             min_chapter: float = DEFAULT_MIN_CHAPTER) -> "ChapterSpec":
        return ChapterSpec(mode="auto", pts_drop=pts_drop, min_chapter=min_chapter)

    @staticmethod
    def duration(interval: float,
                 min_chapter: float = DEFAULT_MIN_CHAPTER) -> "ChapterSpec":
        return ChapterSpec(mode="duration", interval=interval, min_chapter=min_chapter)

    @staticmethod
    def times(times: Sequence[float],
              min_chapter: float = DEFAULT_MIN_CHAPTER) -> "ChapterSpec":
        return ChapterSpec(mode="times", times=tuple(times), min_chapter=min_chapter)

    @staticmethod
    def whole() -> "ChapterSpec":
        return ChapterSpec(mode="whole")


def parse_time_spec(text: str) -> float:
    """解析时间点，统一成秒。支持：

    '90'  '1:30'  '00:01:30.5'  '1h2m3s'  '2m'
    """
    text = text.strip()
    if not text:
        raise ValueError("空的时间点")
    m = _TIME_CLOCK.match(text)
    if m:
        if m.group(3) is not None:
            return (float(m.group(1)) * 3600 + float(m.group(2)) * 60
                    + float(m.group(3)))
        return float(m.group(1)) * 60 + float(m.group(2))
    m = _TIME_HMS.match(text)
    if m and any(g is not None for g in m.groups()):
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = float(m.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError("无法解析时间点: %r" % text)


def parse_time_list(text: str) -> List[float]:
    """解析逗号/分号/空白分隔的时间点列表。"""
    raw = [t for t in re.split(r"[,;\s]+", text.strip()) if t]
    return [parse_time_spec(t) for t in raw]


def _estimate_gop_interval(raps: Sequence[RAP]) -> float:
    """用相邻 RAP 的 PTS 差估算 GOP 间隔（中位数）。"""
    deltas: List[float] = []
    prev = None
    for rap in raps:
        if rap.pts is None:
            continue
        if prev is not None:
            d = rap.pts - prev
            if 0.05 < d < 5.0:      # 排除章边界处的巨大回落
                deltas.append(d)
        prev = rap.pts
    if not deltas:
        return FALLBACK_GOP_INTERVAL
    deltas.sort()
    return deltas[len(deltas) // 2]


def _detect_by_pts_reset(raps: Sequence[RAP], spec: ChapterSpec) -> List[int]:
    """PTS 回落即章边界，返回 RAP 下标。"""
    bounds: List[int] = []
    prev_pts: Optional[float] = None
    for idx, rap in enumerate(raps):
        if rap.pts is None:
            continue
        if prev_pts is not None and rap.pts < prev_pts - spec.pts_drop:
            bounds.append(idx)
        prev_pts = rap.pts
    return bounds


def _build_chapters(raps: Sequence[RAP], bounds: Sequence[int], total_size: int,
                    spec: ChapterSpec) -> List[Chapter]:
    """把边界下标转成章节区间，并合并过短的碎片。"""
    bounds = sorted(set(b for b in bounds if 0 < b < len(raps)))
    starts = [0] + list(bounds)
    chapters: List[Chapter] = []
    for i, start_idx in enumerate(starts):
        end_idx = bounds[i] if i < len(bounds) else len(raps)
        # 第一章必须从字节 0 开始：真实 DVD 的第一个 pack 往往是导航包（不是 RAP），
        # 若从第一个 RAP 起切就会丢掉开头那段，拼接哈希便对不上源流。
        start_offset = (0 if i == 0
                        else (raps[start_idx].offset if start_idx < len(raps) else 0))
        end_offset = raps[end_idx].offset if end_idx < len(raps) else total_size
        pts_list = [r.pts for r in raps[start_idx:end_idx] if r.pts is not None]
        chapters.append(Chapter(
            index=len(chapters),
            start_offset=start_offset,
            end_offset=end_offset,
            start_pts=pts_list[0] if pts_list else None,
            end_pts=pts_list[-1] if pts_list else None,
            rap_count=end_idx - start_idx,
        ))
    return _merge_short(chapters, spec)


def _merge_short(chapters: List[Chapter], spec: ChapterSpec) -> List[Chapter]:
    """把过短的章并入上一章（第一章永远保留）。"""
    if spec.min_chapter <= 0:
        return chapters
    merged: List[Chapter] = []
    for ch in chapters:
        dur = ch.duration
        prev_dur = merged[-1].duration if merged else None
        if (merged and dur is not None and dur < spec.min_chapter
                and prev_dur is not None and prev_dur >= spec.min_chapter):
            prev = merged.pop()
            merged.append(replace(prev, end_offset=ch.end_offset,
                                   end_pts=ch.end_pts,
                                   rap_count=prev.rap_count + ch.rap_count))
            continue
        merged.append(ch)
    return [replace(c, index=i) for i, c in enumerate(merged)]


def _apply_global_timeline(chapters: List[Chapter], gop_interval: float) -> None:
    """给每章补上全局时间轴（就地修改 dataclass 需重建，故返回新列表）。"""
    out: List[Chapter] = []
    t = 0.0
    for ch in chapters:
        span = ch.duration or 0.0
        out.append(replace(ch, global_start=t, global_end=t + span + gop_interval))
        t += span + gop_interval
    return out


def _snap_in_chapter(chapters: Sequence[Chapter], raps: Sequence[RAP],
                     global_time: float) -> Optional[int]:
    """把一个全局时间点落到具体章节内的某个 RAP，返回 RAP 下标。"""
    target = None
    for i, ch in enumerate(chapters):
        if ch.global_start <= global_time < ch.global_end:
            target = i
            break
    if target is None:
        target = len(chapters) - 1
    ch = chapters[target]
    local = global_time - ch.global_start + (ch.start_pts or 0.0)
    best = None
    for idx, rap in enumerate(raps):
        if rap.offset < ch.start_offset:
            continue
        if rap.offset >= ch.end_offset:
            break
        if rap.pts is None:
            continue
        if rap.pts <= local + 1e-6:
            best = idx
        else:
            break
    return best


def detect_chapters(raps: Sequence[RAP],
                    total_size: int,
                    spec: ChapterSpec) -> List[Chapter]:
    """按 spec 推导章节，返回切分区间列表。"""
    if spec.mode == "whole" or not raps:
        ch = Chapter(index=0, start_offset=0, end_offset=total_size,
                     rap_count=len(raps))
        return [replace(ch, global_start=0.0, global_end=0.0)]

    gop = _estimate_gop_interval(raps)

    if spec.mode == "auto":
        bounds = _detect_by_pts_reset(raps, spec)
        chapters = _build_chapters(raps, bounds, total_size, spec)
        return _apply_global_timeline(chapters, gop)

    # duration / times 都基于全局时间轴，先做一次 auto 结构
    base_bounds = _detect_by_pts_reset(raps, spec)
    base = _build_chapters(raps, base_bounds, total_size,
                           replace(spec, min_chapter=0.0))
    base = _apply_global_timeline(base, gop)
    total_duration = base[-1].global_end if base else 0.0

    if spec.mode == "duration":
        if not spec.interval or spec.interval <= 0:
            raise ValueError("--interval 必须为正数")
        targets: List[float] = []
        t = spec.interval
        while t < total_duration:
            targets.append(t)
            t += spec.interval
    elif spec.mode == "times":
        targets = list(spec.times)
    else:
        raise ValueError("未知模式: %s" % spec.mode)

    bounds = []
    for target in targets:
        idx = _snap_in_chapter(base, raps, target)
        if idx is not None and idx not in bounds:
            bounds.append(idx)
    chapters = _build_chapters(raps, bounds, total_size, spec)
    return _apply_global_timeline(chapters, gop)

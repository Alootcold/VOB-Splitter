/// 章节边界推导。
///
/// DVD 的一个标题被切成若干 *program*（俗称章节），登记在 IFO 的 PGC program map 里，
/// 播放器把它们显示成章节。
///
/// 关键物理特征：**每一章都是一条独立的 MPEG-2 sequence**，章首会重置时间戳
/// （PTS 从 ~0 重新开始）。因此在码流里「PTS 回落」就精确对应一个章边界，
/// 而且落点天然是一个随机访问点（序列头 + I 帧），可以安全切入。
/// 这不是某张盘的特例，而是 DVD 通用结构，所以对任意多章节 VOB 都成立。
///
/// 由此带来一个必须处理的问题：**每章的 PTS 是章内局部时间，不是全局时间**。
/// 所以本模块会额外建立一条「全局时间轴」（章节首尾顺延累加），
/// 用于 --times / --interval 这两种以秒为单位的切分方式。
library;

import 'ps.dart';

/// 同一章内相邻 GOP 的 PTS 步进约 0.48s（12 帧 @25fps）。
/// 章首回落幅度远大于此，用 1.0s 作为判定阈值足够安全。
const double defaultPtsDrop = 1.0;

/// 小于这个长度的「章」视为噪声并合并进上一章。
const double defaultMinChapter = 2.0;

/// 没有 PTS 时用来估算的 GOP 间隔。
const double fallbackGopInterval = 0.48;

/// copyWith 的哨兵值：区分「参数没传」与「显式传 null」。
const Object _unset = Object();

/// 切分方式。
enum SplitMode {
  /// 按 DVD 章节（由 PTS 回落推导）。
  auto,

  /// 等长切分（按全局时间轴）。
  duration,

  /// 指定时间点切分（按全局时间轴）。
  times,

  /// 不切，整条流作为一章。
  whole,
}

/// 一个章节：码流里的字节区间 + 时间信息。
///
/// [startPts] / [endPts] 是**章内局部** PTS（每章都从 ~0 开始）；
/// [globalStart] / [globalEnd] 是拼起来的**全局**时间轴（秒），
/// 与播放器显示的章节时间一致。
class Chapter {
  final int index;
  final int startOffset;
  final int endOffset;
  final double? startPts;
  final double? endPts;
  final int rapCount;
  final double globalStart;
  final double globalEnd;

  const Chapter({
    required this.index,
    required this.startOffset,
    required this.endOffset,
    this.startPts,
    this.endPts,
    this.rapCount = 0,
    this.globalStart = 0.0,
    this.globalEnd = 0.0,
  });

  /// 本章占用的字节数。
  int get size => endOffset - startOffset;

  /// 按章内 PTS 跨度估算时长（秒）。
  double? get duration {
    final s = startPts;
    final e = endPts;
    if (s == null || e == null) {
      return null;
    }
    final d = e - s;
    return d > 0.0 ? d : 0.0;
  }

  Chapter copyWith({
    int? index,
    int? startOffset,
    int? endOffset,
    Object? startPts = _unset,
    Object? endPts = _unset,
    int? rapCount,
    double? globalStart,
    double? globalEnd,
  }) {
    return Chapter(
      index: index ?? this.index,
      startOffset: startOffset ?? this.startOffset,
      endOffset: endOffset ?? this.endOffset,
      // 用哨兵区分「没传」与「显式传 null」，对应 Python dataclasses.replace()
      startPts: identical(startPts, _unset) ? this.startPts : startPts as double?,
      endPts: identical(endPts, _unset) ? this.endPts : endPts as double?,
      rapCount: rapCount ?? this.rapCount,
      globalStart: globalStart ?? this.globalStart,
      globalEnd: globalEnd ?? this.globalEnd,
    );
  }

  @override
  String toString() => 'Chapter(index: $index, startOffset: $startOffset, '
      'endOffset: $endOffset, duration: $duration)';
}

/// 切分方式的描述。
class ChapterSpec {
  final SplitMode mode;

  /// mode=times 的切点（全局秒）。
  final List<double> times;

  /// mode=duration 的间隔（秒）。
  final double? interval;

  /// 判定 PTS 回落的阈值（秒）。
  final double ptsDrop;

  /// 短于该时长的章视为噪声并并入上一章。
  final double minChapter;

  /// 按 DVD 章节自动切分。
  const ChapterSpec.auto({this.ptsDrop = defaultPtsDrop, this.minChapter = defaultMinChapter})
      : mode = SplitMode.auto,
        times = const <double>[],
        interval = null;

  /// 按固定间隔（秒）切分。
  const ChapterSpec.duration(this.interval, {this.minChapter = defaultMinChapter})
      : mode = SplitMode.duration,
        times = const <double>[],
        ptsDrop = defaultPtsDrop;

  /// 按指定的全局时间点（秒）切分。
  const ChapterSpec.times(this.times, {this.minChapter = defaultMinChapter})
      : mode = SplitMode.times,
        interval = null,
        ptsDrop = defaultPtsDrop;

  /// 不切分，整条流作为一章。
  const ChapterSpec.whole()
      : mode = SplitMode.whole,
        times = const <double>[],
        interval = null,
        ptsDrop = defaultPtsDrop,
        minChapter = defaultMinChapter;

  /// 内部用：按字段逐个构造（copyWith 需要）。
  const ChapterSpec._(
    this.mode,
    this.times,
    this.interval,
    this.ptsDrop,
    this.minChapter,
  );

  ChapterSpec copyWith({
    SplitMode? mode,
    List<double>? times,
    double? interval,
    double? ptsDrop,
    double? minChapter,
  }) {
    return ChapterSpec._(
      mode ?? this.mode,
      times ?? this.times,
      interval ?? this.interval,
      ptsDrop ?? this.ptsDrop,
      minChapter ?? this.minChapter,
    );
  }
}

// 00:01:30 / 1:30 / 00:01:30.5（全角冒号也认）
final RegExp _timeClock =
    RegExp(r'^\s*(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)\s*(?:[:：]\s*(\d+(?:\.\d+)?)\s*)?$');

// 1h2m3s / 2m / 90（末尾的 's' 可省略，所以裸数字也能解析）
final RegExp _timeHms = RegExp(
    r'^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s?)?\s*$',
    caseSensitive: false);

/// 解析时间点，统一成秒。支持：
///
/// '90'  '1:30'  '00:01:30.5'  '1h2m3s'  '2m'
double parseTimeSpec(String text) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) {
    throw FormatException('空的时间点', text);
  }
  final clock = _timeClock.firstMatch(trimmed);
  if (clock != null) {
    final g3 = clock.group(3);
    if (g3 != null) {
      return _parseNumberStrict(clock.group(1)!, trimmed) * 3600 +
          _parseNumberStrict(clock.group(2)!, trimmed) * 60 +
          _parseNumberStrict(g3, trimmed);
    }
    return _parseNumberStrict(clock.group(1)!, trimmed) * 60 +
        _parseNumberStrict(clock.group(2)!, trimmed);
  }
  final hms = _timeHms.firstMatch(trimmed);
  if (hms != null &&
      (hms.group(1) != null || hms.group(2) != null || hms.group(3) != null)) {
    final hours = hms.group(1) == null ? 0 : int.parse(hms.group(1)!);
    final minutes = hms.group(2) == null ? 0 : int.parse(hms.group(2)!);
    final seconds = hms.group(3) == null ? 0.0 : double.parse(hms.group(3)!);
    return hours * 3600 + minutes * 60 + seconds;
  }
  throw FormatException('无法解析时间点: $text', text);
}

/// 解析逗号/分号/空白分隔的时间点列表。
List<double> parseTimeList(String text) {
  final raw = text
      .trim()
      .split(RegExp(r'[,;\s]+'))
      .where((t) => t.isNotEmpty)
      .toList();
  return [for (final t in raw) parseTimeSpec(t)];
}

/// 时/分部分必须是整数（Python 版用 int() 解析，遇到小数会直接报错）。
/// 解析数字，失败时给出和 Python 版一致的错误信息。
double _parseNumberStrict(String raw, String original) {
  final value = double.tryParse(raw);
  if (value == null) {
    throw FormatException('无法解析时间点: $original', original);
  }
  return value;
}

/// 用相邻 RAP 的 PTS 差估算 GOP 间隔（中位数）。
double _estimateGopInterval(List<Rap> raps) {
  final deltas = <double>[];
  double? prev;
  for (final rap in raps) {
    final pts = rap.pts;
    if (pts == null) {
      continue;
    }
    if (prev != null) {
      final d = pts - prev;
      if (d > 0.05 && d < 5.0) {
        // 排除章边界处的巨大回落
        deltas.add(d);
      }
    }
    prev = pts;
  }
  if (deltas.isEmpty) {
    return fallbackGopInterval;
  }
  deltas.sort();
  return deltas[deltas.length ~/ 2];
}

/// PTS 回落即章边界，返回 RAP 下标。
List<int> _detectByPtsReset(List<Rap> raps, ChapterSpec spec) {
  final bounds = <int>[];
  double? prevPts;
  for (var idx = 0; idx < raps.length; idx++) {
    final pts = raps[idx].pts;
    if (pts == null) {
      continue;
    }
    if (prevPts != null && pts < prevPts - spec.ptsDrop) {
      bounds.add(idx);
    }
    prevPts = pts;
  }
  return bounds;
}

/// 把边界下标转成章节区间，并合并过短的碎片。
List<Chapter> _buildChapters(
    List<Rap> raps, List<int> bounds, int totalSize, ChapterSpec spec) {
  final sorted = bounds.where((b) => b > 0 && b < raps.length).toSet().toList()
    ..sort();
  final starts = <int>[0, ...sorted];
  final chapters = <Chapter>[];
  for (var i = 0; i < starts.length; i++) {
    final startIdx = starts[i];
    final endIdx = i < sorted.length ? sorted[i] : raps.length;
    // 第一章必须从字节 0 开始：真实 DVD 的第一个 pack 往往是导航包（不是 RAP），
    // 若从第一个 RAP 起切就会丢掉开头那段，拼接哈希便对不上源流。
    final startOffset =
        i == 0 ? 0 : (startIdx < raps.length ? raps[startIdx].offset : 0);
    final endOffset = endIdx < raps.length ? raps[endIdx].offset : totalSize;
    final ptsList = <double>[];
    final limit = endIdx < raps.length ? endIdx : raps.length;
    for (var j = startIdx; j < limit; j++) {
      final pts = raps[j].pts;
      if (pts != null) {
        ptsList.add(pts);
      }
    }
    chapters.add(Chapter(
      index: chapters.length,
      startOffset: startOffset,
      endOffset: endOffset,
      startPts: ptsList.isEmpty ? null : ptsList.first,
      endPts: ptsList.isEmpty ? null : ptsList.last,
      rapCount: endIdx - startIdx,
    ));
  }
  return _mergeShort(chapters, spec);
}

/// 把过短的章并入上一章（第一章永远保留）。
List<Chapter> _mergeShort(List<Chapter> chapters, ChapterSpec spec) {
  if (spec.minChapter <= 0) {
    return chapters;
  }
  final merged = <Chapter>[];
  for (final ch in chapters) {
    final dur = ch.duration;
    final prevDur = merged.isEmpty ? null : merged.last.duration;
    if (merged.isNotEmpty &&
        dur != null &&
        dur < spec.minChapter &&
        prevDur != null &&
        prevDur >= spec.minChapter) {
      final prev = merged.removeLast();
      merged.add(prev.copyWith(
        endOffset: ch.endOffset,
        endPts: ch.endPts,
        rapCount: prev.rapCount + ch.rapCount,
      ));
      continue;
    }
    merged.add(ch);
  }
  return [
    for (var i = 0; i < merged.length; i++) merged[i].copyWith(index: i),
  ];
}

/// 给每章补上全局时间轴（章内时长顺延累加）。
List<Chapter> _applyGlobalTimeline(List<Chapter> chapters, double gopInterval) {
  final out = <Chapter>[];
  var t = 0.0;
  for (final ch in chapters) {
    final span = ch.duration ?? 0.0;
    out.add(ch.copyWith(globalStart: t, globalEnd: t + span + gopInterval));
    t += span + gopInterval;
  }
  return out;
}

/// 把一个全局时间点落到具体章节内的某个 RAP，返回 RAP 下标。
int? _snapInChapter(
    List<Chapter> chapters, List<Rap> raps, double globalTime) {
  int? target;
  for (var i = 0; i < chapters.length; i++) {
    if (chapters[i].globalStart <= globalTime &&
        globalTime < chapters[i].globalEnd) {
      target = i;
      break;
    }
  }
  target ??= chapters.length - 1;
  final ch = chapters[target];
  final local = globalTime - ch.globalStart + (ch.startPts ?? 0.0);
  int? best;
  for (var idx = 0; idx < raps.length; idx++) {
    final rap = raps[idx];
    if (rap.offset < ch.startOffset) {
      continue;
    }
    if (rap.offset >= ch.endOffset) {
      break;
    }
    final pts = rap.pts;
    if (pts == null) {
      continue;
    }
    if (pts <= local + 1e-6) {
      best = idx;
    } else {
      break;
    }
  }
  return best;
}

/// 按 spec 推导章节，返回切分区间列表。
List<Chapter> detectChapters(
    List<Rap> raps, int totalSize, ChapterSpec spec) {
  if (spec.mode == SplitMode.whole || raps.isEmpty) {
    return <Chapter>[
      Chapter(
        index: 0,
        startOffset: 0,
        endOffset: totalSize,
        rapCount: raps.length,
        globalStart: 0.0,
        globalEnd: 0.0,
      ),
    ];
  }

  final gop = _estimateGopInterval(raps);

  if (spec.mode == SplitMode.auto) {
    final bounds = _detectByPtsReset(raps, spec);
    final chapters = _buildChapters(raps, bounds, totalSize, spec);
    return _applyGlobalTimeline(chapters, gop);
  }

  // duration / times 都基于全局时间轴，先做一次 auto 结构
  final baseBounds = _detectByPtsReset(raps, spec);
  var base = _buildChapters(raps, baseBounds, totalSize,
      spec.copyWith(minChapter: 0.0));
  base = _applyGlobalTimeline(base, gop);
  final totalDuration = base.isEmpty ? 0.0 : base.last.globalEnd;

  final List<double> targets;
  if (spec.mode == SplitMode.duration) {
    final interval = spec.interval;
    if (interval == null || interval <= 0) {
      throw ArgumentError('interval 必须为正数');
    }
    targets = <double>[];
    var t = interval;
    while (t < totalDuration) {
      targets.add(t);
      t += interval;
    }
  } else if (spec.mode == SplitMode.times) {
    targets = List<double>.from(spec.times);
  } else {
    throw ArgumentError('未知模式: ${spec.mode}');
  }

  final bounds = <int>[];
  for (final target in targets) {
    final idx = _snapInChapter(base, raps, target);
    if (idx != null && !bounds.contains(idx)) {
      bounds.add(idx);
    }
  }
  final chapters = _buildChapters(raps, bounds, totalSize, spec);
  return _applyGlobalTimeline(chapters, gop);
}

/// 供 CLI 用：把秒数格式化成 0:00:00.000。
String formatTimestamp(double? sec) {
  if (sec == null) {
    return '-';
  }
  final value = sec < 0.0 ? 0.0 : sec;
  final h = (value / 3600).floor();
  final m = ((value % 3600) / 60).floor();
  final s = value % 60;
  final mText = m.toString().padLeft(2, '0');
  final sText = s.toStringAsFixed(3).padLeft(6, '0');
  return '$h:$mText:$sText';
}

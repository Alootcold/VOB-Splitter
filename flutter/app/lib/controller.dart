import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:vobsplit_core/vobsplit_core.dart';

/// 输出形式。
enum OutputFormat { vob, mkv, both }

/// 当前处于哪个阶段。
enum Phase { idle, scanning, splitting, remuxing, done, failed }

/// 界面状态与流程编排。
///
/// 所有码流处理都在纯 Dart 的 vobsplit_core 里完成，这里只负责
/// 收集参数、驱动流程、汇报进度。
class SplitController extends ChangeNotifier {
  // ---- 输入参数 ----
  String sourcePath = '';
  String outputDir = '';
  String prefix = 'chapter';
  SplitMode mode = SplitMode.auto;
  double intervalSeconds = 600;
  String timesText = '';
  bool includeMenu = false;
  OutputFormat format = OutputFormat.vob;

  // ---- 运行状态 ----
  Phase phase = Phase.idle;
  double progress = 0;
  String statusText = '等待开始';
  List<Chapter> chapters = <Chapter>[];
  List<String> logs = <String>[];
  bool? verified;
  String? sourceHash;
  String? outputHash;
  String? error;
  bool sawNoChapters = false;

  bool get busy => phase == Phase.scanning ||
      phase == Phase.splitting ||
      phase == Phase.remuxing;

  bool get canRun =>
      !busy && sourcePath.trim().isNotEmpty && outputDir.trim().isNotEmpty;

  void log(String line) {
    logs.add(line);
    // 日志只保留最后 400 行，避免长时间运行把内存吃满
    if (logs.length > 400) {
      logs.removeRange(0, logs.length - 400);
    }
    notifyListeners();
  }

  void reset() {
    phase = Phase.idle;
    progress = 0;
    statusText = '等待开始';
    chapters = <Chapter>[];
    logs = <String>[];
    verified = null;
    sourceHash = null;
    outputHash = null;
    error = null;
    sawNoChapters = false;
    notifyListeners();
  }

  /// 展开源路径：目录 -> 其中的 .vob（按 VTS_xx_N 数字排序）。
  List<String> resolveSources() {
    final dir = Directory(sourcePath.trim());
    final List<String> files = <String>[];
    if (dir.existsSync()) {
      final vobs = dir
          .listSync()
          .whereType<File>()
          .where((f) => f.path.toLowerCase().endsWith('.vob'))
          .toList();
      vobs.sort((a, b) => _compareVobNames(a.path, b.path));
      for (final f in vobs) {
        if (!includeMenu && _isMenuVob(f.path)) {
          continue;
        }
        files.add(f.path);
      }
    } else {
      files.add(sourcePath.trim());
    }
    return files;
  }

  /// VTS_01_1.VOB < VTS_01_2.VOB < VTS_01_10.VOB（按数字排序，不是字符串排序）。
  static int _compareVobNames(String a, String b) {
    final ka = _vobKey(a);
    final kb = _vobKey(b);
    final byGroup = ka.group.compareTo(kb.group);
    if (byGroup != 0) return byGroup;
    return ka.index.compareTo(kb.index);
  }

  static ({String group, int index}) _vobKey(String path) {
    final name = path.split(RegExp(r'[/\\]')).last;
    final stem = name.replaceAll(RegExp(r'\.vob$', caseSensitive: false), '');
    final parts = stem.split('_');
    final parsed = parts.isNotEmpty ? int.tryParse(parts.last) : null;
    final group = parts.length >= 2 ? parts[parts.length - 2] : stem;
    return (group: group, index: parsed ?? 0);
  }

  static bool _isMenuVob(String path) {
    final name = path.split(RegExp(r'[/\\]')).last;
    final stem = name.replaceAll(RegExp(r'\.vob$', caseSensitive: false), '');
    final parts = stem.split('_');
    if (parts.length < 3) return false;
    return int.tryParse(parts.last) == 0;
  }

  ChapterSpec _buildSpec() {
    switch (mode) {
      case SplitMode.auto:
        return const ChapterSpec.auto();
      case SplitMode.duration:
        return ChapterSpec.duration(intervalSeconds);
      case SplitMode.times:
        return ChapterSpec.times(parseTimeList(timesText));
      case SplitMode.whole:
        return const ChapterSpec.whole();
    }
  }

  Future<void> run() async {
    if (busy) return;
    reset();
    try {
      final files = resolveSources();
      if (files.isEmpty) {
        _fail('没有找到 VOB 文件');
        return;
      }
      final missing = files.where((f) => !File(f).existsSync()).toList();
      if (missing.isNotEmpty) {
        _fail('文件不存在：${missing.first}');
        return;
      }

      log('源文件 ${files.length} 个：${files.map((f) => f.split(RegExp(r'[/\\]')).last).join(', ')}');

      // ---- 扫描 ----
      phase = Phase.scanning;
      statusText = '正在扫描码流…';
      notifyListeners();

      final source = VobSource(files);
      log('总大小 ${source.totalSize} 字节（${(source.totalSize / 1073741824).toStringAsFixed(2)} GiB）');

      final index = await buildIndex(
        source,
        onProgress: (p) {
          progress = p * 0.35;
          statusText = '正在扫描码流… ${(p * 100).toStringAsFixed(0)}%';
          notifyListeners();
        },
      );
      log('pack=${index.stats['packs']}  随机访问点=${index.raps.length}');

      final spec = _buildSpec();
      chapters = detectChapters(index.raps, source.totalSize, spec);
      log('检测到 ${chapters.length} 章');
      for (final c in chapters) {
        log('  第 ${c.index + 1} 章  ${_fmt(c.globalStart)} → ${_fmt(c.globalEnd)}'
            '  ${(c.size / 1048576).toStringAsFixed(1)} MB');
      }
      if (chapters.length <= 1 && mode == SplitMode.auto) {
        sawNoChapters = true;
        log('提示：没有检测到章节边界，可以改用「等长切分」或「指定时间点」。');
      }
      progress = 0.35;
      notifyListeners();

      // ---- 切分 ----
      phase = Phase.splitting;
      statusText = '正在切分…';
      notifyListeners();

      final result = await split(
        source,
        chapters,
        outputDir.trim(),
        prefix: prefix,
        onProgress: (done, total, name) {
          progress = 0.35 + 0.5 * (total == 0 ? 1 : done / total);
          statusText = '正在切分 $done / $total';
          notifyListeners();
        },
      );

      verified = result.verified;
      sourceHash = result.sourceSha256;
      outputHash = result.outputSha256;
      log('源流 SHA-256 ${result.sourceSha256}');
      log('出流 SHA-256 ${result.outputSha256}');
      log(result.verified ? '无损校验通过：逐字节一致' : '无损校验未通过！');

      // ---- 可选转 MKV ----
      if (format == OutputFormat.mkv || format == OutputFormat.both) {
        phase = Phase.remuxing;
        statusText = '正在转 MKV…';
        notifyListeners();
        final ffmpeg = findFfmpeg();
        if (ffmpeg == null) {
          log('未找到 ffmpeg，跳过 MKV 转换（VOB 输出本身已经无损）');
        } else {
          log('ffmpeg: $ffmpeg');
          final made = await remuxAll(ffmpeg, result.outputDir, result.files);
          log('生成 ${made.length} 个 MKV');
        }
      }

      phase = Phase.done;
      progress = 1;
      statusText = result.verified ? '完成 · 无损校验通过' : '完成 · 校验未通过';
      notifyListeners();
    } catch (e, st) {
      _fail('$e');
      if (kDebugMode) {
        debugPrint('$st');
      }
    }
  }

  void _fail(String message) {
    phase = Phase.failed;
    error = message;
    statusText = '失败';
    log('错误：$message');
    notifyListeners();
  }

  static String _fmt(double seconds) {
    final s = seconds < 0 ? 0.0 : seconds;
    final h = (s / 3600).floor();
    final m = ((s % 3600) / 60).floor();
    final sec = s % 60;
    String two(int v) => v.toString().padLeft(2, '0');
    return '$h:${two(m)}:${sec.toStringAsFixed(3).padLeft(6, '0')}';
  }
}

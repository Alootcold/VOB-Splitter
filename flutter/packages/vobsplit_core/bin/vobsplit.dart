/// 命令行入口。
///
///   dart run bin/vobsplit.dart scan  VOB... [--json]
///   dart run bin/vobsplit.dart split  VOB... -o OUTDIR [选项]
///   dart run bin/vobsplit.dart verify OUTDIR --source VOB...
///
/// 选项：
///   --mode auto|duration|times|whole   切分方式，默认 auto（按 DVD 章节表）
///   --times  "0,218,489.28"             mode=times 的切点（秒，支持 hh:mm:ss）
///   --interval 600                      mode=duration 的间隔秒数
///   --min-chapter 2.0                   短于该值的章视为噪声并合并
///   --pts-drop 1.0                      判定 PTS 回落的阈值（秒）
///   --format vob|mkv|both               输出形式；mkv/both 需要 ffmpeg
///   --ffmpeg PATH                       指定 ffmpeg 可执行文件
///   --no-verify                         跳过 SHA-256 校验（不推荐）
///   --prefix chapter                    输出文件名前缀
library;

import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:vobsplit_core/vobsplit_core.dart';

const String _version = '1.0.0';

Future<void> main(List<String> args) async {
  try {
    exitCode = await run(args);
  } on FormatException catch (e) {
    stderr.writeln('错误: ${e.message}');
    exitCode = 2;
  } on ArgumentError catch (e) {
    stderr.writeln('错误: ${e.message}');
    exitCode = 2;
  } on FileSystemException catch (e) {
    stderr.writeln('错误: ${e.path ?? e.message}');
    exitCode = 2;
  }
}

/// CLI 主流程；返回进程退出码。
Future<int> run(List<String> args) async {
  if (args.isEmpty) {
    _printTopHelp();
    return 2;
  }
  final command = args.first;
  if (command == '--help' || command == '-h' || command == 'help') {
    _printTopHelp();
    return 0;
  }
  if (command == '--version') {
    stdout.writeln('vobsplit $_version');
    return 0;
  }
  final rest = args.sublist(1);
  switch (command) {
    case 'scan':
      return _cmdScan(rest);
    case 'split':
      return _cmdSplit(rest);
    case 'verify':
      return _cmdVerify(rest);
    default:
      stderr.writeln('未知命令: $command');
      _printTopHelp();
      return 2;
  }
}

// ---------------------------------------------------------------- 命令实现

Future<int> _cmdScan(List<String> args) async {
  final parsed = _parseArgs(args, valueOptions: _commonValueOptions,
      boolFlags: <String>{'json', 'include-menu'});
  if (parsed.flags.contains('help')) {
    _printScanHelp();
    return 0;
  }
  final files = _collectFiles(parsed.positional,
      includeMenu: parsed.flags.contains('include-menu'));
  if (files.isEmpty) {
    stderr.writeln('没有找到 VOB 文件');
    return 2;
  }
  final source = VobSource(files);
  final spec = _buildSpec(parsed.values);
  final (raps, chapters, stats) =
      await _scan(source, spec, quiet: parsed.flags.contains('json'));

  if (parsed.flags.contains('json')) {
    final payload = <String, dynamic>{
      'files': [for (final f in files) p.basename(f)],
      'total_size': source.totalSize,
      'stats': stats,
      'chapters': [
        for (final c in chapters)
          <String, dynamic>{
            'index': c.index,
            'start_offset': c.startOffset,
            'end_offset': c.endOffset,
            'bytes': c.size,
            'start_pts': c.startPts,
            'end_pts': c.endPts,
            'duration': c.duration,
            'rap_count': c.rapCount,
          }
      ],
    };
    stdout.writeln(const JsonEncoder.withIndent('  ').convert(payload));
  }
  return 0;
}

Future<int> _cmdSplit(List<String> args) async {
  final parsed = _parseArgs(args, valueOptions: _commonValueOptions,
      boolFlags: <String>{'no-verify', 'no-manifest', 'quiet', 'include-menu'});
  if (parsed.flags.contains('help')) {
    _printSplitHelp();
    return 0;
  }
  final output = parsed.values['output'];
  if (output == null || output.isEmpty) {
    stderr.writeln('错误: split 需要 -o/--output 输出目录');
    return 2;
  }
  final files = _collectFiles(parsed.positional,
      includeMenu: parsed.flags.contains('include-menu'));
  if (files.isEmpty) {
    stderr.writeln('没有找到 VOB 文件');
    return 2;
  }
  final source = VobSource(files);
  final spec = _buildSpec(parsed.values);
  final quiet = parsed.flags.contains('quiet');
  final (raps, chapters, stats) = await _scan(source, spec, quiet: quiet);

  if (chapters.length <= 1 && spec.mode == SplitMode.auto) {
    stdout.writeln('\n提示: 没检测到章节边界（该 VOB 可能只有一段，'
        '或时间戳未重置）。可以用 --interval 或 --times 指定切点。');
  }

  stdout.writeln('\n开始切分 -> $output');
  // 与 Python 版 CLI 保持一致：不打印逐章进度（库层的 onProgress 供 GUI 用）
  final result = await split(
    source,
    chapters,
    output,
    prefix: parsed.values['prefix'] ?? 'chapter',
    verify: !parsed.flags.contains('no-verify'),
    onProgress: (done, total, name) {
      stderr.write('\r  正在切分 $done / $total');
    },
    manifest: !parsed.flags.contains('no-manifest'),
  );

  final format = parsed.values['format'] ?? 'vob';
  if (format == 'mkv' || format == 'both') {
    final ffmpeg = findFfmpeg(parsed.values['ffmpeg']);
    if (ffmpeg == null) {
      stdout.writeln('\n未找到 ffmpeg，跳过 MKV 转换（VOB 输出已经是无损的）');
    } else {
      stdout.writeln('\n用 ffmpeg 转 MKV: $ffmpeg');
      final made = await remuxAll(ffmpeg, output, result.files);
      stdout.writeln('生成 ${made.length} 个 MKV');
    }
  }

  stdout.writeln();
  stdout.writeln(result.summary());
  if (result.manifestPath != null) {
    stdout.writeln('清单: ${result.manifestPath}');
  }
  final noVerify = parsed.flags.contains('no-verify');
  return (result.verified || noVerify) ? 0 : 1;
}

Future<int> _cmdVerify(List<String> args) async {
  final parsed = _parseArgs(args,
      valueOptions: <String>{'source'},
      boolFlags: <String>{'include-menu'});
  if (parsed.flags.contains('help')) {
    _printVerifyHelp();
    return 0;
  }
  if (parsed.positional.isEmpty) {
    stderr.writeln('错误: verify 需要切分结果所在目录');
    return 2;
  }
  final sourcePaths = parsed.values['source'] ?? '';
  if (sourcePaths.isEmpty) {
    stderr.writeln('错误: verify 需要 --source 原始 VOB 文件或目录');
    return 2;
  }
  final outDir = parsed.positional.first;
  final files = _collectFiles(
      sourcePaths.split(RegExp(r'[,;\s]+')).where((t) => t.isNotEmpty).toList(),
      includeMenu: parsed.flags.contains('include-menu'));
  final source = VobSource(files);

  final names = listVobOutputs(outDir);
  if (names.isEmpty) {
    stderr.writeln('目录里没有 .vob 文件');
    return 2;
  }
  final (digest, total) = await verifyOutputs(outDir, names);
  final src = await source.sha256();
  stdout.writeln('源流  ${source.totalSize} 字节  SHA-256 = $src');
  stdout.writeln('输出  $total 字节  SHA-256 = $digest');
  final ok = src == digest && total == source.totalSize;
  stdout.writeln('结果: ${ok ? '逐字节完全一致 —— 100% 无损' : '不一致'}');
  return ok ? 0 : 1;
}

// ---------------------------------------------------------------- 公共逻辑

Future<(List<Rap>, List<Chapter>, Map<String, int>)> _scan(
    VobSource source, ChapterSpec spec,
    {bool quiet = false}) async {
  if (!quiet) {
    stdout.writeln('扫描: ${source.paths.map(p.basename).join(', ')}');
    stdout.writeln('总大小: ${source.totalSize} 字节 '
        '(${(source.totalSize / 1073741824.0).toStringAsFixed(2)} GiB)');
  }
  final index = await buildIndex(source, onProgress: (frac) {
    stderr.write('\r  正在扫描码流… ${(frac * 100).toStringAsFixed(0)}%');
  });
  stderr.write('\n');
  final chapters = detectChapters(index.raps, source.totalSize, spec);
  if (!quiet) {
    stdout.writeln('pack=${index.stats['packs']}  '
        '非法pack=${index.stats['invalid_packs']}  '
        '视频PES=${index.stats['video_pes']}  '
        '随机访问点=${index.stats['raps']}');
    stdout.writeln('检测到 ${chapters.length} 章\n');
    stdout.writeln('  ${_pad('章', 4)} ${_pad('起始', 14)} ${_pad('结束', 14)} '
        '${_pad('时长', 14)} ${_padRight('字节', 12)} ${_padRight('GOP', 8)}');
    for (final ch in chapters) {
      stdout.writeln('  ${_pad('${ch.index + 1}', 4)} '
          '${_pad(formatTimestamp(ch.startPts), 14)} '
          '${_pad(formatTimestamp(ch.endPts), 14)} '
          '${_pad(formatTimestamp(ch.duration), 14)} '
          '${_padRight('${ch.size}', 12)} '
          '${_padRight('${ch.rapCount}', 8)}');
    }
  }
  return (index.raps, chapters, index.stats);
}

ChapterSpec _buildSpec(Map<String, String> values) {
  final mode = values['mode'] ?? 'auto';
  final minChapter = double.parse(values['min-chapter'] ?? '2.0');
  switch (mode) {
    case 'duration':
      final interval = double.parse(values['interval'] ?? '600.0');
      return ChapterSpec.duration(interval, minChapter: minChapter);
    case 'times':
      final times = parseTimeList(values['times'] ?? '');
      return ChapterSpec.times(times, minChapter: minChapter);
    case 'whole':
      return const ChapterSpec.whole();
    case 'auto':
      final ptsDrop = double.parse(values['pts-drop'] ?? '1.0');
      return ChapterSpec.auto(ptsDrop: ptsDrop, minChapter: minChapter);
    default:
      throw FormatException('未知模式: $mode');
  }
}

/// 展开目录参数：给目录就把里面所有 .vob 按 DVD 顺序排好。
///
/// DVD 会额外放一个 VTS_xx_0.VOB 作为盘上菜单（标题 0），它不属于正片内容，
/// 展开目录时默认跳过；用 --include-menu 可以带上。
List<String> _collectFiles(List<String> paths, {bool includeMenu = false}) {
  final out = <String>[];
  for (final path in paths) {
    final dir = Directory(path);
    if (dir.existsSync()) {
      final vobs = dir
          .listSync()
          .whereType<File>()
          .map((f) => p.basename(f.path))
          .where((name) => name.toLowerCase().endsWith('.vob'))
          .toList();
      // 稳定排序（Python 的 sorted 是稳定的，Dart 的 List.sort 不是）
      final indexed = [
        for (var i = 0; i < vobs.length; i++) (i, vobs[i]),
      ];
      indexed.sort((a, b) {
        final ka = _vobSortKey(a.$2);
        final kb = _vobSortKey(b.$2);
        if (ka.$1 != kb.$1) {
          return ka.$1.compareTo(kb.$1);
        }
        if (ka.$2 != kb.$2) {
          return ka.$2.compareTo(kb.$2);
        }
        return a.$1.compareTo(b.$1);
      });
      final sorted = [for (final item in indexed) item.$2];
      if (!includeMenu) {
        final skipped = sorted.where(_isMenuVob).toList();
        final kept = sorted.where((v) => !_isMenuVob(v)).toList();
        if (skipped.isNotEmpty) {
          stdout.writeln('跳过菜单 VOB: ${skipped.join(', ')}'
              '（用 --include-menu 可包含）');
        }
        out.addAll([for (final v in kept) p.join(path, v)]);
      } else {
        out.addAll([for (final v in sorted) p.join(path, v)]);
      }
    } else {
      out.add(path);
    }
  }
  return out;
}

/// VTS_01_0.VOB / VTS_03_0.VOB 是盘上菜单（标题 0）。
bool _isMenuVob(String name) {
  final base = p.basenameWithoutExtension(name);
  final parts = base.split('_');
  if (parts.length < 3) {
    return false;
  }
  final n = int.tryParse(parts.last.trim());
  if (n == null) {
    return false;
  }
  return n == 0;
}

/// VTS_01_1.VOB < VTS_01_2.VOB < VTS_01_10.VOB（按数字排序）。
(String, int) _vobSortKey(String name) {
  final base = p.basenameWithoutExtension(name);
  final parts = base.split('_');
  final n = int.tryParse(parts.last.trim());
  if (n == null) {
    return (base, 0);
  }
  return (parts.first, n);
}

String _pad(String text, int width) => text.padRight(width);

String _padRight(String text, int width) => text.padLeft(width);

// ---------------------------------------------------------------- 参数解析

const Set<String> _commonValueOptions = <String>{
  'mode',
  'times',
  'interval',
  'min-chapter',
  'pts-drop',
  'prefix',
  'format',
  'ffmpeg',
  'output',
};

class _ParsedArgs {
  final List<String> positional = <String>[];
  final Map<String, String> values = <String, String>{};
  final Set<String> flags = <String>{};

  bool has(String flag) => flags.contains(flag);
}

/// 手写的极简参数解析（只允许 crypto/path 依赖，不能引入 args 包）。
_ParsedArgs _parseArgs(
  List<String> args, {
  required Set<String> valueOptions,
  required Set<String> boolFlags,
}) {
  final parsed = _ParsedArgs();
  var onlyPositional = false;
  var i = 0;
  while (i < args.length) {
    final arg = args[i];
    if (!onlyPositional && arg == '--') {
      onlyPositional = true;
      i++;
      continue;
    }
    if (!onlyPositional && arg.startsWith('--')) {
      var name = arg.substring(2);
      String? inline;
      final eq = name.indexOf('=');
      if (eq >= 0) {
        inline = name.substring(eq + 1);
        name = name.substring(0, eq);
      }
      if (name == 'help') {
        parsed.flags.add('help');
        i++;
        continue;
      }
      if (boolFlags.contains(name)) {
        parsed.flags.add(name);
        i++;
        continue;
      }
      if (valueOptions.contains(name)) {
        if (inline != null) {
          parsed.values[name] = inline;
          i++;
        } else {
          if (i + 1 >= args.length) {
            throw FormatException('选项 --$name 缺少参数');
          }
          parsed.values[name] = args[i + 1];
          i += 2;
        }
        continue;
      }
      throw FormatException('未知选项: --$name');
    }
    if (!onlyPositional && arg.startsWith('-') && arg.length > 1) {
      final name = arg.substring(1);
      if (name == 'h') {
        parsed.flags.add('help');
        i++;
        continue;
      }
      if (name == 'q') {
        parsed.flags.add('quiet');
        i++;
        continue;
      }
      if (name == 'o') {
        if (i + 1 >= args.length) {
          throw FormatException('选项 -o 缺少参数');
        }
        parsed.values['output'] = args[i + 1];
        i += 2;
        continue;
      }
      throw FormatException('未知选项: $arg');
    }
    parsed.positional.add(arg);
    i++;
  }
  return parsed;
}

// ---------------------------------------------------------------- 帮助文本

void _printTopHelp() {
  stdout.writeln('''
vobsplit $_version —— DVD VOB 无损分割工具（纯 Dart 版）

用法:
  vobsplit scan   VOB... [选项]
  vobsplit split  VOB... -o OUTDIR [选项]
  vobsplit verify OUTDIR --source VOB...

子命令:
  scan    扫描并列出检测到的章节
  split   按章节切分
  verify  校验已有切分结果

通用选项:
  --mode auto|duration|times|whole   切分方式，默认 auto（按 DVD 章节表）
  --times  "0,218,489.28"             mode=times 的切点（秒，支持 hh:mm:ss）
  --interval 600                      mode=duration 的间隔秒数
  --min-chapter 2.0                   短于该值的章视为噪声并合并
  --pts-drop 1.0                      判定 PTS 回落的阈值（秒）
  --include-menu                      展开目录时把 VTS_xx_0.VOB 菜单文件也算进去
  -h, --help                          显示帮助

split 专有:
  -o, --output OUTDIR                 输出目录（必填）
  --prefix chapter                    输出文件名前缀，默认 chapter
  --format vob|mkv|both               输出形式，默认 vob；mkv/both 需要 ffmpeg
  --ffmpeg PATH                       指定 ffmpeg 可执行文件
  --no-verify                         跳过 SHA-256 校验（不推荐）
  --no-manifest                       不写 JSON 清单
  -q, --quiet                         安静模式''');
}

void _printScanHelp() {
  stdout.writeln('''
用法: vobsplit scan VOB... [选项]

扫描并列出检测到的章节。

选项:
  --json                              输出 JSON
  --mode auto|duration|times|whole   切分方式，默认 auto
  --times "0,218,489.28"              mode=times 的切点
  --interval 600                      mode=duration 的间隔秒数
  --min-chapter 2.0                   短于该秒数的章视为噪声并合并
  --pts-drop 1.0                      判定 PTS 回落的阈值（秒）
  --include-menu                      展开目录时把 VTS_xx_0.VOB 菜单文件也算进去
  -h, --help                          显示帮助''');
}

void _printSplitHelp() {
  stdout.writeln('''
用法: vobsplit split VOB... -o OUTDIR [选项]

按章节切分，输出逐字节无损。

选项:
  -o, --output OUTDIR                 输出目录（必填）
  --prefix chapter                    输出文件名前缀，默认 chapter
  --format vob|mkv|both               输出形式，默认 vob；mkv/both 需要 ffmpeg
  --ffmpeg PATH                       指定 ffmpeg 可执行文件
  --no-verify                         跳过 SHA-256 校验
  --no-manifest                       不写 JSON 清单
  --mode auto|duration|times|whole   切分方式，默认 auto
  --times "0,218,489.28"              mode=times 的切点
  --interval 600                      mode=duration 的间隔秒数
  --min-chapter 2.0                   短于该秒数的章视为噪声并合并
  --pts-drop 1.0                      判定 PTS 回落的阈值（秒）
  --include-menu                      展开目录时把 VTS_xx_0.VOB 菜单文件也算进去
  -q, --quiet                         安静模式
  -h, --help                          显示帮助''');
}

void _printVerifyHelp() {
  stdout.writeln('''
用法: vobsplit verify OUTDIR --source VOB...

校验已有切分结果：用 SHA-256 证明「各输出拼接 == 源流」。

选项:
  --source VOB...                     原始 VOB 文件或目录（必填）
  --include-menu                      展开目录时把 VTS_xx_0.VOB 菜单文件也算进去
  -h, --help                          显示帮助''');
}

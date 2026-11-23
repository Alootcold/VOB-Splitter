/// 切分与校验。
///
/// 切分是**字节级切片**：每个输出文件就是输入码流的一段连续字节，
/// 原样复制，不重新编码、不重新封装、不改写任何字节。
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:path/path.dart' as p;

import 'chapters.dart';
import 'ps.dart';

/// 单次复制的块大小（4 MiB）。
const int _copyChunk = 1 << 22;

/// 一次切分的结果与证据。
class SplitResult {
  final String outputDir;

  /// 输出的文件名（相对 [outputDir]），按章节顺序。
  final List<String> files;

  /// 每章的元信息（与写进 manifest 的内容一致）。
  final List<Map<String, dynamic>> chapters;

  final int sourceBytes;
  final int outputBytes;
  final String sourceSha256;
  final String outputSha256;

  /// 是否已通过 SHA-256 校验（各章拼接 == 源流）。
  final bool verified;

  /// JSON 清单路径；未写清单时为 null。
  final String? manifestPath;

  const SplitResult({
    required this.outputDir,
    this.files = const <String>[],
    this.chapters = const <Map<String, dynamic>>[],
    this.sourceBytes = 0,
    this.outputBytes = 0,
    this.sourceSha256 = '',
    this.outputSha256 = '',
    this.verified = false,
    this.manifestPath,
  });

  /// 人类可读的结果摘要。
  String summary() {
    final lines = <String>[
      '输出目录: $outputDir',
      '章节数  : ${files.length}',
      '源字节  : $sourceBytes',
      '出字节  : $outputBytes',
      '源SHA256: $sourceSha256',
      '出SHA256: $outputSha256',
      '无损校验: ${verified ? '通过（逐字节一致）' : '未通过'}',
    ];
    return lines.join('\n');
  }
}

/// 增量 SHA-256 累加器。
///
/// package:crypto 3.0.x 的 `Hash` 继承自 `Converter`，没有 `add()`，
/// 所以这里用 `startChunkedConversion` 接一个自己的 sink，
/// 边复制边算哈希 —— 对光盘来说能省掉整整一趟重读。
class Sha256Accumulator {
  final _DigestSink _sink = _DigestSink();
  late final ByteConversionSink _input = crypto.sha256.startChunkedConversion(_sink);

  void add(List<int> data) => _input.add(data);

  /// 收尾并返回十六进制摘要。
  String get hex {
    _input.close();
    return _sink.value?.toString() ?? '';
  }
}

class _DigestSink implements Sink<crypto.Digest> {
  crypto.Digest? value;

  @override
  void add(crypto.Digest data) {
    value = data;
  }

  @override
  void close() {}
}

/// 把 [start, end) 原样复制到 [destPath]，返回写入字节数。
Future<int> _copyRange(
    VobSource source, int start, int end, String destPath,
    [Sha256Accumulator? digest]) async {
  var written = 0;
  final out = File(destPath).openSync(mode: FileMode.write);
  try {
    var pos = start;
    while (pos < end) {
      final remain = end - pos;
      final take = remain < _copyChunk ? remain : _copyChunk;
      final data = await source.readAt(pos, take);
      if (data.isEmpty) {
        break;
      }
      await out.writeFrom(data);
      digest?.add(data);
      written += data.length;
      pos += data.length;
    }
  } finally {
    out.closeSync();
  }
  return written;
}

/// 把输出文件按顺序读回来算 SHA-256，用于和源流比对。
///
/// 返回 (SHA-256 十六进制, 总字节数)。
Future<(String, int)> verifyOutputs(String outputDir, List<String> files) async {
  var total = 0;
  Stream<List<int>> source() async* {
    for (final name in files) {
      await for (final data in File(p.join(outputDir, name)).openRead()) {
        total += data.length;
        yield data;
      }
    }
  }

  final digest = await crypto.sha256.bind(source()).first;
  return (digest.toString(), total);
}

/// 按章节切分并写出文件。
///
/// [verify] 为 true 时会用 SHA-256 证明「各章拼接 == 源流」。
Future<SplitResult> split(
  VobSource source,
  List<Chapter> chapters,
  String outputDir, {
  String prefix = 'chapter',
  bool verify = true,
  bool manifest = true,
  void Function(int done, int total, String name)? onProgress,
}) async {
  await Directory(outputDir).create(recursive: true);

  final files = <String>[];
  final chapterMeta = <Map<String, dynamic>>[];
  final srcDigest = Sha256Accumulator();

  for (final ch in chapters) {
    final name = '${prefix}_${(ch.index + 1).toString().padLeft(2, '0')}.vob';
    final path = p.join(outputDir, name);
    await _copyRange(source, ch.startOffset, ch.endOffset, path, srcDigest);
    files.add(name);
    chapterMeta.add(<String, dynamic>{
      'index': ch.index,
      'file': name,
      'start_offset': ch.startOffset,
      'end_offset': ch.endOffset,
      'bytes': ch.size,
      'start_pts': ch.startPts,
      'end_pts': ch.endPts,
      'duration': ch.duration,
      'rap_count': ch.rapCount,
    });
    if (onProgress != null) {
      onProgress(ch.index + 1, chapters.length, name);
    }
  }

  var sourceSha = '';
  var outputSha = '';
  var verified = false;
  var outputBytes = 0;
  for (final meta in chapterMeta) {
    outputBytes += meta['bytes'] as int;
  }

  if (verify) {
    // 章节完整覆盖整条流时，切分过程中顺带算出的源流哈希就可以直接用；
    // 否则老老实实再读一遍源（宁可慢，也不能算错）。
    final covered = chapters.fold<int>(0, (sum, ch) => sum + ch.size);
    final complete = chapters.isNotEmpty &&
        chapters.first.startOffset == 0 &&
        covered == source.totalSize;
    sourceSha = complete ? srcDigest.hex : await source.sha256();
    final result = await verifyOutputs(outputDir, files);
    outputSha = result.$1;
    final outTotal = result.$2;
    verified = sourceSha == outputSha && outTotal == source.totalSize;
  }

  String? manifestPath;
  if (manifest) {
    final path = p.join(outputDir, 'vobsplit-manifest.json');
    final payload = <String, dynamic>{
      'tool': 'vobsplit',
      'source_files': [for (final path in source.paths) p.basename(path)],
      'source_bytes': source.totalSize,
      'source_sha256': sourceSha,
      'output_bytes': outputBytes,
      'output_sha256': outputSha,
      'verified': verified,
      'chapters': chapterMeta,
    };
    await File(path).writeAsString(
      const JsonEncoder.withIndent('  ').convert(payload),
      encoding: utf8,
      flush: true,
    );
    manifestPath = path;
  }

  return SplitResult(
    outputDir: outputDir,
    files: files,
    chapters: chapterMeta,
    sourceBytes: source.totalSize,
    outputBytes: outputBytes,
    sourceSha256: sourceSha,
    outputSha256: outputSha,
    verified: verified,
    manifestPath: manifestPath,
  );
}

/// 读取结果目录里的 .vob 文件名（按名称排序）。
List<String> listVobOutputs(String outputDir) {
  final dir = Directory(outputDir);
  if (!dir.existsSync()) {
    return const <String>[];
  }
  // 优先按 manifest 里记录的章节文件列表，避免把上一次切分的残留文件算进去
  final manifestFile = File(p.join(outputDir, 'vobsplit-manifest.json'));
  if (manifestFile.existsSync()) {
    try {
      final data = jsonDecode(manifestFile.readAsStringSync());
      final chapters = data is Map ? data['chapters'] : null;
      if (chapters is List) {
        final names = <String>[
          for (final c in chapters)
            if (c is Map && c['file'] is String) c['file'] as String,
        ];
        if (names.isNotEmpty) {
          return names;
        }
      }
    } catch (_) {
      // manifest 坏了就退回按目录扫
    }
  }
  final names = dir
      .listSync()
      .whereType<File>()
      .map((f) => p.basename(f.path))
      .where((name) => name.toLowerCase().endsWith('.vob'))
      .toList()
    ..sort();
  return names;
}

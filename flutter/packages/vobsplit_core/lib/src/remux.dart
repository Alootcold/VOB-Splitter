/// 可选的 MKV 重封装（调用 ffmpeg，零重编码）。
///
/// VOB 切出来的每一章本身已经是无损的；转 MKV 只是换容器，方便播放。
/// 这个步骤用 ffmpeg 的 stream copy，码流载荷不会被改动。
/// ffmpeg 不存在时会安静跳过 —— 纯 VOB 分割不依赖 ffmpeg。
library;

import 'dart:io';

import 'package:path/path.dart' as p;

/// 找到 ffmpeg：优先用给定路径，其次 PATH，再试几个常见安装位置。
String? findFfmpeg([String? explicit]) {
  if (explicit != null && explicit.isNotEmpty) {
    return File(explicit).existsSync() ? explicit : null;
  }

  // PATH 里找（Windows 上同时看 ffmpeg.exe 与 ffmpeg）
  final pathEnv = Platform.environment['PATH'] ?? '';
  final sep = Platform.isWindows ? ';' : ':';
  final exeNames = Platform.isWindows ? <String>['ffmpeg.exe', 'ffmpeg'] : <String>['ffmpeg'];
  for (final dir in pathEnv.split(sep)) {
    if (dir.isEmpty) {
      continue;
    }
    for (final exe in exeNames) {
      final candidate = p.join(dir, exe);
      if (File(candidate).existsSync()) {
        return candidate;
      }
    }
  }

  const candidates = <String>[
    r'D:\Program Files\ffmpeg\bin\ffmpeg.exe',
    r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
    '/usr/local/bin/ffmpeg',
    '/opt/homebrew/bin/ffmpeg',
    '/usr/bin/ffmpeg',
  ];
  for (final candidate in candidates) {
    if (File(candidate).existsSync()) {
      return candidate;
    }
  }
  return null;
}

/// 把一个 VOB 重封装成 MKV。返回是否成功。
///
/// -fflags +genpts：切片起点的音频 PES 本身不带时间戳，需要补齐，
/// 否则 Matroska 封装器会报 "Can't write packet with unknown timestamp"。
Future<bool> remuxToMkv(String ffmpeg, String src, String dst, {String? title}) async {
  final cmd = <String>[
    ffmpeg,
    '-hide_banner',
    '-v',
    'error',
    '-nostdin',
    '-y',
    '-fflags',
    '+genpts',
    '-i',
    src,
    '-map',
    '0:v',
    '-map',
    '0:a?',
    '-c',
    'copy',
  ];
  if (title != null && title.isNotEmpty) {
    cmd.addAll(<String>['-metadata', 'title=$title']);
  }
  cmd.addAll(<String>['-f', 'matroska', dst]);

  try {
    final result = await Process.run(ffmpeg, cmd);
    return result.exitCode == 0;
  } on ProcessException {
    // ffmpeg 不可用等情况一律当作失败，调用方会安静跳过
    return false;
  }
}

/// 批量把输出目录里的 .vob 转成同名 .mkv，返回成功生成的列表。
Future<List<String>> remuxAll(
    String ffmpeg, String outputDir, List<String> files) async {
  final made = <String>[];
  for (final name in files) {
    if (!name.toLowerCase().endsWith('.vob')) {
      continue;
    }
    final src = p.join(outputDir, name);
    final stem = name.substring(0, name.length - 4);
    final dst = p.join(outputDir, '$stem.mkv');
    final title = stem.replaceAll('_', ' ');
    if (await remuxToMkv(ffmpeg, src, dst, title: title)) {
      made.add(p.basename(dst));
    }
  }
  return made;
}

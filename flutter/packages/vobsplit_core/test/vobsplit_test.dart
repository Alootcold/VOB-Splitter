/// vobsplit 单元测试（package:test）。
///
///   cd flutter/packages/vobsplit_core && dart test
///
/// 本文件是 python/tests/test_vobsplit.py 的逐个移植：测试数量与断言语义保持一致。
library;

import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:test/test.dart';
import 'package:vobsplit_core/vobsplit_core.dart';

import 'synth.dart' as synth;

void main() {
  group('时间戳', () {
    test('往返', () {
      for (final value in <int>[0, 1, 2700, 90000, 123456789, 0x1FFFFFFFF]) {
        final raw = synth.encodeTimestamp(value);
        final decoded = decodeTimestamp(raw, 0);
        expect(decoded, isNotNull);
        expect(decoded!, closeTo(value / 90000.0, 1e-6));
      }
    });

    test('拒绝垃圾字节', () {
      expect(
          decodeTimestamp(
              Uint8List.fromList(<int>[0x00, 0x00, 0x00, 0x00, 0x00]), 0),
          isNull);
      expect(
          decodeTimestamp(
              Uint8List.fromList(<int>[0xFF, 0xFF, 0xFF, 0xFF, 0xFF]), 0),
          isNull);
    });
  });

  group('时间点解析', () {
    test('各种写法', () {
      expect(parseTimeSpec('90'), closeTo(90.0, 1e-9));
      expect(parseTimeSpec('1:30'), closeTo(90.0, 1e-9));
      expect(parseTimeSpec('00:01:30'), closeTo(90.0, 1e-9));
      expect(parseTimeSpec('00:01:30.5'), closeTo(90.5, 1e-9));
      expect(parseTimeSpec('1h2m3s'), closeTo(3723.0, 1e-9));
      expect(parseTimeList('0, 218, 00:08:09.28'), <double>[0.0, 218.0, 489.28]);
    });
  });

  group('章节检测', () {
    late Directory tmp;
    late String path;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('vobsplit-test-');
      path = '${tmp.path}${Platform.pathSeparator}VTS_01_1.VOB';
      synth.writeVob(path, <double>[6.0, 4.0, 8.0]);
    });

    tearDown(() {
      if (tmp.existsSync()) {
        tmp.deleteSync(recursive: true);
      }
    });

    Future<(List<Chapter>, List<Rap>, Map<String, int>)> chaptersOf(
        String file) async {
      final source = VobSource(<String>[file]);
      final index = await buildIndex(source);
      return (
        detectChapters(index.raps, source.totalSize, const ChapterSpec.auto()),
        index.raps,
        index.stats
      );
    }

    test('检测出三章', () async {
      final (chapters, raps, stats) = await chaptersOf(path);
      expect(chapters.length, 3);
      expect(stats['raps'], greaterThan(10));
      expect(stats['invalid_packs'], 0);
      expect(raps, isNotEmpty);
    });

    test('章节边界按 pack 对齐', () async {
      final (chapters, _, _) = await chaptersOf(path);
      for (final ch in chapters) {
        expect(ch.startOffset % 2048, 0);
        expect(ch.endOffset % 2048, 0);
      }
    });

    test('章节覆盖整条流', () async {
      final (chapters, _, _) = await chaptersOf(path);
      expect(chapters.first.startOffset, 0);
      expect(chapters.last.endOffset, File(path).lengthSync());
    });

    test('首章从字节 0 开始（真实 DVD 的首个 pack 是导航包）', () async {
      // 真实 DVD 的第一个 pack 是导航包（stream id 0xBB），不是随机访问点。
      // 首章必须仍然从字节 0 开始 —— 否则开头那段会被丢掉，
      // 「各章拼接 == 源流」的哈希校验就通不过。
      final (chapters, _, _) = await chaptersOf(path);
      expect(chapters.first.startOffset, 0);
      expect(chapters.first.endOffset % 2048, 0);
    });

    test('扫描期间事件循环不能被饿死（否则界面会冻住）', () async {
    // 读光盘时如果用同步读盘 + await for，await 只是微任务，
    // 事件队列整个扫描期间拿不到时间片 ⇒ 界面不重绘 ⇒ Windows 判定「未响应」。
    // 用定时器探针验证：扫描期间定时器必须能跑起来。
    //
    // 夹具要够大，扫描才够长、才有时间让定时器被触发（约 12MB ≈ 6000 个 pack）。
    final big = '${tmp.path}${Platform.pathSeparator}big.vob';
    synth.writeVob(big, <double>[3000.0]);

    var ticks = 0;
    final timer = Timer.periodic(const Duration(milliseconds: 5), (_) => ticks++);
    final source = VobSource(<String>[big]);
    await buildIndex(source);
    timer.cancel();
    expect(ticks, greaterThan(0),
        reason: '扫描期间事件循环被饿死，界面会冻住（同步读盘？）');
  });

  test('扫描期间必须回报进度', () async {
    // 读光盘很慢，没有进度用户会以为卡死
    final source = VobSource(<String>[path]);
    final seen = <double>[];
    await buildIndex(source, onProgress: seen.add);
    expect(seen, isNotEmpty);
    expect(seen.every((v) => v >= 0.0 && v <= 1.0), isTrue);
    expect(seen.last, greaterThan(0.0));
  });

  test('单个 program 只有一章', () async {
      final single = '${tmp.path}${Platform.pathSeparator}single.vob';
      synth.writeVob(single, <double>[10.0]);
      final (chapters, _, _) = await chaptersOf(single);
      expect(chapters.length, 1);
    });

    test('过短的章并入上一章', () async {
      // 太短的章视为噪声，并入上一章。
      final short = '${tmp.path}${Platform.pathSeparator}short.vob';
      synth.writeVob(short, <double>[6.0, 1.0, 6.0]);
      final (chapters, _, _) = await chaptersOf(short);
      expect(chapters.length, 2);
    });

    test('全局时间轴单调递增', () async {
      final (chapters, _, _) = await chaptersOf(path);
      for (var i = 1; i < chapters.length; i++) {
        expect(chapters[i].globalStart, greaterThan(chapters[i - 1].globalStart));
        expect(chapters[i].globalEnd, greaterThan(chapters[i].globalStart));
      }
    });
  });

  group('切分', () {
    late Directory tmp;
    late String path;
    late String out;

    setUp(() {
      tmp = Directory.systemTemp.createTempSync('vobsplit-test-');
      path = '${tmp.path}${Platform.pathSeparator}VTS_01_1.VOB';
      synth.writeVob(path, <double>[6.0, 4.0, 8.0]);
      out = '${tmp.path}${Platform.pathSeparator}out';
    });

    tearDown(() {
      if (tmp.existsSync()) {
        tmp.deleteSync(recursive: true);
      }
    });

    Future<SplitResult> runSplit({ChapterSpec? spec}) async {
      final source = VobSource(<String>[path]);
      final index = await buildIndex(source);
      final chapters = detectChapters(
          index.raps, source.totalSize, spec ?? const ChapterSpec.auto());
      return split(source, chapters, out);
    }

    test('字节级精确', () async {
      final result = await runSplit();
      expect(result.verified, isTrue);
      expect(result.sourceBytes, result.outputBytes);
      expect(result.sourceSha256, result.outputSha256);
    });

    test('拼接等于源', () async {
      await runSplit();
      final original = File(path).readAsBytesSync();
      final pieces = <int>[];
      for (final name in resultNames(out)) {
        pieces.addAll(
            File('${out}${Platform.pathSeparator}$name').readAsBytesSync());
      }
      expect(crypto.sha256.convert(pieces).toString(),
          crypto.sha256.convert(original).toString());
      expect(pieces, original);
    });

    test('每个输出都以 pack header 开头', () async {
      await runSplit();
      for (final name in resultNames(out)) {
        final handle = File('${out}${Platform.pathSeparator}$name').openSync();
        final head = handle.readSync(4);
        handle.closeSync();
        expect(head, <int>[0x00, 0x00, 0x01, 0xBA]);
      }
    });

    test('写出 manifest', () async {
      final result = await runSplit();
      expect(result.manifestPath, isNotNull);
      expect(File(result.manifestPath!).existsSync(), isTrue);
      expect(result.chapters.length, 3);
    });

    test('多文件源', () async {
      // DVD 会把标题切成多个 VOB，必须当作一条连续流处理。
      final multi = '${tmp.path}${Platform.pathSeparator}multi';
      Directory(multi).createSync(recursive: true);
      final paths = synth.writeVob(
          '$multi${Platform.pathSeparator}VTS_02_1.VOB',
          <double>[6.0, 4.0, 8.0],
          splitAt: 3);
      final source = VobSource(paths);
      final index = await buildIndex(source);
      final chapters =
          detectChapters(index.raps, source.totalSize, const ChapterSpec.auto());
      final out2 = '${tmp.path}${Platform.pathSeparator}out2';
      final result = await split(source, chapters, out2);
      expect(result.verified, isTrue);
      expect(chapters.length, 3);
    });

    test('duration 模式', () async {
      final source = VobSource(<String>[path]);
      final index = await buildIndex(source);
      final spec = ChapterSpec.duration(2.0, minChapter: 0.0);
      final chapters = detectChapters(index.raps, source.totalSize, spec);
      expect(chapters.length, greaterThan(1));
    });

    test('times 模式', () async {
      final source = VobSource(<String>[path]);
      final index = await buildIndex(source);
      final spec = ChapterSpec.times(<double>[2.0], minChapter: 0.0);
      final chapters = detectChapters(index.raps, source.totalSize, spec);
      expect(chapters.length, 2);
    });
  });
}

/// 输出目录里的 .vob 文件名（按名称排序）。
List<String> resultNames(String outDir) {
  final dir = Directory(outDir);
  if (!dir.existsSync()) {
    return const <String>[];
  }
  final names = dir
      .listSync()
      .whereType<File>()
      .map((f) => f.path.split(Platform.pathSeparator).last)
      .where((name) => name.endsWith('.vob'))
      .toList()
    ..sort();
  return names;
}

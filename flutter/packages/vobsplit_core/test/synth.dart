/// 合成 MPEG-2 PS (VOB) 测试夹具。
///
/// 不依赖真实光盘：按 MPEG-2 规范生成 pack header / 视频 PES / 序列头，
/// 可以精确控制「几章、每章多少 GOP、PTS 是否重置」，用来验证
/// 章节检测与字节级无损切分。
///
/// 本文件是 python/tests/synth.py 的逐行移植：生成的字节与 Python 版**完全一致**，
/// 因此两套实现的测试夹具可以互相校验。
library;

import 'dart:io';
import 'dart:typed_data';

/// pack 长度。
const int packSize = 2048;

/// GOP 间隔（秒，12 帧 @25fps，DVD 常见值）。
const double gopInterval = 0.48;

/// 真实 DVD 上首帧 GOP 的 PTS 量级。
const double firstGopPts = 0.367;

/// 按位写出的比特流。
class BitWriter {
  final List<int> _bits = <int>[];

  /// 写出 [value] 的低 [count] 位（高位在前）。
  void write(int value, int count) {
    for (var i = count - 1; i >= 0; i--) {
      _bits.add((value >> i) & 1);
    }
  }

  /// 补零到字节边界后打包。
  Uint8List toBytes() {
    final bits = List<int>.from(_bits);
    while (bits.length % 8 != 0) {
      bits.add(0);
    }
    final out = Uint8List(bits.length ~/ 8);
    for (var i = 0; i < bits.length; i += 8) {
      var byte = 0;
      for (var b = 0; b < 8; b++) {
        byte = (byte << 1) | bits[i + b];
      }
      out[i ~/ 8] = byte;
    }
    return out;
  }
}

/// 把 90kHz 时间戳编码成 5 字节 PTS/DTS 字段。
///
/// byte0 = prefix | PTS[32..30] | marker
/// byte1-2 = PTS[29..15] | marker
/// byte3-4 = PTS[14..0] | marker
Uint8List encodeTimestamp(int pts90k, {int prefix = 0x30}) {
  final hi = (pts90k >> 30) & 0x07;
  final mid = (pts90k >> 15) & 0x7FFF;
  final lo = pts90k & 0x7FFF;
  return Uint8List.fromList(<int>[
    prefix | (hi << 1) | 1,
    (mid >> 7) & 0xFF,
    ((mid & 0x7F) << 1) | 1,
    (lo >> 7) & 0xFF,
    ((lo & 0x7F) << 1) | 1,
  ]);
}

/// 生成 14 字节 MPEG-2 pack header。
Uint8List packHeader(int scr90k, {int muxRate = 0x3FFFF}) {
  final w = BitWriter();
  w.write((scr90k >> 30) & 0x07, 3);
  w.write(1, 1);
  w.write((scr90k >> 15) & 0x7FFF, 15);
  w.write(1, 1);
  w.write(scr90k & 0x7FFF, 15);
  w.write(1, 1);
  w.write(0, 9); // SCR_ext
  w.write(1, 1);
  w.write(muxRate, 22);
  w.write(1, 1);
  w.write(1, 1);
  w.write(0x1F, 5); // reserved
  w.write(0, 3); // pack_stuffing_length
  w.write(0, 2); // 补齐到 14 字节
  final body = w.toBytes();
  return Uint8List.fromList(<int>[0x00, 0x00, 0x01, 0xBA, ...body]);
}

/// 720x576 / 25fps 的序列头。
Uint8List sequenceHeader() {
  const h = 0x2D02; // 720 x 576
  const v = 0x0240; // 576
  const ratio = 0x23; // 16:9, 25fps
  return Uint8List.fromList(<int>[
    0x00,
    0x00,
    0x01,
    0xB3,
    (h >> 4) & 0xFF,
    ((h & 0x0F) << 4) | ((v >> 8) & 0x0F),
    v & 0xFF,
    ratio,
  ]);
}

/// GOP 头。
Uint8List gopHeader() {
  return Uint8List.fromList(<int>[0x00, 0x00, 0x01, 0xB8, 0x00, 0x08, 0x45, 0x40]);
}

/// 图像头（起始码是 00 00 01 00，不是 0xB2）。
Uint8List pictureHeader({bool isIFrame = true}) {
  final codingType = isIFrame ? 1 : 2;
  const temporal = 0x008C;
  final word = (temporal << 6) | (codingType << 3);
  return Uint8List.fromList(<int>[
    0x00,
    0x00,
    0x01,
    0x00,
    (word >> 8) & 0xFF,
    word & 0xFF,
    0x5A,
    0x70,
  ]);
}

/// 视频 PES（带 PTS 与 DTS），[length] = PES 包总长（含头部）。
Uint8List videoPes(int pts90k, int dts90k, Uint8List es, int length) {
  final headerData = <int>[
    ...encodeTimestamp(pts90k, prefix: 0x30),
    ...encodeTimestamp(dts90k, prefix: 0x10),
  ];
  return Uint8List.fromList(<int>[
    0x00,
    0x00,
    0x01,
    0xE0,
    (length >> 8) & 0xFF,
    length & 0xFF,
    0x81,
    0xC0,
    headerData.length,
    ...headerData,
    ...es,
  ]);
}

/// 一个 pack：pack header + 一个视频 PES（PES 负载以序列头开头）。
Uint8List buildPack(double ptsSeconds, {int fill = 0x55}) {
  final head = packHeader((ptsSeconds * 90000).toInt());
  var es = <int>[
    ...sequenceHeader(),
    ...gopHeader(),
    ...pictureHeader(),
  ];
  final fixed = head.length + 6 + 3 + 10; // pack header + PES 固定头 + 时间戳
  final esLen = packSize - fixed;
  if (esLen < es.length) {
    throw StateError('pack 太小');
  }
  es = <int>[
    ...es,
    ...List<int>.filled(esLen - es.length, fill),
  ];
  final pts90k = (ptsSeconds * 90000).toInt();
  final pes = videoPes(pts90k, pts90k - 2700, Uint8List.fromList(es), 6 + 3 + 10 + es.length);
  final pack = Uint8List.fromList(<int>[...head, ...pes]);
  if (pack.length != packSize) {
    throw StateError('pack 长度不对: ${pack.length}');
  }
  return pack;
}

/// 生成含若干章的 VOB 码流；每章的 PTS 从 0 重新开始。
/// 真实 DVD 的第一个 pack 通常是导航包（stream id 0xBB），不是视频 PES。
///
/// 它不是随机访问点 —— 首章必须仍然从字节 0 开始，否则拼接哈希对不上源流。
Uint8List navPack() {
  final head = packHeader(0);
  final dataLen = packSize - head.length - 9;
  final data = Uint8List(dataLen)..fillRange(0, dataLen, 0x55);
  final pes = BytesBuilder(copy: false)
    ..add(const <int>[0x00, 0x00, 0x01, 0xBB])
    ..add(_u16(3 + data.length))
    ..add(const <int>[0x80, 0xC0, 0x00])
    ..add(data);
  final pack = BytesBuilder(copy: false)
    ..add(head)
    ..add(pes.takeBytes());
  final bytes = pack.takeBytes();
  assert(bytes.length == packSize, bytes.length);
  return bytes;
}

Uint8List _u16(int v) => Uint8List.fromList(<int>[(v >> 8) & 0xFF, v & 0xFF]);

Uint8List makeVobBytes(List<double> chapterDurations,
    {double gop = gopInterval, bool leadingNav = true}) {
  final out = BytesBuilder(copy: false);
  if (leadingNav) {
    out.add(navPack());
  }
  for (final duration in chapterDurations) {
    final count = pythonRound(duration / gop);
    final n = count < 1 ? 1 : count;
    for (var i = 0; i < n; i++) {
      out.add(buildPack(firstGopPts + i * gop));
    }
  }
  return out.takeBytes();
}

/// 写出一个（或按 [splitAt] 切成多个）VOB 文件，返回文件路径列表。
List<String> writeVob(
  String path,
  List<double> chapterDurations, {
  double gop = gopInterval,
  int splitAt = 0,
}) {
  final data = makeVobBytes(chapterDurations, gop: gop);
  if (splitAt <= 0) {
    File(path).writeAsBytesSync(data);
    return <String>[path];
  }
  final chunk = (data.length ~/ splitAt ~/ packSize) * packSize;
  final paths = <String>[];
  for (var i = 0; i < splitAt; i++) {
    final piece = i < splitAt - 1
        ? data.sublist(i * chunk, (i + 1) * chunk)
        : data.sublist(i * chunk);
    final file = '$path.${i + 1}';
    File(file).writeAsBytesSync(piece);
    paths.add(file);
  }
  return paths;
}

/// Python 的 round() 是「四舍六入五成双」（round half to even），
/// 而 Dart 的 [num.round] 是「五入」（half away from zero）。
///
/// 夹具里 6.0 / 0.48 == 12.5 正好落在 .5 上：Python 得 12，Dart 默认得 13，
/// 会让两套实现的合成码流差一个 pack。这里显式实现 Python 的舍入规则，
/// 保证 Dart 与 Python 生成的夹具逐字节一致。
int pythonRound(double value) {
  final floor = value.floorToDouble();
  final diff = value - floor;
  if (diff > 0.5) {
    return floor.toInt() + 1;
  }
  if (diff < 0.5) {
    return floor.toInt();
  }
  // 正好 .5：取偶数
  final f = floor.toInt();
  return f.isEven ? f : f + 1;
}

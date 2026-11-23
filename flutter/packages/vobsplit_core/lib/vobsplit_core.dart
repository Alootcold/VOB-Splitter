/// vobsplit_core —— DVD VOB 无损分割核心库（纯 Dart，无 Flutter 依赖）。
///
/// 核心保证：输出文件是输入码流的连续字节区间，逐字节复制，
/// 不重新编码、不重新封装、不改写任何一个字节。
///
/// 公开 API：
///  * [VobSource]   把多个 VOB 文件当作一条连续码流
///  * [buildIndex]  扫描码流，建立随机访问点（RAP）索引
///  * [detectChapters] 依据码流特征推导章节边界
///  * [split]       按章节切分并写出文件
///  * [verifyOutputs] 用 SHA-256 证明切分无损
library;

export 'src/chapters.dart';
export 'src/ps.dart';
export 'src/remux.dart';
export 'src/splitter.dart';

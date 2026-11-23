"""在真实 DVD 上验证 Dart 核心扫描期间事件循环是否被饿死。

这是 Flutter 界面「读 DVD 未响应」的机制验证：
如果扫描期间定时器能持续触发 ⇒ 事件队列拿得到时间片 ⇒ 界面能重绘。
"""
import os
import shutil
import subprocess
import sys

CORE = r"C:\Users\Lenovo\.minimax\sessions\mvs_11d98ac453304b228301186a9c1c547d\workspace\VOB-Splitter\flutter\packages\vobsplit_core"

script = os.path.join(CORE, 'tool', 'dvdscan_probe.dart')
os.makedirs(os.path.dirname(script), exist_ok=True)
with open(script, 'w', encoding='utf-8') as f:
    f.write('''
import 'dart:async';
import 'package:vobsplit_core/vobsplit_core.dart';

Future<void> main() async {
  final source = VobSource(<String>[
    r'G:\\VIDEO_TS\\VTS_01_1.VOB',
    r'G:\\VIDEO_TS\\VTS_01_2.VOB',
    r'G:\\VIDEO_TS\\VTS_01_3.VOB',
    r'G:\\VIDEO_TS\\VTS_01_4.VOB',
  ]);
  var ticks = 0;
  final timer = Timer.periodic(const Duration(milliseconds: 100), (_) => ticks++);
  final sw = Stopwatch()..start();
  var lastPercent = -1;
  final index = await buildIndex(source, onProgress: (frac) {
    final p = (frac * 100).floor();
    if (p != lastPercent && p % 10 == 0) {
      lastPercent = p;
      print('  扫描 $p%  (定时器已触发 $ticks 次)');
    }
  });
  timer.cancel();
  print('扫描完成: pack=${index.stats['packs']} RAP=${index.raps.length}');
  print('扫描耗时 ${sw.elapsedMilliseconds / 1000}s，期间定时器触发 $ticks 次');
  print(ticks > 0 ? 'OK: 事件循环没有被饿死，界面可以正常重绘' : 'FAIL: 事件循环被饿死');
}
''')

dart = os.path.join(os.path.expanduser('~'), 'Flutter', 'flutter', 'bin',
                    'cache', 'dart-sdk', 'bin', 'dart.exe')
r = subprocess.run([dart, 'run', 'tool/dvdscan_probe.dart'], cwd=CORE,
                   capture_output=True, text=True, encoding='utf-8',
                   errors='replace')
print(r.stdout[-2000:])
# 清理临时探针脚本
try:
    os.remove(script)
    print('(temporary probe cleaned)')
except OSError:
    pass
if r.returncode != 0:
    print('stderr:', r.stderr[-800:])

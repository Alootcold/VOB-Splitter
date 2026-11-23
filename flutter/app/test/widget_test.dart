import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vobsplit_gui/controller.dart';
import 'package:vobsplit_gui/main.dart';

void main() {
  // 侧栏内容按 960x640 的最小窗口设计，测试用更大的画布，保证全部渲染出来
  setUp(() {
    final view = TestWidgetsFlutterBinding.ensureInitialized().platformDispatcher.views.first;
    view.physicalSize = const Size(1440, 960);
    view.devicePixelRatio = 1.0;
  });
  tearDown(() {
    final view = TestWidgetsFlutterBinding.ensureInitialized().platformDispatcher.views.first;
    view.resetPhysicalSize();
    view.resetDevicePixelRatio();
  });

  testWidgets('首屏渲染出标题、控制栏与空状态', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());

    expect(find.text('VOB Splitter'), findsOneWidget);
    expect(find.text('源'), findsOneWidget);
    expect(find.text('切分方式'), findsOneWidget);
    expect(find.text('输出'), findsOneWidget);

    // 空状态给的是可操作的提示，而不是空白
    expect(find.textContaining('还没有章节'), findsOneWidget);
  });

  testWidgets('没选源与输出目录时主按钮禁用', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());

    final button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, '开始分割'),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('切分方式可切换，等长时出现间隔输入框', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());

    expect(find.textContaining('按 DVD 内置章节表切分'), findsOneWidget);

    await tester.tap(find.text('等长'));
    await tester.pumpAndSettle();

    expect(find.text('每段秒数'), findsOneWidget);
    expect(find.textContaining('按 DVD 内置章节表切分'), findsNothing);
  });

  testWidgets('校验徽章初始为未校验', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());
    expect(find.text('未校验'), findsOneWidget);
  });

  test('控制器：默认不可运行', () {
    final c = SplitController();
    expect(c.canRun, isFalse);
    expect(c.phase, Phase.idle);
    expect(c.busy, isFalse);
  });

  test('控制器：填齐源与输出后可以运行', () {
    final c = SplitController()
      ..sourcePath = 'D:\\VIDEO_TS'
      ..outputDir = 'D:\\Split';
    expect(c.canRun, isTrue);
  });

  test('控制器：目录展开跳过菜单 VOB', () {
    final c = SplitController();
    // 用合成目录验证「VTS_01_0.VOB 被跳过、_1 保留」
    final dir = Directory.systemTemp.createTempSync('vobsplit_widget');
    addTearDown(() => dir.deleteSync(recursive: true));
    for (final name in ['VTS_01_0.VOB', 'VTS_01_1.VOB', 'VTS_01_2.VOB']) {
      File('${dir.path}${Platform.pathSeparator}$name').writeAsBytesSync(List.filled(2048, 0));
    }
    c.sourcePath = dir.path;
    final sources = c.resolveSources();
    expect(sources.length, 2);
    expect(sources.any((s) => s.endsWith('VTS_01_0.VOB')), isFalse);

    c.includeMenu = true;
    expect(c.resolveSources().length, 3);
  });
}

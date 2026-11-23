import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:vobsplit_core/vobsplit_core.dart';
import 'package:vobsplit_gui/controller.dart';
import 'package:vobsplit_gui/main.dart';
import 'package:vobsplit_gui/theme.dart';
import 'package:vobsplit_gui/ui/chapter_table.dart';

void main() {
  testWidgets('主题确实是暗色', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());
    final ctx = tester.element(find.byType(Scaffold));
    final theme = Theme.of(ctx);
    expect(theme.brightness, Brightness.dark);
    expect(theme.scaffoldBackgroundColor, VobColors.surface);
    expect(theme.colorScheme.primary, VobColors.primary);
    expect(theme.colorScheme.onSurface, VobColors.onSurface);
    expect(theme.colorScheme.surfaceContainer, VobColors.surfaceContainer);
  });

  testWidgets('锁定暗色，不随系统主题变', (WidgetTester tester) async {
    await tester.pumpWidget(const VobSplitterApp());
    final app = tester.widget<MaterialApp>(find.byType(MaterialApp));
    expect(app.themeMode, ThemeMode.dark);
  });

  testWidgets('生成界面截图（golden）', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(const VobSplitterApp());
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(VobSplitterApp),
      matchesGoldenFile('goldens/gui.png'),
    );
  });

  testWidgets('章节表有数据时的排版（列不贴边）', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(900, 420);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = SplitController();
    controller.chapters = <Chapter>[
      for (var i = 0; i < 6; i++)
        Chapter(
          index: i,
          startOffset: 0,
          endOffset: 138842112,
          startPts: 0.367,
          endPts: 218.247,
          rapCount: 455 + i * 12,
          globalStart: i * 218.0,
          globalEnd: (i + 1) * 218.0,
        ),
    ];

    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(),
      darkTheme: buildTheme(),
      themeMode: ThemeMode.dark,
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: ChapterTable(controller: controller),
        ),
      ),
    ));
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(ChapterTable),
      matchesGoldenFile('goldens/table.png'),
    );
  });
}

import 'package:flutter/material.dart';

import 'controller.dart';
import 'theme.dart';
import 'ui/chapter_table.dart';
import 'ui/console_log.dart';
import 'ui/side_panel.dart';
import 'ui/verify_badge.dart';

void main() {
  runApp(const VobSplitterApp());
}

class VobSplitterApp extends StatelessWidget {
  const VobSplitterApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'VOB Splitter',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      // 显式锁定暗色：不让系统浅色主题影响，也不给「主题没生效」留余地
      themeMode: ThemeMode.dark,
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final SplitController controller = SplitController();

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                width: 320,
                child: SidePanel(controller: controller),
              ),
              const VerticalDivider(width: 1),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _TopBar(controller: controller),
                    const Divider(height: 1),
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(
                              flex: 3,
                              child: ChapterTable(controller: controller),
                            ),
                            Gap.m,
                            Expanded(
                              flex: 2,
                              child: ConsoleLog(controller: controller),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.controller});

  final SplitController controller;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      color: VobColors.surfaceLowest,
      child: Row(
        children: [
          Container(
            width: 4,
            height: 18,
            decoration: BoxDecoration(
              color: VobColors.primary,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Gap.m,
          Text(
            'VOB Splitter',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              letterSpacing: 0.2,
            ),
          ),
          Gap.s,
          Text(
            '无损分割',
            style: theme.textTheme.bodySmall?.copyWith(
              color: VobColors.onSurfaceVariant,
            ),
          ),
          const Spacer(),
          Semantics(
            label: '当前状态：${controller.statusText}',
            child: ExcludeSemantics(
              child: Text(
                controller.statusText,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: controller.phase == Phase.failed
                      ? VobColors.error
                      : VobColors.onSurfaceVariant,
                ),
              ),
            ),
          ),
          Gap.m,
          VerifyBadge(controller: controller),
          Gap.m,
          if (controller.busy)
            SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: VobColors.primary,
              ),
            ),
        ],
      ),
    );
  }
}

/// 托盘图标菜单里没用的占位（保持菜单栏简洁）。
// 窗口使用系统原生标题栏与红黄绿按钮，这里不做自绘交通灯。

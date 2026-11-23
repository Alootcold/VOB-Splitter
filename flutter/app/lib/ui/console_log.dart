import 'package:flutter/material.dart';

import '../controller.dart';
import '../theme.dart';

/// 只追加的日志面板。
class ConsoleLog extends StatelessWidget {
  const ConsoleLog({super.key, required this.controller});

  final SplitController controller;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            height: 32,
            color: VobColors.surfaceContainerHigh,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                const Text(
                  '日志',
                  style: TextStyle(
                    color: VobColors.onSurfaceVariant,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.8,
                  ),
                ),
                const Spacer(),
                if (controller.busy) ...[
                  const SizedBox(
                    width: 12,
                    height: 12,
                    child: CircularProgressIndicator(strokeWidth: 1.6),
                  ),
                  Gap.s,
                ],
                Text(
                  controller.statusText,
                  style: tabularStyle(null, size: 11),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: controller.logs.isEmpty
                ? const Center(
                    child: Text(
                      '运行日志会出现在这里',
                      style: TextStyle(fontSize: 12, color: VobColors.outlineVariant),
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    itemCount: controller.logs.length,
                    itemBuilder: (context, index) {
                      final line = controller.logs[index];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 2),
                        child: Text(
                          line,
                          style: const TextStyle(
                            fontFamily: 'Consolas',
                            fontFamilyFallback: ['Menlo', 'Monaco'],
                            fontSize: 11.5,
                            height: 1.45,
                            color: VobColors.onSurfaceVariant,
                          ),
                        ),
                      );
                    },
                  ),
          ),
          if (controller.busy)
            LinearProgressIndicator(
              value: controller.progress,
              minHeight: 2,
            ),
        ],
      ),
    );
  }
}

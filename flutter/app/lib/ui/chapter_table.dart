import 'package:flutter/material.dart';

import '../controller.dart';
import '../theme.dart';

/// 章节结果表：紧凑行高，数字等宽。
class ChapterTable extends StatelessWidget {
  const ChapterTable({super.key, required this.controller});

  final SplitController controller;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(context),
          const Divider(height: 1),
          Expanded(child: _body(context)),
        ],
      ),
    );
  }

  Widget _header(BuildContext context) {
    final style = const TextStyle(
      color: VobColors.onSurfaceVariant,
      fontSize: 11,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.8,
    );
    return Container(
      height: 32,
      color: VobColors.surfaceContainerHigh,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      child: Row(
        children: [
          SizedBox(width: 44, child: Text('章', style: style)),
          Expanded(flex: 3, child: Text('起始', style: style)),
          Expanded(flex: 3, child: Text('时长', style: style)),
          Expanded(flex: 3, child: Text('大小', style: style)),
          SizedBox(
            width: 64,
            child: Padding(
              padding: const EdgeInsets.only(left: 16),
              child: Text('GOP', style: style, textAlign: TextAlign.right),
            ),
          ),
        ],
      ),
    );
  }

  Widget _body(BuildContext context) {
    final chapters = controller.chapters;
    if (chapters.isEmpty) {
      return _empty(context);
    }
    return ListView.builder(
      padding: EdgeInsets.zero,
      itemCount: chapters.length,
      itemBuilder: (context, index) {
        final c = chapters[index];
        return _row(context, c);
      },
    );
  }

  Widget _row(BuildContext context, dynamic c) {
    final index = c.index as int;
    final size = c.size as int;
    final rapCount = c.rapCount as int;
    final globalStart = c.globalStart as double;
    final duration = c.duration as double?;
    final numStyle = tabularStyle(null);
    return Container(
      height: 32,
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: VobColors.outline.withValues(alpha: 0.5)),
        ),
      ),
      child: Padding(
        // 与表头保持一致的内边距，否则数字会顶在卡片边缘上
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: Text(
                (index + 1).toString().padLeft(2, '0'),
                style: numStyle.copyWith(color: VobColors.onSurface),
              ),
            ),
            Expanded(
              flex: 3,
              child: Text(_fmt(globalStart), style: numStyle),
            ),
            Expanded(
              flex: 3,
              child: Text(
                duration == null ? '—' : _fmt(duration),
                style: numStyle,
              ),
            ),
            Expanded(
              flex: 3,
              child: Text(_size(size), style: numStyle),
            ),
            SizedBox(
              width: 64,
              child: Padding(
                padding: const EdgeInsets.only(left: 16),
                child: Text('$rapCount',
                    style: numStyle, textAlign: TextAlign.right),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _empty(BuildContext context) {
    final String title;
    final String body;
    if (controller.sawNoChapters) {
      title = '没有检测到章节边界';
      body = '这个 VOB 里没有出现「时间戳归零」的章边界，可能不是 DVD 分章结构，'
          '也可能时间戳异常。换「等长」或「指定点」方式即可切。';
    } else if (controller.busy) {
      title = '正在分析…';
      body = '扫描码流、建立随机访问点索引。';
    } else {
      title = '还没有章节';
      body = '选择 VOB 文件或目录后点「开始分割」，这里会列出检测到的每一章。';
    }
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.segment_outlined, size: 28, color: VobColors.outlineVariant),
            Gap.m,
            Text(
              title,
              style: const TextStyle(fontSize: 14, color: VobColors.onSurface),
            ),
            Gap.s,
            Text(
              body,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 12,
                height: 1.6,
                color: VobColors.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _fmt(double seconds) {
    final s = seconds < 0 ? 0.0 : seconds;
    final h = (s / 3600).floor();
    final m = ((s % 3600) / 60).floor();
    final sec = s % 60;
    String two(int v) => v.toString().padLeft(2, '0');
    return '$h:${two(m)}:${sec.toStringAsFixed(3).padLeft(6, '0')}';
  }

  static String _size(int bytes) {
    if (bytes >= 1048576) {
      return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    }
    return '${(bytes / 1024).toStringAsFixed(1)} KB';
  }
}

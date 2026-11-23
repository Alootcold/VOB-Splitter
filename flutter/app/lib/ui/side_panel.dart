import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:vobsplit_core/vobsplit_core.dart';

import '../controller.dart';
import '../theme.dart';

/// 左侧控制栏：源 → 切分方式 → 输出 → 开始。
class SidePanel extends StatefulWidget {
  const SidePanel({super.key, required this.controller});

  final SplitController controller;

  @override
  State<SidePanel> createState() => _SidePanelState();
}

class _SidePanelState extends State<SidePanel> {
  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return Container(
      color: VobColors.surfaceLowest,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              children: [
                _SectionLabel('源'),
                Gap.s,
                _PathField(
                  label: 'VOB 文件或目录',
                  value: c.sourcePath,
                  hint: r'D:\VIDEO_TS 或 VTS_01_1.VOB',
                  onChanged: (v) => setState(() => c.sourcePath = v),
                  onBrowse: () => _browseDirectory((v) {
                    setState(() => c.sourcePath = v);
                  }),
                ),
                Gap.s,
                _CheckRow(
                  label: '包含菜单 VOB（TTS_xx_0.VOB）',
                  value: c.includeMenu,
                  onChanged: (v) => setState(() => c.includeMenu = v),
                ),
                Gap.xl,
                _SectionLabel('切分方式'),
                Gap.s,
                SegmentedButton<SplitMode>(
                  segments: const [
                    ButtonSegment(
                      value: SplitMode.auto,
                      label: Text('按章节'),
                      icon: Icon(Icons.segment_outlined, size: 16),
                    ),
                    ButtonSegment(
                      value: SplitMode.duration,
                      label: Text('等长'),
                      icon: Icon(Icons.timeline_outlined, size: 16),
                    ),
                    ButtonSegment(
                      value: SplitMode.times,
                      label: Text('指定点'),
                      icon: Icon(Icons.my_location_outlined, size: 16),
                    ),
                  ],
                  selected: {c.mode},
                  showSelectedIcon: false,
                  onSelectionChanged: (s) => setState(() => c.mode = s.first),
                ),
                Gap.s,
                if (c.mode == SplitMode.auto)
                  _HintText('按 DVD 内置章节表切分。每章都是独立 MPEG-2 '
                      'sequence，章首时间戳归零 —— 靠这一点定位章边界。')
                else if (c.mode == SplitMode.duration)
                  _NumberField(
                    label: '每段秒数',
                    value: c.intervalSeconds,
                    suffix: '秒',
                    onChanged: (v) => setState(() => c.intervalSeconds = v),
                  )
                else
                  _TextField(
                    label: '切点',
                    value: c.timesText,
                    hint: '0, 218, 489.28 或 00:01:30',
                    onChanged: (v) => setState(() => c.timesText = v),
                  ),
                Gap.xl,
                _SectionLabel('输出'),
                Gap.s,
                _PathField(
                  label: '输出目录',
                  value: c.outputDir,
                  hint: r'D:\Split',
                  onChanged: (v) => setState(() => c.outputDir = v),
                  onBrowse: () => _browseDirectory((v) {
                    setState(() => c.outputDir = v);
                  }),
                ),
                Gap.s,
                _TextField(
                  label: '文件名前缀',
                  value: c.prefix,
                  hint: 'chapter',
                  onChanged: (v) => setState(() => c.prefix = v),
                ),
                Gap.s,
                Row(
                  children: [
                    Expanded(
                      child: SegmentedButton<OutputFormat>(
                        segments: const [
                          ButtonSegment(value: OutputFormat.vob, label: Text('VOB')),
                          ButtonSegment(value: OutputFormat.mkv, label: Text('MKV')),
                          ButtonSegment(value: OutputFormat.both, label: Text('两者')),
                        ],
                        selected: {c.format},
                        showSelectedIcon: false,
                        onSelectionChanged: (s) => setState(() => c.format = s.first),
                      ),
                    ),
                  ],
                ),
                Gap.s,
                _HintText('VOB 是字节级原样切出，可直接再刻盘；MKV 需要 ffmpeg，'
                    '只换容器不重编码。'),
              ],
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                FilledButton.icon(
                  onPressed: c.canRun ? () => c.run() : null,
                  icon: const Icon(Icons.play_arrow_rounded, size: 18),
                  label: Text(c.busy ? '处理中…' : '开始分割'),
                ),
                if (c.error != null) ...[
                  Gap.s,
                  Text(
                    c.error!,
                    style: const TextStyle(color: VobColors.error, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _browseDirectory(void Function(String path) onPicked) async {
    try {
      final dir = await getDirectoryPath();
      if (dir != null) {
        onPicked(dir);
      }
    } catch (_) {
      // 平台不支持时静默降级为手动输入
    }
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: const TextStyle(
        color: VobColors.onSurfaceVariant,
        fontSize: 11,
        fontWeight: FontWeight.w600,
        letterSpacing: 1.1,
      ),
    );
  }
}

class _HintText extends StatelessWidget {
  const _HintText(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: VobColors.onSurfaceVariant,
        fontSize: 12,
        height: 1.5,
      ),
    );
  }
}

/// 自己持有 TextEditingController 的输入框。
///
/// 不在 build 里 new controller —— 否则每次重建都会把光标弹回末尾，
/// 打字时体验很差。
class _ManagedField extends StatefulWidget {
  const _ManagedField({
    required this.label,
    required this.value,
    required this.hint,
    required this.onChanged,
    this.trailing,
  });

  final String label;
  final String value;
  final String hint;
  final ValueChanged<String> onChanged;
  final Widget? trailing;

  @override
  State<_ManagedField> createState() => _ManagedFieldState();
}

class _ManagedFieldState extends State<_ManagedField> {
  late final TextEditingController _controller =
      TextEditingController(text: widget.value);
  final FocusNode _focus = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(_ManagedField oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 外部值变了且用户没在编辑时，才同步回输入框
    if (widget.value != _controller.text && !_focus.hasFocus) {
      _controller.text = widget.value;
    }
  }

  @override
  Widget build(BuildContext context) {
    final field = TextField(
      controller: _controller,
      focusNode: _focus,
      onChanged: widget.onChanged,
      style: const TextStyle(fontSize: 13),
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: widget.hint,
      ),
    );
    return Semantics(
      label: widget.label,
      textField: true,
      child: widget.trailing == null
          ? field
          : Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: field),
                Gap.s,
                widget.trailing!,
              ],
            ),
    );
  }
}

class _PathField extends StatelessWidget {
  const _PathField({
    required this.label,
    required this.value,
    required this.hint,
    required this.onChanged,
    required this.onBrowse,
  });

  final String label;
  final String value;
  final String hint;
  final ValueChanged<String> onChanged;
  final VoidCallback onBrowse;

  @override
  Widget build(BuildContext context) {
    return _ManagedField(
      label: label,
      value: value,
      hint: hint,
      onChanged: onChanged,
      trailing: Tooltip(
        message: '浏览',
        child: OutlinedButton(
          onPressed: onBrowse,
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(48, 48),
            padding: EdgeInsets.zero,
          ),
          child: const Icon(Icons.folder_open_outlined, size: 18),
        ),
      ),
    );
  }
}

class _TextField extends StatelessWidget {
  const _TextField({
    required this.label,
    required this.value,
    required this.hint,
    required this.onChanged,
  });

  final String label;
  final String value;
  final String hint;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return _ManagedField(
      label: label,
      value: value,
      hint: hint,
      onChanged: onChanged,
    );
  }
}

class _NumberField extends StatelessWidget {
  const _NumberField({
    required this.label,
    required this.value,
    required this.suffix,
    required this.onChanged,
  });

  final String label;
  final double value;
  final String suffix;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      textField: true,
      child: TextFormField(
        initialValue: value.toStringAsFixed(0),
        keyboardType: TextInputType.number,
        onChanged: (v) {
          final parsed = double.tryParse(v);
          if (parsed != null && parsed > 0) {
            onChanged(parsed);
          }
        },
        style: const TextStyle(fontSize: 13),
        decoration: InputDecoration(labelText: label, suffixText: suffix),
      ),
    );
  }
}

class _CheckRow extends StatelessWidget {
  const _CheckRow({
    required this.label,
    required this.value,
    required this.onChanged,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: label,
      toggled: value,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () => onChanged(!value),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Checkbox(
                  value: value,
                  onChanged: (v) => onChanged(v ?? false),
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                Gap.s,
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(
                      fontSize: 12,
                      color: VobColors.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

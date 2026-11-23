import 'package:flutter/material.dart';

import '../controller.dart';
import '../theme.dart';

/// 无损校验结论徽章。
///
/// 这是整个工具最该被看见的东西：切完之后，
/// 「源流 SHA-256」和「出流 SHA-256」是否一致。
class VerifyBadge extends StatelessWidget {
  const VerifyBadge({super.key, required this.controller});

  final SplitController controller;

  @override
  Widget build(BuildContext context) {
    final verified = controller.verified;
    final bool failed = verified == false;

    final IconData icon;
    final String text;
    final Color accent;

    if (verified == null) {
      icon = Icons.shield_outlined;
      text = '未校验';
      accent = VobColors.outlineVariant;
    } else if (failed) {
      icon = Icons.error_outline;
      text = '校验未通过';
      accent = VobColors.error;
    } else {
      icon = Icons.verified_outlined;
      text = '无损校验通过';
      accent = VobColors.primary;
    }

    return Semantics(
      label: failed ? '无损校验未通过' : (verified == null ? '尚未校验' : '无损校验通过'),
      child: Tooltip(
        message: _tooltip(verified),
        child: Container(
          height: 28,
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: BoxDecoration(
            borderRadius: Radii.sm,
            border: Border.all(color: accent.withValues(alpha: 0.55)),
            color: accent.withValues(alpha: 0.08),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 15, color: accent),
              Gap.s,
              Text(
                text,
                style: TextStyle(
                  fontSize: 12,
                  color: accent,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _tooltip(bool? verified) {
    final src = controller.sourceHash;
    final out = controller.outputHash;
    if (verified == null) {
      return '切分完成后会在这里给出 SHA-256 比对结论';
    }
    return '源流 SHA-256\n$src\n\n出流 SHA-256\n$out';
  }
}

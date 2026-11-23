import 'package:flutter/material.dart';

/// VOB Splitter 的配色。
///
/// 手工指定 ColorScheme，不使用 ColorScheme.fromSeed —— fromSeed 会按种子色
/// 派生出一整套带色相偏移的表面色，在暗色界面里会糊成偏蓝/偏紫的一团。
/// 这里每个表面色都单独指定，保证暗部层次干净。
class VobColors {
  const VobColors._();

  static const surface = Color(0xFF0D0E11);
  static const surfaceLowest = Color(0xFF111318);
  static const surfaceContainer = Color(0xFF16181D);
  static const surfaceContainerHigh = Color(0xFF1C1F26);
  static const outline = Color(0xFF2A2E37);
  static const outlineVariant = Color(0xFF3A3F4A);
  static const onSurface = Color(0xFFE7E9ED);
  static const onSurfaceVariant = Color(0xFF9BA1AC);
  static const primary = Color(0xFF5AA9B8);
  static const onPrimary = Color(0xFF06171B);
  static const error = Color(0xFFE06C75);
  static const onError = Color(0xFF2B0A0D);
}

/// 间距只用 4 / 8 / 12 / 16 / 24。
class Gap {
  const Gap._();

  static const xs = SizedBox(height: 4, width: 4);
  static const s = SizedBox(height: 8, width: 8);
  static const m = SizedBox(height: 12, width: 12);
  static const l = SizedBox(height: 16, width: 16);
  static const xl = SizedBox(height: 24, width: 24);
}

/// 圆角只用 6 / 10 / 16。
class Radii {
  const Radii._();

  static const sm = BorderRadius.all(Radius.circular(6));
  static const md = BorderRadius.all(Radius.circular(10));
  static const lg = BorderRadius.all(Radius.circular(16));
}

/// 统一的动效曲线与时长。
class Motion {
  const Motion._();

  static const curve = Cubic(0.2, 0.0, 0.0, 1.0);
  static const fast = Duration(milliseconds: 120);
  static const normal = Duration(milliseconds: 180);
}

ThemeData buildTheme() {
  const scheme = ColorScheme(
    brightness: Brightness.dark,
    primary: VobColors.primary,
    onPrimary: VobColors.onPrimary,
    secondary: VobColors.primary,
    onSecondary: VobColors.onPrimary,
    error: VobColors.error,
    onError: VobColors.onError,
    surface: VobColors.surface,
    onSurface: VobColors.onSurface,
    surfaceContainerLowest: VobColors.surfaceLowest,
    surfaceContainerLow: VobColors.surfaceLowest,
    surfaceContainer: VobColors.surfaceContainer,
    surfaceContainerHigh: VobColors.surfaceContainerHigh,
    surfaceContainerHighest: VobColors.surfaceContainerHigh,
    onSurfaceVariant: VobColors.onSurfaceVariant,
    outline: VobColors.outline,
    outlineVariant: VobColors.outlineVariant,
    shadow: Colors.black,
    scrim: Colors.black,
    inverseSurface: VobColors.onSurface,
    onInverseSurface: VobColors.surface,
    inversePrimary: VobColors.primary,
  );

  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: VobColors.surface,
    splashFactory: NoSplash.splashFactory,
    visualDensity: VisualDensity.standard,
  );

  return base.copyWith(
    // 不指定 fontFamily：跟随平台（Windows → Segoe UI，macOS → SF Pro）
    textTheme: base.textTheme.apply(
      bodyColor: VobColors.onSurface,
      displayColor: VobColors.onSurface,
    ),
    dividerTheme: const DividerThemeData(
      color: VobColors.outline,
      thickness: 1,
      space: 1,
    ),
    iconTheme: const IconThemeData(color: VobColors.onSurfaceVariant, size: 18),
    cardTheme: const CardThemeData(
      color: VobColors.surfaceContainer,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: Radii.md,
        side: BorderSide(color: VobColors.outline),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: VobColors.surfaceLowest,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      hintStyle: const TextStyle(color: VobColors.onSurfaceVariant, fontSize: 13),
      labelStyle: const TextStyle(color: VobColors.onSurfaceVariant, fontSize: 13),
      floatingLabelStyle: const TextStyle(color: VobColors.primary, fontSize: 13),
      border: const OutlineInputBorder(
        borderRadius: Radii.sm,
        borderSide: BorderSide(color: VobColors.outline),
      ),
      enabledBorder: const OutlineInputBorder(
        borderRadius: Radii.sm,
        borderSide: BorderSide(color: VobColors.outline),
      ),
      focusedBorder: const OutlineInputBorder(
        borderRadius: Radii.sm,
        borderSide: BorderSide(color: VobColors.primary, width: 1.4),
      ),
      errorBorder: const OutlineInputBorder(
        borderRadius: Radii.sm,
        borderSide: BorderSide(color: VobColors.error),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: VobColors.primary,
        foregroundColor: VobColors.onPrimary,
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 16),
        shape: const RoundedRectangleBorder(borderRadius: Radii.sm),
        textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: VobColors.onSurface,
        minimumSize: const Size(0, 48),
        padding: const EdgeInsets.symmetric(horizontal: 16),
        side: const BorderSide(color: VobColors.outline),
        shape: const RoundedRectangleBorder(borderRadius: Radii.sm),
        textStyle: const TextStyle(fontSize: 13),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: VobColors.primary,
        minimumSize: const Size(0, 40),
        textStyle: const TextStyle(fontSize: 13),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        side: const WidgetStatePropertyAll(
          BorderSide(color: VobColors.outline),
        ),
        backgroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return VobColors.surfaceContainerHigh;
          }
          return Colors.transparent;
        }),
        foregroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return VobColors.onSurface;
          }
          return VobColors.onSurfaceVariant;
        }),
        textStyle: const WidgetStatePropertyAll(TextStyle(fontSize: 13)),
      ),
    ),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 500),
      decoration: BoxDecoration(
        color: VobColors.surfaceContainerHigh,
        borderRadius: Radii.sm,
        border: Border.all(color: VobColors.outlineVariant),
      ),
      textStyle: const TextStyle(color: VobColors.onSurface, fontSize: 12),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: VobColors.primary,
      linearTrackColor: VobColors.surfaceContainerHigh,
      circularTrackColor: VobColors.surfaceContainerHigh,
    ),
    scrollbarTheme: ScrollbarThemeData(
      thumbColor: WidgetStatePropertyAll(VobColors.outlineVariant),
      thickness: const WidgetStatePropertyAll(8),
      radius: const Radius.circular(4),
    ),
  );
}

/// 表格里的数字用等宽数字，避免列宽跳动。
TextStyle tabularStyle(TextStyle? base, {double size = 12, Color? color}) {
  return (base ?? const TextStyle()).copyWith(
    fontSize: size,
    color: color ?? VobColors.onSurfaceVariant,
    fontFeatures: const [FontFeature.tabularFigures()],
  );
}

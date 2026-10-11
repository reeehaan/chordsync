import 'package:flutter/material.dart';

import 'practice_stage_colors.dart';

/// Dark "stage" theme the practice sheet renders under.
ThemeData practiceStageTheme(ThemeData baseTheme) {
  final stageScheme = baseTheme.colorScheme.copyWith(
    brightness: Brightness.dark,
    primary: PracticeStageColors.amber,
    onPrimary: PracticeStageColors.background,
    secondary: PracticeStageColors.amberBright,
    surface: PracticeStageColors.surface,
    onSurface: PracticeStageColors.textPrimary,
    outline: PracticeStageColors.border,
    outlineVariant: PracticeStageColors.border,
  );
  return baseTheme.copyWith(
    colorScheme: stageScheme,
    scaffoldBackgroundColor: PracticeStageColors.background,
    textTheme: baseTheme.textTheme.apply(
      bodyColor: PracticeStageColors.textPrimary,
      displayColor: PracticeStageColors.textPrimary,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: PracticeStageColors.background,
      foregroundColor: PracticeStageColors.textPrimary,
      elevation: 0,
    ),
    cardTheme: baseTheme.cardTheme.copyWith(
      color: PracticeStageColors.surface,
      surfaceTintColor: Colors.transparent,
    ),
    dividerColor: PracticeStageColors.border,
    sliderTheme: baseTheme.sliderTheme.copyWith(
      activeTrackColor: PracticeStageColors.amberBright,
      inactiveTrackColor: PracticeStageColors.border,
      thumbColor: PracticeStageColors.amberBright,
      trackHeight: 3,
      overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
      thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
    ),
  );
}

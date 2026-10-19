import 'package:flutter/material.dart';

import 'practice_stage_colors.dart';

/// Golden Hour theme with the practice sheet's own slider (and accents).
ThemeData practiceStageTheme(ThemeData baseTheme) {
  final stageScheme = baseTheme.colorScheme.copyWith(
    primary: PracticeStageColors.amber,
    onPrimary: PracticeStageColors.surface,
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
    // The slider sits on the espresso player bar.
    sliderTheme: baseTheme.sliderTheme.copyWith(
      activeTrackColor: PracticeStageColors.playerAccent,
      inactiveTrackColor: PracticeStageColors.playerTrack,
      thumbColor: PracticeStageColors.playerAccent,
      trackHeight: 3,
      overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
      thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
    ),
  );
}

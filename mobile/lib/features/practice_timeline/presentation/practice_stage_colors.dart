import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Colors used by the live practice experience, taken from the Golden Hour
/// theme so the practice sheet matches the rest of the app: parchment page,
/// pale-peach chord chips, burnt-sienna accents, and an espresso player.
abstract final class PracticeStageColors {
  static const background = ChordSyncColors.background;
  static const surface = ChordSyncColors.surface;
  static const surfaceRaised = ChordSyncColors.surfaceAlt;
  static const border = ChordSyncColors.border;
  static const textPrimary = ChordSyncColors.textPrimary;
  static const textSecondary = ChordSyncColors.textSecondary;
  static const textFaint = ChordSyncColors.chipTextUpcoming;

  /// Accent for labels and icons, and the colour of the word being sung.
  static const amber = ChordSyncColors.brand;
  static const amberBright = ChordSyncColors.brand;
  static const activeWord = ChordSyncColors.surfaceAlt;

  /// The espresso "dark nav/player" bar and the colours drawn on it.
  static const player = ChordSyncColors.brandDark;
  static const onPlayer = ChordSyncColors.surfaceAlt;
  static const onPlayerMuted = Color(0xFFBBA894); // derived from surfaceAlt
  static const playerAccent = ChordSyncColors.brandAccent;
  static const playerTrack = Color(0x33F5E1D2); // surfaceAlt at 20%
}

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Colors used by the live practice experience, taken from the Golden Hour
/// theme so the practice sheet matches the rest of the app: parchment page,
/// pale-peach chord chips, burnt-sienna accents, and an espresso player.
abstract final class PracticeStageColors {
  static Color get background => ChordSyncColors.background;
  static Color get surface => ChordSyncColors.surface;
  static Color get surfaceRaised => ChordSyncColors.surfaceAlt;
  static Color get border => ChordSyncColors.border;
  static Color get textPrimary => ChordSyncColors.textPrimary;
  static Color get textSecondary => ChordSyncColors.textSecondary;
  static Color get textFaint => ChordSyncColors.chipTextUpcoming;

  /// The not-yet-played beat segments of the chord being played. Darker than
  /// [border] so they stay visible on the pale-peach card, yet clearly
  /// different from the burnt-sienna of a played beat.
  static Color get beatTrack =>
      ChordSyncColors.dark ? const Color(0xFF6B5948) : const Color(0xFF9E8D7C);

  /// Accent for labels and icons, and the colour of the word being sung.
  static Color get amber => ChordSyncColors.brand;
  static Color get amberBright => ChordSyncColors.brand;
  static Color get activeWord => ChordSyncColors.surfaceAlt;

  /// The espresso "dark nav/player" bar and the colours drawn on it.
  static Color get player => ChordSyncColors.brandDark;
  static const onPlayer = Color(
    0xFFF5E1D2,
  ); // pale peach, on espresso in both palettes
  static const onPlayerMuted = Color(0xFFBBA894); // derived from surfaceAlt
  static Color get playerAccent => ChordSyncColors.brandAccent;
  static const playerTrack = Color(0x33F5E1D2); // surfaceAlt at 20%
}

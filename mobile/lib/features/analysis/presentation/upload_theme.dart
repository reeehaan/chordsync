import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Colors for the Home, Add song and Tuner tabs, from the Golden Hour theme:
/// parchment page, white cards, and an espresso bottom nav.
abstract final class UploadPalette {
  static const background = ChordSyncColors.background;
  static const card = ChordSyncColors.surface;
  static const border = ChordSyncColors.border;
  static const primaryText = ChordSyncColors.textPrimary;
  static const secondaryText = ChordSyncColors.textSecondary;

  /// The espresso "dark nav" and what is drawn on it.
  static const dock = ChordSyncColors.brandDark;
  static const dockSelected = Color(0xFF45362D); // lifted from espresso
  static const dockIcon = ChordSyncColors.surfaceAlt;
  static const dockIconSelected = ChordSyncColors.brandAccent;
  static const dockShadow = Color(0x292B201B);
}

/// The app theme already is the Golden Hour theme; the tabs use it as is.
ThemeData uploadTheme(BuildContext context) => Theme.of(context);

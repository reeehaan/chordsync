import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Colors for the Home, Add song and Tuner tabs, from the Golden Hour theme:
/// parchment page, white cards, and an espresso bottom nav.
abstract final class UploadPalette {
  static Color get background => ChordSyncColors.background;
  static Color get card => ChordSyncColors.surface;
  static Color get border => ChordSyncColors.border;
  static Color get primaryText => ChordSyncColors.textPrimary;
  static Color get secondaryText => ChordSyncColors.textSecondary;

  /// The espresso "dark nav" and what is drawn on it.
  static Color get dock => ChordSyncColors.brandDark;
  static const dockSelected = Color(0xFF45362D); // lifted from espresso
  static const dockIcon = Color(0xFFF5E1D2); // drawn on the espresso dock
  static Color get dockIconSelected => ChordSyncColors.brandAccent;
  static const dockShadow = Color(0x292B201B);
}

/// The app theme already is the Golden Hour theme; the tabs use it as is.
ThemeData uploadTheme(BuildContext context) => Theme.of(context);

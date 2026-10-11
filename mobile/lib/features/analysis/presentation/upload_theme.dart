import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Dark palette shared by the upload, library, and tuner tabs.
abstract final class UploadPalette {
  static const background = Color(0xFF171411);
  static const card = Color(0xFF241E1A);
  static const dock = Color(0xFF181512);
  static const selected = Color(0xFF403A36);
  static const border = Color(0xFF3B3531);
  static const primaryText = Color(0xFFF6F2ED);
  static const secondaryText = Color(0xFFB8AEA6);
  static const coral = Color(0xFFFF7779);
}

ThemeData uploadTheme(BuildContext context) {
  final base = Theme.of(context);
  return base.copyWith(
    scaffoldBackgroundColor: UploadPalette.background,
    textTheme: base.textTheme.apply(
      bodyColor: UploadPalette.primaryText,
      displayColor: UploadPalette.primaryText,
    ),
    iconTheme: const IconThemeData(color: UploadPalette.primaryText),
    cardTheme: CardThemeData(
      color: UploadPalette.card,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ChordSyncRadii.card),
        side: const BorderSide(color: UploadPalette.border),
      ),
    ),
  );
}

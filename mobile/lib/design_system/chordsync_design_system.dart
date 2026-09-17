import 'package:flutter/material.dart';

/// Warm, material-inspired tokens shared by the add and song-sheet screens.
abstract final class ChordSyncColors {
  static const background = Color(0xFFF9F5ED);
  static const surface = Color(0xFFFFFCF7);
  static const surfaceAlt = Color(0xFFF1E5D5);
  static const textPrimary = Color(0xFF2B1B12);
  static const textSecondary = Color(0xFF69584B);
  static const brand = Color(0xFF5B3A28);
  static const brandDark = Color(0xFF3A261B);
  static const brandAccent = Color(0xFFA4713F);
  static const honey = Color(0xFFC58B4E);
  static const border = Color(0xFFD8C5AF);
  static const success = Color(0xFF486B3D);
  static const warning = Color(0xFF8A5918);
  static const error = Color(0xFFA83D30);
  static const currentChord = brandDark;
  static const inactiveChord = surfaceAlt;
}

abstract final class ChordSyncSpace {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}

abstract final class ChordSyncRadii {
  static const card = 18.0;
  static const control = 12.0;
}

abstract final class ChordSyncTypography {
  // Georgia is available on iOS/macOS; Flutter's sans fallback handles UI.
  static const displayFamily = 'Georgia';

  static TextTheme textTheme() => const TextTheme(
    displayLarge: TextStyle(
      fontFamily: displayFamily,
      fontSize: 56,
      height: 1.05,
      fontWeight: FontWeight.w700,
    ),
    displayMedium: TextStyle(
      fontFamily: displayFamily,
      fontSize: 38,
      height: 1.12,
      fontWeight: FontWeight.w700,
    ),
    headlineSmall: TextStyle(
      fontFamily: displayFamily,
      fontSize: 27,
      height: 1.2,
      fontWeight: FontWeight.w600,
    ),
    titleLarge: TextStyle(fontSize: 21, fontWeight: FontWeight.w700),
    titleMedium: TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
    bodyLarge: TextStyle(fontSize: 17, height: 1.45),
    bodyMedium: TextStyle(fontSize: 15, height: 1.45),
    labelLarge: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
    labelMedium: TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
  );
}

abstract final class ChordSyncTheme {
  static ThemeData light() {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: ChordSyncColors.brand,
          brightness: Brightness.light,
        ).copyWith(
          primary: ChordSyncColors.brand,
          onPrimary: ChordSyncColors.background,
          primaryContainer: ChordSyncColors.surfaceAlt,
          onPrimaryContainer: ChordSyncColors.textPrimary,
          secondary: ChordSyncColors.brandAccent,
          onSecondary: ChordSyncColors.textPrimary,
          secondaryContainer: ChordSyncColors.surfaceAlt,
          onSecondaryContainer: ChordSyncColors.textPrimary,
          surface: ChordSyncColors.surface,
          onSurface: ChordSyncColors.textPrimary,
          error: ChordSyncColors.error,
          onError: ChordSyncColors.surface,
          outline: ChordSyncColors.border,
          outlineVariant: ChordSyncColors.border,
        );
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: ChordSyncColors.background,
    );
    return base.copyWith(
      textTheme: ChordSyncTypography.textTheme().apply(
        bodyColor: ChordSyncColors.textPrimary,
        displayColor: ChordSyncColors.textPrimary,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: ChordSyncColors.background,
        foregroundColor: ChordSyncColors.textPrimary,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardThemeData(
        color: ChordSyncColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.card),
          side: const BorderSide(color: ChordSyncColors.border),
        ),
      ),
      dividerColor: ChordSyncColors.border,
      iconTheme: const IconThemeData(color: ChordSyncColors.brand),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: ChordSyncColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: const BorderSide(color: ChordSyncColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: const BorderSide(color: ChordSyncColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: const BorderSide(color: ChordSyncColors.brand, width: 2),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: ChordSyncColors.brand,
          foregroundColor: ChordSyncColors.background,
          disabledBackgroundColor: ChordSyncColors.surfaceAlt,
          disabledForegroundColor: ChordSyncColors.textSecondary,
          minimumSize: const Size(44, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(ChordSyncRadii.control),
            side: const BorderSide(color: ChordSyncColors.brand),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ChordSyncColors.brand,
          minimumSize: const Size(44, 50),
          side: const BorderSide(color: ChordSyncColors.brand),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: ChordSyncColors.brand,
          minimumSize: const Size(44, 44),
        ),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: ChordSyncColors.brandAccent,
        linearTrackColor: ChordSyncColors.surfaceAlt,
        circularTrackColor: ChordSyncColors.surfaceAlt,
      ),
      sliderTheme: base.sliderTheme.copyWith(
        activeTrackColor: ChordSyncColors.brand,
        inactiveTrackColor: ChordSyncColors.border,
        thumbColor: ChordSyncColors.brand,
      ),
    );
  }
}

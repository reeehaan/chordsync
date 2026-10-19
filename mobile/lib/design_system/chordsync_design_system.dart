import 'package:flutter/material.dart';

/// "Golden Hour" — burnt sienna / warm amber / espresso brown on a parchment
/// background, with pale-peach chord highlights. Warm and reading-focused,
/// built from a user-specified palette.
/// Display: Newsreader (song titles & lyrics). Body/UI: DM Sans (controls &
/// instructional content).
abstract final class ChordSyncColors {
  static const background = Color(0xFFFBF6EC); // Parchment
  static const surface = Color(0xFFFFFFFF);
  static const surfaceAlt = Color(0xFFF5E1D2); // Pale peach — chord highlights
  static const textPrimary = Color(0xFF29231F); // Charcoal brown
  static const textSecondary = Color(
    0xFF6E6054,
  ); // derived, not in the spec — muted charcoal
  static const brand = Color(0xFFA84F2A); // Burnt sienna
  static const brandDark = Color(
    0xFF2B201B,
  ); // Espresso brown — dark nav/player
  static const brandAccent = Color(
    0xFFD88732,
  ); // Warm amber — interactive accent
  static const honey = Color(0xFFD88732); // same as brandAccent in this palette
  static const border = Color(
    0xFFEAD9C3,
  ); // derived from the peach/parchment family

  // State triad. `warning` reuses the spec's warm amber (it already reads as
  // a warning color). `success` and `error` are NOT in the spec — added so
  // the app has a pass/fail signal that isn't just "more orange": a blue
  // keeps success distinguishable from both burnt sienna and the error red
  // for colorblind users. Flagging this because burnt sienna (#A84F2A) and
  // a standard error red sit close in hue — if that pairing is ever used
  // for a right/wrong indicator, pair it with an icon or shape too, not
  // color alone.
  static const success = Color(
    0xFF2E6FA3,
  ); // blue — not in the spec, added for state feedback
  static const warning = Color(0xFFD88732); // = brandAccent, per the spec
  static const error = Color(
    0xFF9E2B45,
  ); // crimson, pulled toward magenta to clear `brand`

  static const currentChord = brandDark;
  static const inactiveChord = surfaceAlt;

  /// Chord-chip states now share one background (`surfaceAlt`, the pale
  /// peach) — state is shown by border + text color + icon instead of a
  /// background swap:
  ///   upcoming        → chipBorderUpcoming (invisible), chipTextUpcoming
  ///   already played  → chipBorderPlayed (solid sienna), chipTextPlayed
  ///   now playing     → solid brandDark fill, white text, play icon
  static const chipBorderUpcoming = Colors.transparent;
  static const chipTextUpcoming = Color(0xFF8A7A6B);
  static const chipBorderPlayed = brand; // solid, fully opaque sienna
  static const chipTextPlayed = textPrimary;
}

abstract final class ChordSyncSpace {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}

abstract final class ChordSyncRadii {
  static const card = 16.0;
  static const control = 10.0;
}

abstract final class ChordSyncTypography {
  static const displayFamily = 'Newsreader'; // song titles & lyrics
  static const bodyFamily = 'DM Sans'; // controls & instructional content

  static TextTheme textTheme() => const TextTheme(
    displayLarge: TextStyle(
      fontFamily: displayFamily,
      fontSize: 54,
      height: 1.1,
      fontWeight: FontWeight.w600,
    ),
    displayMedium: TextStyle(
      fontFamily: displayFamily,
      fontSize: 37,
      height: 1.15,
      fontWeight: FontWeight.w600,
    ),
    headlineSmall: TextStyle(
      fontFamily: displayFamily,
      fontSize: 26,
      height: 1.22,
      fontWeight: FontWeight.w600,
    ),
    titleLarge: TextStyle(
      fontFamily: bodyFamily,
      fontSize: 20,
      fontWeight: FontWeight.w700,
    ),
    titleMedium: TextStyle(
      fontFamily: bodyFamily,
      fontSize: 16,
      fontWeight: FontWeight.w600,
    ),
    bodyLarge: TextStyle(
      fontFamily: displayFamily, // lyrics are body-ish but still "reading" text
      fontSize: 17,
      height: 1.5,
    ),
    bodyMedium: TextStyle(fontFamily: bodyFamily, fontSize: 14, height: 1.5),
    labelLarge: TextStyle(
      fontFamily: bodyFamily,
      fontSize: 14,
      fontWeight: FontWeight.w700,
    ),
    labelMedium: TextStyle(
      fontFamily: bodyFamily,
      fontSize: 12,
      fontWeight: FontWeight.w600,
    ),
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
          onPrimary: ChordSyncColors.surface,
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
          backgroundColor: ChordSyncColors.brandDark,
          foregroundColor: ChordSyncColors.background,
          disabledBackgroundColor: ChordSyncColors.surfaceAlt,
          disabledForegroundColor: ChordSyncColors.textSecondary,
          minimumSize: const Size(44, 52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: ChordSyncColors.brand,
          minimumSize: const Size(44, 50),
          side: const BorderSide(color: ChordSyncColors.brand, width: 1.5),
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

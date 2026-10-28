import 'package:flutter/material.dart';

/// "Golden Hour" — burnt sienna / warm amber / espresso brown on a parchment
/// background, with pale-peach chord highlights. Warm and reading-focused,
/// built from a user-specified palette.
/// Display: Newsreader (song titles & lyrics). Body/UI: DM Sans (controls &
/// instructional content).
abstract final class ChordSyncColors {
  /// True while the dark palette is in use. The app sets it (see
  /// `AppearanceController`) before any screen is drawn, so every colour below
  /// answers for the palette on screen.
  static bool dark = false;

  static Color _pick(Color light, Color night) => dark ? night : light;

  static Color get background =>
      _pick(const Color(0xFFFBF6EC), const Color(0xFF181210)); // Parchment
  static Color get surface =>
      _pick(const Color(0xFFFFFFFF), const Color(0xFF251C17));
  static Color get surfaceAlt => _pick(
    const Color(0xFFF5E1D2), // Pale peach — chord highlights
    const Color(0xFF3B2B22),
  );
  static Color get textPrimary =>
      _pick(const Color(0xFF29231F), const Color(0xFFF4E8D8)); // Charcoal brown
  static Color get textSecondary =>
      _pick(const Color(0xFF6E6054), const Color(0xFFBDAA96));
  static Color get brand =>
      _pick(const Color(0xFFA84F2A), const Color(0xFFE48B5C)); // Burnt sienna
  static Color get brandDark => _pick(
    const Color(0xFF2B201B), // Espresso brown — dark nav/player
    const Color(0xFF30231C),
  );
  static Color get brandAccent =>
      _pick(const Color(0xFFD88732), const Color(0xFFE79A45)); // Warm amber
  static Color get honey => brandAccent;

  /// A firmer edge for cards on the page.
  static Color get cardEdge =>
      _pick(const Color(0xFFD9C3A3), const Color(0xFF4D3A2D));
  static Color get border =>
      _pick(const Color(0xFFEAD9C3), const Color(0xFF3D2E24));

  // State triad. `warning` reuses the warm amber. `success` is a blue so it
  // stays distinguishable from burnt sienna and from the error red for
  // colourblind users; pair state colours with an icon or shape too.
  static Color get success =>
      _pick(const Color(0xFF2E6FA3), const Color(0xFF6AAEE0));
  static Color get warning => brandAccent;
  static Color get error =>
      _pick(const Color(0xFF9E2B45), const Color(0xFFFF8FA6));

  /// The chord being played: espresso on parchment, honey at night.
  static Color get currentChord => _pick(brandDark, brandAccent);
  static Color get inactiveChord => surfaceAlt;

  /// Chord-chip states share one background (`surfaceAlt`); state is shown by
  /// border, text colour and icon instead of a background swap.
  static const chipBorderUpcoming = Colors.transparent;
  static Color get chipTextUpcoming =>
      _pick(const Color(0xFF8A7A6B), const Color(0xFFA08F7E));
  static Color get chipBorderPlayed => brand;
  static Color get chipTextPlayed => textPrimary;
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
  static const displayFamily = 'Newsreader'; // song titles
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
  /// The parchment theme. Sets the palette, so call it only when drawing.
  static ThemeData light() => _build(Brightness.light);

  /// Golden Hour at night: espresso page, warm cream text, honey accents.
  static ThemeData dark() => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    ChordSyncColors.dark = brightness == Brightness.dark;
    final night = ChordSyncColors.dark;
    final scheme =
        ColorScheme.fromSeed(
          seedColor: ChordSyncColors.brand,
          brightness: brightness,
        ).copyWith(
          primary: ChordSyncColors.brand,
          onPrimary: night
              ? ChordSyncColors.background
              : ChordSyncColors.surface,
          primaryContainer: ChordSyncColors.surfaceAlt,
          onPrimaryContainer: ChordSyncColors.textPrimary,
          secondary: ChordSyncColors.brandAccent,
          onSecondary: ChordSyncColors.textPrimary,
          secondaryContainer: ChordSyncColors.surfaceAlt,
          onSecondaryContainer: ChordSyncColors.textPrimary,
          surface: ChordSyncColors.surface,
          onSurface: ChordSyncColors.textPrimary,
          error: ChordSyncColors.error,
          onError: night ? ChordSyncColors.background : ChordSyncColors.surface,
          outline: ChordSyncColors.border,
          outlineVariant: ChordSyncColors.border,
        );
    final base = ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: ChordSyncColors.background,
    );
    return base.copyWith(
      textTheme: ChordSyncTypography.textTheme().apply(
        bodyColor: ChordSyncColors.textPrimary,
        displayColor: ChordSyncColors.textPrimary,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: ChordSyncColors.background,
        foregroundColor: ChordSyncColors.textPrimary,
        elevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardThemeData(
        color: ChordSyncColors.surface,
        // A soft lift and a firmer edge, so white cards stand out from the
        // parchment page instead of fading into it.
        elevation: 2,
        shadowColor: night ? Colors.black : const Color(0x4D2B201B),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.card),
          side: BorderSide(color: ChordSyncColors.cardEdge, width: 1.2),
        ),
      ),
      dividerColor: ChordSyncColors.border,
      iconTheme: IconThemeData(color: ChordSyncColors.brand),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: ChordSyncColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: BorderSide(color: ChordSyncColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: BorderSide(color: ChordSyncColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(ChordSyncRadii.control),
          borderSide: BorderSide(color: ChordSyncColors.brand, width: 2),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: night
              ? ChordSyncColors.brandAccent
              : ChordSyncColors.brandDark,
          foregroundColor: night
              ? ChordSyncColors.background
              : ChordSyncColors.background,
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
          side: BorderSide(color: ChordSyncColors.brand, width: 1.5),
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
      progressIndicatorTheme: ProgressIndicatorThemeData(
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

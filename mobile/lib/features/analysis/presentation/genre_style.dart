import 'package:flutter/material.dart';

/// The two colours of a genre's banner and tile. Warm and rich, to sit with the
/// Golden Hour theme; the text over them is white, and the darker colour sits
/// where the text does.
class GenreStyle {
  const GenreStyle(this.light, this.dark);

  final Color light;
  final Color dark;

  LinearGradient get gradient => LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [light, dark],
  );

  static const _styles = <String, GenreStyle>{
    'Sinhala': GenreStyle(Color(0xFFC8651B), Color(0xFF7A2E0E)),
    'Pop': GenreStyle(Color(0xFFD9577F), Color(0xFF8E2A50)),
    'Rock': GenreStyle(Color(0xFFB3392B), Color(0xFF5E1B14)),
    'Indie': GenreStyle(Color(0xFF3E8E8A), Color(0xFF1F4B53)),
    'Jazz': GenreStyle(Color(0xFF3B4F7A), Color(0xFF1C2742)),
    'Hip-Hop': GenreStyle(Color(0xFF6B4EA0), Color(0xFF33224F)),
    'Classical': GenreStyle(Color(0xFF8C7A4E), Color(0xFF4D4128)),
    'Country': GenreStyle(Color(0xFFB98A1F), Color(0xFF6E4E0E)),
    'Folk': GenreStyle(Color(0xFF6F8F4E), Color(0xFF35502A)),
    'Blues': GenreStyle(Color(0xFF2F6FA3), Color(0xFF173A5C)),
    'R&B': GenreStyle(Color(0xFF9A4F9E), Color(0xFF4E1F55)),
    'Metal': GenreStyle(Color(0xFF55555C), Color(0xFF1B1B1F)),
    'Reggae': GenreStyle(Color(0xFF4C9A52), Color(0xFF5E5A12)),
    'Soul': GenreStyle(Color(0xFFB5651D), Color(0xFF5B2D0A)),
    'Punk': GenreStyle(Color(0xFFC23B30), Color(0xFF2B2B2B)),
    'Electronic': GenreStyle(Color(0xFF2F8FB5), Color(0xFF1B3F8A)),
    'Latin': GenreStyle(Color(0xFFD9772B), Color(0xFF9C3326)),
    'Bollywood': GenreStyle(Color(0xFFC83F7F), Color(0xFFC7661F)),
    'K-Pop': GenreStyle(Color(0xFF9B5BD0), Color(0xFF3F5DC0)),
    'Gospel': GenreStyle(Color(0xFFC2A04A), Color(0xFF7A5A22)),
    'Other': GenreStyle(Color(0xFF7A6A5C), Color(0xFF3E342C)),
  };

  /// The style for [genre]; a neutral one for any name not on the list.
  static GenreStyle of(String genre) => _styles[genre] ?? _styles['Other']!;

  static Iterable<String> get names => _styles.keys;
}

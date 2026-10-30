import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../data/cached_cover_image.dart';
import 'genre_style.dart';

/// A song's art card: its real cover when it has one, and otherwise a card
/// made for it, in the colours of its genre. The made card is always underneath,
/// so while a cover loads (or if it cannot) the card is what shows.
class SongCover extends StatelessWidget {
  const SongCover({
    super.key,
    required this.seed,
    this.coverUrl,
    this.coverKey,
    this.genres = const [],
    this.size = 64,
    this.radius = 12,
  });

  /// The song's title; its first letter goes on the made card.
  final String seed;

  /// An https link to the cover image, or null.
  final String? coverUrl;

  /// What the cover is kept under on this phone (the song's id), so it is
  /// fetched once. Null means it is not kept.
  final String? coverKey;
  final List<String> genres;
  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) {
    final url = coverUrl;
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: SizedBox(
        width: size,
        height: size,
        child: Stack(
          fit: StackFit.expand,
          children: [
            ExcludeSemantics(
              child: CustomPaint(
                key: const ValueKey('artCard'),
                painter: _ArtCardPainter(
                  seed: seed,
                  style: genres.isEmpty ? null : GenreStyle.of(genres.first),
                  letterStyle: TextStyle(
                    fontFamily: ChordSyncTypography.displayFamily,
                    fontWeight: FontWeight.w700,
                    fontSize: size * 0.44,
                    color: const Color(0xD9FFFFFF),
                  ),
                ),
              ),
            ),
            if (url != null && Uri.tryParse(url)?.scheme == 'https')
              Image(
                image: ResizeImage(
                  CachedCoverImage(cacheKey: coverKey, url: url),
                  width: (size * 3).round(),
                ),
                key: const ValueKey('coverImage'),
                fit: BoxFit.cover,
                gaplessPlayback: true,
                excludeFromSemantics: true,
                // A cover that fades in over the made card.
                frameBuilder: (context, child, frame, sync) => AnimatedOpacity(
                  opacity: sync || frame != null ? 1 : 0,
                  duration: const Duration(milliseconds: 220),
                  child: child,
                ),
                // If it cannot load, the made card underneath simply stays.
                errorBuilder: (context, error, stack) =>
                    const SizedBox.shrink(),
              ),
          ],
        ),
      ),
    );
  }
}

/// The made card: two colours, five guitar strings, a soft sound hole and the
/// first letter.
class _ArtCardPainter extends CustomPainter {
  _ArtCardPainter({
    required this.seed,
    required this.style,
    required this.letterStyle,
  });

  final String seed;
  final GenreStyle? style;
  final TextStyle letterStyle;

  static const _plain = [
    GenreStyle(Color(0xFFB4663A), Color(0xFF6B2E14)),
    GenreStyle(Color(0xFFD98A33), Color(0xFF8A4A12)),
    GenreStyle(Color(0xFF8C6A3F), Color(0xFF4D3A22)),
    GenreStyle(Color(0xFF6E5A4B), Color(0xFF35291F)),
    GenreStyle(Color(0xFFA8502A), Color(0xFF5E2210)),
  ];

  GenreStyle get _style =>
      style ?? _plain[seed.codeUnits.fold(0, (a, b) => a + b) % _plain.length];

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    canvas.drawRect(rect, Paint()..shader = _style.gradient.createShader(rect));

    // A soft round "sound hole" low on the card.
    final hole = Offset(size.width * 0.62, size.height * 0.68);
    canvas.drawCircle(
      hole,
      size.width * 0.34,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = size.width * 0.018
        ..color = const Color(0x24FFFFFF),
    );
    canvas.drawCircle(
      hole,
      size.width * 0.2,
      Paint()..color = const Color(0x14000000),
    );

    // Five strings across the card.
    final string = Paint()
      ..strokeWidth = (size.width * 0.008).clamp(0.6, 1.6)
      ..color = const Color(0x38FFFFFF);
    for (var i = 0; i < 5; i++) {
      final y = size.height * (0.26 + i * 0.1);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), string);
    }

    final letter = seed.trim().isEmpty
        ? '♪'
        : String.fromCharCode(seed.trim().runes.first).toUpperCase();
    final text = TextPainter(
      text: TextSpan(text: letter, style: letterStyle),
      textDirection: TextDirection.ltr,
    )..layout();
    text.paint(
      canvas,
      Offset(size.width * 0.12, size.height * 0.88 - text.height),
    );
  }

  @override
  bool shouldRepaint(_ArtCardPainter old) =>
      old.seed != seed || old.style != style;
}

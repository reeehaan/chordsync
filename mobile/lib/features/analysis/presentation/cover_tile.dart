import 'dart:typed_data';

import 'package:flutter/material.dart';

/// The song's embedded cover art, or a coloured tile with its first letter
/// when it has none.
class CoverTile extends StatelessWidget {
  const CoverTile({
    super.key,
    required this.future,
    required this.seed,
    this.size = defaultSize,
    this.tone,
  });

  final Future<Uint8List?> future;
  final String seed;

  static const defaultSize = 64.0;

  /// The tile's width and height.
  final double size;

  /// The colour behind the first letter when there is no cover art; picked from
  /// the song's name when null.
  final Color? tone;

  // Warm tones from the Golden Hour theme, so a missing cover still fits.
  static const _tones = [
    Color(0xFFA8502A),
    Color(0xFFD98A33),
    Color(0xFF6E5A4B),
    Color(0xFF8C6A3F),
    Color(0xFFB4663A),
  ];

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: SizedBox(
        width: size,
        height: size,
        child: FutureBuilder<Uint8List?>(
          future: future,
          builder: (context, snapshot) {
            final bytes = snapshot.data;
            if (bytes == null) return _fallback(context);
            return Image.memory(
              bytes,
              key: const ValueKey('coverArt'),
              fit: BoxFit.cover,
              cacheWidth: (size * 3).round(),
              gaplessPlayback: true,
              errorBuilder: (context, error, stack) => _fallback(context),
            );
          },
        ),
      ),
    );
  }

  Widget _fallback(BuildContext context) {
    final letter = seed.trim().isEmpty
        ? '♪'
        : String.fromCharCode(seed.trim().runes.first).toUpperCase();
    final tone =
        this.tone ??
        _tones[seed.codeUnits.fold(0, (a, b) => a + b) % _tones.length];
    return ColoredBox(
      key: const ValueKey('coverFallback'),
      color: tone,
      child: Center(
        child: Text(
          letter,
          style:
              (size > 90
                      ? Theme.of(context).textTheme.displaySmall
                      : Theme.of(context).textTheme.headlineSmall)
                  ?.copyWith(color: Colors.white, fontWeight: FontWeight.w800),
        ),
      ),
    );
  }
}

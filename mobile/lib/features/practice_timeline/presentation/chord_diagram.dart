import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Standard voicings only — open shapes plus canonical movable E-shape and
/// A-shape barre chords for roots with no open-position fingering. Each root
/// also has the easiest shape (frets 0 to 9) for the 7, maj7, m7, sus2 and sus4
/// chords. Unknown labels never receive invented dots.
class ChordDiagram extends StatelessWidget {
  const ChordDiagram({
    super.key,
    required this.chord,
    this.foregroundColor,
    this.accentColor,
  });

  final String chord;
  final Color? foregroundColor;
  final Color? accentColor;

  // Low E to high e; -1 = muted, 0 = open, positive values = absolute fret.
  static const _voicings = <String, _ChordVoicing>{
    // Open-position shapes.
    'C': _ChordVoicing([-1, 3, 2, 0, 1, 0]),
    'G': _ChordVoicing([3, 2, 0, 0, 0, 3]),
    'Am': _ChordVoicing([-1, 0, 2, 2, 1, 0]),
    'Dm': _ChordVoicing([-1, -1, 0, 2, 3, 1]),
    'Em': _ChordVoicing([0, 2, 2, 0, 0, 0]),
    'D': _ChordVoicing([-1, -1, 0, 2, 3, 2]),
    'A': _ChordVoicing([-1, 0, 2, 2, 2, 0]),
    'E': _ChordVoicing([0, 2, 2, 1, 0, 0]),
    // Movable E-shape barre (root on the low E string).
    'F': _ChordVoicing([1, 3, 3, 2, 1, 1], baseFret: 1),
    'Fm': _ChordVoicing([1, 3, 3, 1, 1, 1], baseFret: 1),
    'F#': _ChordVoicing([2, 4, 4, 3, 2, 2], baseFret: 2),
    'F#m': _ChordVoicing([2, 4, 4, 2, 2, 2], baseFret: 2),
    'Gm': _ChordVoicing([3, 5, 5, 3, 3, 3], baseFret: 3),
    'G#': _ChordVoicing([4, 6, 6, 5, 4, 4], baseFret: 4),
    'G#m': _ChordVoicing([4, 6, 6, 4, 4, 4], baseFret: 4),
    // Movable A-shape barre (root on the A string, low E muted).
    'A#': _ChordVoicing([-1, 1, 3, 3, 3, 1], baseFret: 1),
    'A#m': _ChordVoicing([-1, 1, 3, 3, 2, 1], baseFret: 1),
    'B': _ChordVoicing([-1, 2, 4, 4, 4, 2], baseFret: 2),
    'Bm': _ChordVoicing([-1, 2, 4, 4, 3, 2], baseFret: 2),
    'C#': _ChordVoicing([-1, 4, 6, 6, 6, 4], baseFret: 4),
    'C#m': _ChordVoicing([-1, 4, 6, 6, 5, 4], baseFret: 4),
    'Cm': _ChordVoicing([-1, 3, 5, 5, 4, 3], baseFret: 3),
    'D#': _ChordVoicing([-1, 6, 8, 8, 8, 6], baseFret: 6),
    'D#m': _ChordVoicing([-1, 6, 8, 8, 7, 6], baseFret: 6),

    // Dominant 7th: the easiest shape for each root, in frets 0 to 9.
    'C7': _ChordVoicing([-1, 3, 2, 3, 1, 0]),
    'C#7': _ChordVoicing([-1, 4, 6, 4, 6, 4], baseFret: 4),
    'D7': _ChordVoicing([-1, -1, 0, 2, 1, 2]),
    'D#7': _ChordVoicing([-1, -1, 1, 3, 2, 3]),
    'E7': _ChordVoicing([0, 2, 0, 1, 0, 0]),
    'F7': _ChordVoicing([-1, -1, 3, 5, 4, 5], baseFret: 3),
    'F#7': _ChordVoicing([-1, -1, 4, 6, 5, 6], baseFret: 4),
    'G7': _ChordVoicing([3, 2, 0, 0, 0, 1]),
    'G#7': _ChordVoicing([-1, -1, 6, 8, 7, 8], baseFret: 6),
    'A7': _ChordVoicing([-1, 0, 2, 0, 2, 0]),
    'A#7': _ChordVoicing([-1, 1, 3, 1, 3, 1]),
    'B7': _ChordVoicing([-1, 2, 1, 2, 0, 2]),
    // Major 7th: the easiest shape for each root, in frets 0 to 9.
    'Cmaj7': _ChordVoicing([-1, 3, 2, 0, 0, 0]),
    'C#maj7': _ChordVoicing([-1, 4, 6, 5, 6, 4], baseFret: 4),
    'Dmaj7': _ChordVoicing([-1, -1, 0, 2, 2, 2]),
    'D#maj7': _ChordVoicing([-1, -1, 1, 3, 3, 3]),
    'Emaj7': _ChordVoicing([0, 2, 1, 1, 0, 0]),
    'Fmaj7': _ChordVoicing([-1, -1, 3, 2, 1, 0]),
    'F#maj7': _ChordVoicing([-1, -1, 4, 6, 6, 6], baseFret: 4),
    'Gmaj7': _ChordVoicing([3, 2, 0, 0, 0, 2]),
    'G#maj7': _ChordVoicing([-1, -1, 6, 8, 8, 8], baseFret: 6),
    'Amaj7': _ChordVoicing([-1, 0, 2, 1, 2, 0]),
    'A#maj7': _ChordVoicing([-1, 1, 3, 2, 3, 1]),
    'Bmaj7': _ChordVoicing([-1, 2, 4, 3, 4, 2], baseFret: 2),
    // Minor 7th: the easiest shape for each root, in frets 0 to 9.
    'Cm7': _ChordVoicing([-1, 3, 5, 3, 4, 3], baseFret: 3),
    'C#m7': _ChordVoicing([-1, 4, 6, 4, 5, 4], baseFret: 4),
    'Dm7': _ChordVoicing([-1, -1, 0, 2, 1, 1]),
    'D#m7': _ChordVoicing([-1, -1, 1, 3, 2, 2]),
    'Em7': _ChordVoicing([0, 2, 0, 0, 0, 0]),
    'Fm7': _ChordVoicing([1, 3, 1, 1, 1, 1]),
    'F#m7': _ChordVoicing([2, 4, 2, 2, 2, 2], baseFret: 2),
    'Gm7': _ChordVoicing([3, 5, 3, 3, 3, 3], baseFret: 3),
    'G#m7': _ChordVoicing([4, 6, 4, 4, 4, 4], baseFret: 4),
    'Am7': _ChordVoicing([-1, 0, 2, 0, 1, 0]),
    'A#m7': _ChordVoicing([-1, 1, 3, 1, 2, 1]),
    'Bm7': _ChordVoicing([-1, 2, 0, 2, 0, 2]),
    // Suspended 2nd: the easiest shape for each root, in frets 0 to 9.
    'Csus2': _ChordVoicing([-1, 3, 5, 5, 3, 3], baseFret: 3),
    'C#sus2': _ChordVoicing([-1, 4, 6, 6, 4, 4], baseFret: 4),
    'Dsus2': _ChordVoicing([-1, -1, 0, 2, 3, 0]),
    'D#sus2': _ChordVoicing([-1, -1, 1, 3, 4, 1]),
    'Esus2': _ChordVoicing([0, 2, 4, 4, 0, 0]),
    'Fsus2': _ChordVoicing([-1, -1, 3, 5, 6, 3], baseFret: 3),
    'F#sus2': _ChordVoicing([-1, -1, 4, 6, 7, 4], baseFret: 4),
    'Gsus2': _ChordVoicing([3, 0, 0, 0, 3, 3]),
    'G#sus2': _ChordVoicing([-1, -1, 6, 8, 9, 6], baseFret: 6),
    'Asus2': _ChordVoicing([-1, 0, 2, 2, 0, 0]),
    'A#sus2': _ChordVoicing([-1, 1, 3, 3, 1, 1]),
    'Bsus2': _ChordVoicing([-1, 2, 4, 4, 2, 2], baseFret: 2),
    // Suspended 4th: the easiest shape for each root, in frets 0 to 9.
    'Csus4': _ChordVoicing([-1, 3, 3, 0, 1, 1]),
    'C#sus4': _ChordVoicing([-1, 4, 6, 6, 7, 4], baseFret: 4),
    'Dsus4': _ChordVoicing([-1, -1, 0, 2, 3, 3]),
    'D#sus4': _ChordVoicing([-1, -1, 1, 3, 4, 4]),
    'Esus4': _ChordVoicing([0, 2, 2, 2, 0, 0]),
    'Fsus4': _ChordVoicing([-1, -1, 3, 5, 6, 6], baseFret: 3),
    'F#sus4': _ChordVoicing([-1, -1, 4, 6, 7, 7], baseFret: 4),
    'Gsus4': _ChordVoicing([3, 3, 0, 0, 1, 3]),
    'G#sus4': _ChordVoicing([-1, -1, 6, 8, 9, 9], baseFret: 6),
    'Asus4': _ChordVoicing([-1, 0, 2, 2, 3, 0]),
    'A#sus4': _ChordVoicing([-1, 1, 3, 3, 4, 1]),
    'Bsus4': _ChordVoicing([-1, 2, 4, 4, 5, 2], baseFret: 2),
  };

  /// The fret numbers of a chord's shape (low E to high e), or null when the
  /// chord has none. For tests that check every shape against its chord.
  @visibleForTesting
  static List<int>? fretsFor(String chord) => _voicings[chord]?.frets;

  @override
  Widget build(BuildContext context) {
    final voicing = _voicings[chord];
    if (chord == 'N') {
      return Semantics(
        label: 'Rest, no chord',
        child: const SizedBox(key: ValueKey('noChordFallback')),
      );
    }
    if (voicing == null) {
      return Text(
        chord,
        key: const ValueKey('unknownChordFallback'),
        style: Theme.of(context).textTheme.headlineSmall,
      );
    }
    return Semantics(
      label: voicing.baseFret == 1
          ? '$chord guitar chord diagram'
          : '$chord guitar chord diagram, barre at fret ${voicing.baseFret}',
      child: SizedBox(
        key: const ValueKey('chordDiagram'),
        width: 152,
        height: 142,
        child: CustomPaint(
          painter: _ChordDiagramPainter(
            voicing,
            foregroundColor: foregroundColor ?? ChordSyncColors.textSecondary,
            accentColor: accentColor ?? ChordSyncColors.brand,
          ),
        ),
      ),
    );
  }
}

/// A fingering for one chord. [frets] holds absolute fret numbers (-1 muted,
/// 0 open, positive = fret); [baseFret] is the lowest fret shown on the
/// diagram, i.e. where its barre sits for a movable shape (1 = at the nut).
class _ChordVoicing {
  const _ChordVoicing(this.frets, {this.baseFret = 1});

  final List<int> frets;
  final int baseFret;
}

class _ChordDiagramPainter extends CustomPainter {
  const _ChordDiagramPainter(
    this.voicing, {
    required this.foregroundColor,
    required this.accentColor,
  });

  final _ChordVoicing voicing;
  final Color foregroundColor;
  final Color accentColor;

  @override
  void paint(Canvas canvas, Size size) {
    final frets = voicing.frets;
    final baseFret = voicing.baseFret;
    final line = Paint()
      ..color = foregroundColor
      ..strokeWidth = 1.5;
    final dot = Paint()..color = accentColor;
    const left = 20.0;
    const top = 26.0;
    const stringGap = 22.0;
    const fretGap = 25.0;

    if (baseFret > 1) {
      final label = TextPainter(
        text: TextSpan(
          text: '${baseFret}fr',
          style: TextStyle(fontSize: 13, color: foregroundColor),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      label.paint(canvas, Offset(left - stringGap, top - 2));
    }

    final barredStrings = [
      for (var string = 0; string < 6; string++)
        if (frets[string] == baseFret) string,
    ];
    final hasBarre = barredStrings.length >= 2;

    for (var string = 0; string < 6; string++) {
      final x = left + string * stringGap;
      canvas.drawLine(Offset(x, top), Offset(x, top + fretGap * 4), line);
      final fret = frets[string];
      final isBarredHere = hasBarre && fret == baseFret;
      if (fret > 0 && !isBarredHere) {
        final row = fret - baseFret + 1;
        canvas.drawCircle(Offset(x, top + (row - 0.5) * fretGap), 7, dot);
      } else if (fret <= 0) {
        final marker = TextPainter(
          text: TextSpan(
            text: fret == 0 ? 'O' : '×',
            style: TextStyle(fontSize: 16, color: foregroundColor),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        marker.paint(canvas, Offset(x - marker.width / 2, 0));
      }
    }
    for (var fret = 0; fret <= 4; fret++) {
      final y = top + fret * fretGap;
      canvas.drawLine(Offset(left, y), Offset(left + stringGap * 5, y), line);
    }

    if (baseFret == 1) {
      final nut = Paint()
        ..color = foregroundColor
        ..strokeWidth = 4;
      canvas.drawLine(
        const Offset(left, top),
        const Offset(left + stringGap * 5, top),
        nut,
      );
    }

    if (hasBarre) {
      final barre = Paint()
        ..color = accentColor
        ..strokeWidth = 10
        ..strokeCap = StrokeCap.round;
      final y = top + 0.5 * fretGap;
      canvas.drawLine(
        Offset(left + barredStrings.first * stringGap, y),
        Offset(left + barredStrings.last * stringGap, y),
        barre,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ChordDiagramPainter oldDelegate) =>
      oldDelegate.voicing.frets != voicing.frets ||
      oldDelegate.voicing.baseFret != voicing.baseFret ||
      oldDelegate.foregroundColor != foregroundColor ||
      oldDelegate.accentColor != accentColor;
}

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';

/// Standard open voicings only. Unknown labels never receive invented dots.
class ChordDiagram extends StatelessWidget {
  const ChordDiagram({super.key, required this.chord});

  final String chord;

  // Low E to high e; -1 = muted, 0 = open, positive values = fret.
  static const _voicings = <String, List<int>>{
    'C': [-1, 3, 2, 0, 1, 0],
    'G': [3, 2, 0, 0, 0, 3],
    'Am': [-1, 0, 2, 2, 1, 0],
    'F': [1, 3, 3, 2, 1, 1],
    'Dm': [-1, -1, 0, 2, 3, 1],
    'Em': [0, 2, 2, 0, 0, 0],
    'D': [-1, -1, 0, 2, 3, 2],
    'A': [-1, 0, 2, 2, 2, 0],
    'E': [0, 2, 2, 1, 0, 0],
  };

  @override
  Widget build(BuildContext context) {
    final voicing = _voicings[chord];
    if (chord == 'N') {
      return Semantics(
        label: 'Rest, no chord',
        child: const Text('Rest / No chord', key: ValueKey('noChordFallback')),
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
      label: '$chord guitar chord diagram',
      child: SizedBox(
        key: const ValueKey('chordDiagram'),
        width: 152,
        height: 142,
        child: CustomPaint(painter: _ChordDiagramPainter(voicing)),
      ),
    );
  }
}

class _ChordDiagramPainter extends CustomPainter {
  const _ChordDiagramPainter(this.frets);

  final List<int> frets;

  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()
      ..color = ChordSyncColors.textSecondary
      ..strokeWidth = 1.5;
    final dot = Paint()..color = ChordSyncColors.brand;
    const left = 20.0;
    const top = 26.0;
    const stringGap = 22.0;
    const fretGap = 25.0;
    for (var string = 0; string < 6; string++) {
      final x = left + string * stringGap;
      canvas.drawLine(Offset(x, top), Offset(x, top + fretGap * 4), line);
      final fret = frets[string];
      if (fret > 0) {
        canvas.drawCircle(Offset(x, top + (fret - 0.5) * fretGap), 7, dot);
      } else {
        final marker = TextPainter(
          text: TextSpan(
            text: fret == 0 ? 'O' : '×',
            style: const TextStyle(
              fontSize: 16,
              color: ChordSyncColors.textPrimary,
            ),
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
    final nut = Paint()
      ..color = ChordSyncColors.brandDark
      ..strokeWidth = 4;
    canvas.drawLine(
      const Offset(left, top),
      const Offset(left + stringGap * 5, top),
      nut,
    );
  }

  @override
  bool shouldRepaint(covariant _ChordDiagramPainter oldDelegate) =>
      oldDelegate.frets != frets;
}

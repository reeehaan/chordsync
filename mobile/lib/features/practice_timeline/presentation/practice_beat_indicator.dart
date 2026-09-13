import 'package:flutter/material.dart';

class PracticeBeatIndicator extends StatelessWidget {
  const PracticeBeatIndicator({
    required this.beatNumber,
    required this.beatsPerBar,
    required this.isDownbeat,
    super.key,
  });

  final int? beatNumber;
  final int beatsPerBar;
  final bool isDownbeat;

  @override
  Widget build(BuildContext context) {
    final activeBeat = beatNumber;
    final semanticsLabel = activeBeat == null
        ? 'No active beat'
        : 'Beat $activeBeat of $beatsPerBar${isDownbeat ? ', downbeat' : ''}';

    return Semantics(
      key: const ValueKey('practiceBeatIndicator'),
      container: true,
      label: semanticsLabel,
      child: ExcludeSemantics(
        child: Wrap(
          alignment: WrapAlignment.center,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 12,
          runSpacing: 8,
          children: [
            for (var beat = 1; beat <= beatsPerBar; beat++)
              _BeatMarker(
                beat: beat,
                isActive: activeBeat == beat,
                isDownbeat: activeBeat == beat && isDownbeat,
              ),
          ],
        ),
      ),
    );
  }
}

class _BeatMarker extends StatelessWidget {
  const _BeatMarker({
    required this.beat,
    required this.isActive,
    required this.isDownbeat,
  });

  final int beat;
  final bool isActive;
  final bool isDownbeat;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final size = isDownbeat ? 24.0 : (isActive ? 20.0 : 14.0);
    final marker = Container(
      key: ValueKey('beatMarker$beat'),
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isActive ? colorScheme.primary : colorScheme.surface,
        border: Border.all(
          color: isActive ? colorScheme.primary : colorScheme.outline,
          width: isDownbeat ? 3 : 2,
        ),
      ),
    );

    if (!isActive) return marker;
    return KeyedSubtree(key: const ValueKey('activeBeatMarker'), child: marker);
  }
}

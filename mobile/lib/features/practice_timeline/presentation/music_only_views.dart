import 'package:flutter/material.dart';

import '../data/playback_state.dart';
import 'chord_diagram_strip.dart';
import 'practice_stage_colors.dart';

/// Shown in place of the chord strip while a MUSIC_ONLY region plays.
class MusicOnlyChordFocus extends StatelessWidget {
  const MusicOnlyChordFocus({super.key});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label: 'No chord to play',
      child: SizedBox(
        key: const ValueKey('musicOnlyChordFocus'),
        height: ChordDiagramStrip.compactHeight,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.music_note_rounded,
                size: 32,
                color: PracticeStageColors.amber,
              ),
              const SizedBox(height: 8),
              Text(
                'NO CHORD TO PLAY',
                key: const ValueKey('musicOnlyChordMessage'),
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: PracticeStageColors.textPrimary,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Beat-pulsing "MUSIC" banner shown in place of lyrics in MUSIC_ONLY regions.
class MusicOnlyLyrics extends StatelessWidget {
  const MusicOnlyLyrics({super.key, required this.state});

  final PlaybackState state;

  @override
  Widget build(BuildContext context) {
    const word = 'MUSIC';
    final beatProgress = state.beatProgress ?? 0.0;
    final revealedLetters = (beatProgress * word.length).floor() + 1;
    final pulse = 1.0 + (1.0 - beatProgress) * (state.isDownbeat ? 0.06 : 0.03);

    return Semantics(
      container: true,
      label: 'Music only section',
      value: '${((state.musicOnlyProgress ?? 0) * 100).round()} percent',
      child: Center(
        child: Transform.scale(
          scale: pulse,
          child: Row(
            key: const ValueKey('musicOnlyLyrics'),
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                '♪ ',
                style: TextStyle(
                  color: PracticeStageColors.amber,
                  fontSize: 30,
                ),
              ),
              for (var index = 0; index < word.length; index++)
                Text(
                  word[index],
                  key: ValueKey('musicLetter$index'),
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: index < revealedLetters
                        ? PracticeStageColors.amberBright
                        : PracticeStageColors.textFaint,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
              const Text(
                ' ♪',
                style: TextStyle(
                  color: PracticeStageColors.amber,
                  fontSize: 30,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

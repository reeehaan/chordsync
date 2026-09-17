import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';

/// Test-only, publication-safe sheet with 40 bars and 40 lyric lines.
SharedTimeline longSharedTimeline() => SharedTimeline(
  schemaVersion: 1,
  bpm: 60,
  beatsPerBar: 4,
  beatSource: 'synthetic-grid',
  lyricSource: 'synthetic-words',
  bars: [
    for (var bar = 0; bar < 40; bar++)
      TimelineBar(
        barNumber: bar + 1,
        startTime: bar * 4.0,
        endTime: (bar + 1) * 4.0,
        beats: [
          for (var beat = 0; beat < 4; beat++)
            TimelineEvent(
              time: bar * 4.0 + beat,
              beatNumber: beat + 1,
              isDownbeat: beat == 0,
              chord: const ['C', 'G', 'Am', 'F'][beat],
            ),
        ],
      ),
  ],
  lyrics: [
    for (var line = 0; line < 40; line++)
      LyricSegment(
        start: line * 4.0 + 0.5,
        end: line * 4.0 + 2.5,
        text: 'Practice line ${line + 1}',
        words: [
          LyricWord(
            start: line * 4.0 + 0.5,
            end: line * 4.0 + 1.5,
            text: 'Practice',
          ),
          LyricWord(
            start: line * 4.0 + 1.5,
            end: line * 4.0 + 2.5,
            text: 'line${line + 1}',
          ),
        ],
      ),
  ],
);

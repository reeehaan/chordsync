import 'shared_timeline.dart';

/// Display-only capo transposition. The analyzed/sounding chord remains
/// untouched; guitar shapes are moved down by the capo fret count.
class ChordTransposition {
  static const _sharpRoots = <String>[
    'C',
    'C#',
    'D',
    'D#',
    'E',
    'F',
    'F#',
    'G',
    'G#',
    'A',
    'A#',
    'B',
  ];

  static const _rootValues = <String, int>{
    'C': 0,
    'B#': 0,
    'C#': 1,
    'Db': 1,
    'D': 2,
    'D#': 3,
    'Eb': 3,
    'E': 4,
    'Fb': 4,
    'F': 5,
    'E#': 5,
    'F#': 6,
    'Gb': 6,
    'G': 7,
    'G#': 8,
    'Ab': 8,
    'A': 9,
    'A#': 10,
    'Bb': 10,
    'B': 11,
    'Cb': 11,
  };

  static final _rootPattern = RegExp(r'^([A-G](?:#|b)?)(.*)$');

  static String forCapo(String chord, int fret) {
    if (fret == 0 || chord == 'N' || chord == '—') return chord;
    final match = _rootPattern.firstMatch(chord);
    if (match == null) return chord;
    final root = _rootValues[match.group(1)];
    if (root == null) return chord;
    final shifted = (root - fret) % 12;
    return '${_sharpRoots[shifted]}${match.group(2)}';
  }

  static List<String> songChords(SharedTimeline timeline, {int capoFret = 0}) {
    final seen = <String>{};
    return [
      for (final bar in timeline.bars)
        for (final beat in bar.beats)
          if (beat.chord != 'N' && seen.add(beat.chord))
            forCapo(beat.chord, capoFret),
    ];
  }

  /// Chooses one song-wide capo position that favours common open shapes.
  /// It never substitutes an isolated chord, because that would change the
  /// harmony instead of preserving it.
  static int recommendedCapo(SharedTimeline timeline) {
    final chords = songChords(timeline);
    if (chords.isEmpty) return 0;
    var bestFret = 0;
    var bestScore = _score(chords, 0);
    for (var fret = 1; fret <= 6; fret++) {
      final score = _score(chords, fret);
      if (score < bestScore) {
        bestScore = score;
        bestFret = fret;
      }
    }
    return bestFret;
  }

  static int _score(List<String> chords, int fret) {
    const easy = {'C', 'G', 'D', 'A', 'E', 'Am', 'Em', 'Dm'};
    var score = fret; // Prefer the lowest capo when shapes are equally easy.
    for (final chord in chords) {
      final displayed = forCapo(chord, fret);
      if (easy.contains(displayed)) continue;
      score += displayed.contains('#') || displayed.contains('b') ? 6 : 3;
    }
    return score;
  }

  static SharedTimeline timelineForCapo(SharedTimeline timeline, int fret) {
    if (fret == 0) return timeline;
    return SharedTimeline(
      schemaVersion: timeline.schemaVersion,
      bpm: timeline.bpm,
      beatsPerBar: timeline.beatsPerBar,
      beatSource: timeline.beatSource,
      lyricSource: timeline.lyricSource,
      bars: [
        for (final bar in timeline.bars)
          TimelineBar(
            barNumber: bar.barNumber,
            startTime: bar.startTime,
            endTime: bar.endTime,
            beats: [
              for (final beat in bar.beats)
                TimelineEvent(
                  time: beat.time,
                  beatNumber: beat.beatNumber,
                  isDownbeat: beat.isDownbeat,
                  chord: forCapo(beat.chord, fret),
                ),
            ],
          ),
      ],
      lyrics: timeline.lyrics,
      practiceRegions: timeline.practiceRegions,
    );
  }
}

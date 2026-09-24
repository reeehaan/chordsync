import '../data/shared_timeline.dart';

class LyricChordWord {
  const LyricChordWord({
    required this.segmentIndex,
    required this.wordIndex,
    required this.word,
    required this.chordMarkers,
  });

  final int segmentIndex;
  final int wordIndex;
  final LyricWord word;
  final List<String> chordMarkers;

  String? get chordMarker => chordMarkers.isEmpty ? null : chordMarkers.first;
}

/// Maps timeline chord changes onto timed lyric words without altering either
/// source timeline. Live playback state remains authoritative.
abstract final class LyricChordMarkerMapper {
  static List<LyricChordWord> map(SharedTimeline timeline) {
    final words =
        <LyricChordWord>[
          for (
            var segmentIndex = 0;
            segmentIndex < timeline.lyrics.length;
            segmentIndex++
          )
            for (
              var wordIndex = 0;
              wordIndex < timeline.lyrics[segmentIndex].words.length;
              wordIndex++
            )
              LyricChordWord(
                segmentIndex: segmentIndex,
                wordIndex: wordIndex,
                word: timeline.lyrics[segmentIndex].words[wordIndex],
                chordMarkers: const [],
              ),
        ]..sort((left, right) {
          final byStart = left.word.start.compareTo(right.word.start);
          if (byStart != 0) return byStart;
          final bySegment = left.segmentIndex.compareTo(right.segmentIndex);
          return bySegment != 0
              ? bySegment
              : left.wordIndex.compareTo(right.wordIndex);
        });

    final events = [for (final bar in timeline.bars) ...bar.beats]
      ..sort((left, right) => left.time.compareTo(right.time));
    final changes = <TimelineEvent>[];
    String? previousChord;
    for (final event in events) {
      if (event.chord == previousChord) continue;
      previousChord = event.chord;
      changes.add(event);
    }

    final markers = <int, String>{};
    for (final change in changes) {
      final target = words.indexWhere(
        (entry) => entry.word.start >= change.time,
      );
      if (target == -1) continue;
      if (change.chord == 'N') {
        markers.remove(target);
      } else {
        // Several changes can occur before lyrics resume. Only the chord that
        // is active when the next real word begins is useful as its cue.
        markers[target] = change.chord;
      }
    }

    return [
      for (var index = 0; index < words.length; index++)
        LyricChordWord(
          segmentIndex: words[index].segmentIndex,
          wordIndex: words[index].wordIndex,
          word: words[index].word,
          chordMarkers: markers[index] == null ? const [] : [markers[index]!],
        ),
    ];
  }
}

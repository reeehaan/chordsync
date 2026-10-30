import 'shared_timeline.dart';

/// Removes chords too brief to be played: a chord that lasts one beat, or less
/// than [minimumSeconds], is a detector wobble or a passing chord nobody can
/// strum in time. Its beats go to the longer of the two chords around it, so
/// the chord before or after simply lasts a little longer.
///
/// The analysis already merges an interruption between two identical chords;
/// this also catches one between two different chords.
class ChordBlipFilter {
  const ChordBlipFilter._();

  /// A chord shorter than this many beats is a blip.
  static const minimumBeats = 2;

  /// A chord shorter than this is a blip, whatever the tempo. Some songs'
  /// beats are counted at double speed, where a flicker spans two beats.
  static const minimumSeconds = 0.7;

  static List<TimelineBar> apply(List<TimelineBar> bars) {
    final beats = [for (final bar in bars) ...bar.beats];
    if (beats.length < 3) return bars;
    final chords = [for (final beat in beats) beat.chord];

    // Each pass absorbs the shortest blip; neighbours that now match join up
    // and can themselves stop being blips, so repeat until none is left.
    while (true) {
      final runs = _runs(chords, beats);
      var shortest = -1;
      for (var index = 0; index < runs.length; index++) {
        final run = runs[index];
        if (!_isBlip(run, runs, index)) continue;
        if (shortest < 0 || run.seconds < runs[shortest].seconds) {
          shortest = index;
        }
      }
      if (shortest < 0) break;
      final blip = runs[shortest];
      final target = _neighbour(runs, shortest);
      for (var beat = blip.start; beat < blip.start + blip.count; beat++) {
        chords[beat] = target.chord;
      }
    }

    var next = 0;
    return [
      for (final bar in bars)
        TimelineBar(
          barNumber: bar.barNumber,
          startTime: bar.startTime,
          endTime: bar.endTime,
          beats: [
            for (final beat in bar.beats)
              chords[next++] == beat.chord
                  ? beat
                  : TimelineEvent(
                      time: beat.time,
                      beatNumber: beat.beatNumber,
                      isDownbeat: beat.isDownbeat,
                      chord: chords[next - 1],
                    ),
          ],
        ),
    ];
  }

  static bool _isBlip(_Run run, List<_Run> runs, int index) {
    if (run.chord == 'N') return false; // a rest is not a wobble
    final isEnd = index == 0 || index == runs.length - 1;
    if (isEnd) return false; // nothing on one side to give it to
    return _isBrief(run);
  }

  static bool _isBrief(_Run run) =>
      run.count < minimumBeats || run.seconds < minimumSeconds;

  /// The chord a blip's beats go to: the longer neighbour, and never a rest
  /// when the other side is a real chord.
  static _Run _neighbour(List<_Run> runs, int index) {
    final before = runs[index - 1];
    final after = runs[index + 1];
    if (before.chord == 'N' && after.chord != 'N') return after;
    if (after.chord == 'N' && before.chord != 'N') return before;
    return after.seconds > before.seconds ? after : before;
  }

  static List<_Run> _runs(List<String> chords, List<TimelineEvent> beats) {
    final runs = <_Run>[];
    var start = 0;
    for (var index = 1; index <= chords.length; index++) {
      if (index < chords.length && chords[index] == chords[start]) continue;
      final end = index < beats.length
          ? beats[index].time
          : beats[index - 1].time + _beatLength(beats);
      runs.add(
        _Run(
          chord: chords[start],
          start: start,
          count: index - start,
          seconds: end - beats[start].time,
        ),
      );
      start = index;
    }
    return runs;
  }

  static double _beatLength(List<TimelineEvent> beats) =>
      (beats.last.time - beats.first.time) / (beats.length - 1);
}

class _Run {
  const _Run({
    required this.chord,
    required this.start,
    required this.count,
    required this.seconds,
  });

  final String chord;
  final int start;
  final int count;
  final double seconds;
}

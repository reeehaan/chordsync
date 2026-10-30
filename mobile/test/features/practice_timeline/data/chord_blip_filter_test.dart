import 'package:chordsync/features/practice_timeline/data/chord_blip_filter.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

/// One bar per four beats, half a second apart (120 bpm).
List<TimelineBar> _bars(List<String> chords) {
  final bars = <TimelineBar>[];
  for (var start = 0; start < chords.length; start += 4) {
    final end = (start + 4).clamp(0, chords.length);
    bars.add(
      TimelineBar(
        barNumber: bars.length + 1,
        startTime: start * 0.5,
        endTime: end * 0.5,
        beats: [
          for (var index = start; index < end; index++)
            TimelineEvent(
              time: index * 0.5,
              beatNumber: index % 4 + 1,
              isDownbeat: index % 4 == 0,
              chord: chords[index],
            ),
        ],
      ),
    );
  }
  return bars;
}

List<String> _chords(List<TimelineBar> bars) => [
  for (final bar in bars)
    for (final beat in bar.beats) beat.chord,
];

String _run(String chord, int beats) => List.filled(beats, chord).join(' ');

List<String> _song(String spec) => spec.split(' ');

void main() {
  test('a one-beat chord between two different chords goes to the longer', () {
    final bars = _bars(_song('${_run('C', 4)} G ${_run('Am', 3)}'));

    expect(
      _chords(ChordBlipFilter.apply(bars)),
      _song('${_run('C', 5)} ${_run('Am', 3)}'),
    );
  });

  test('a one-beat chord between two matching chords disappears', () {
    final bars = _bars(_song('${_run('E', 4)} A ${_run('E', 4)}'));

    expect(_chords(ChordBlipFilter.apply(bars)), _song(_run('E', 9)));
  });

  test('a run of brief chords settles to the chord that holds', () {
    // C#m, a passing F#, then C#m again for a beat before A: all one C#m.
    final bars = _bars(_song('${_run('C#m', 6)} F# C#m ${_run('A', 4)}'));

    expect(
      _chords(ChordBlipFilter.apply(bars)),
      _song('${_run('C#m', 8)} ${_run('A', 4)}'),
    );
  });

  test('chords of two beats or more are left alone', () {
    final song = _song(
      '${_run('C', 4)} ${_run('G', 2)} ${_run('Am', 2)} ${_run('F', 4)}',
    );

    expect(_chords(ChordBlipFilter.apply(_bars(song))), song);
  });

  test('a two-beat chord under 0.7 s is a blip, as in a double-time song', () {
    // 0.3 s beats (200 bpm): two beats last 0.6 s.
    final bars = [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 3.6,
        beats: [
          for (var i = 0; i < 12; i++)
            TimelineEvent(
              time: i * 0.3,
              beatNumber: i % 4 + 1,
              isDownbeat: i % 4 == 0,
              chord: i < 4 ? 'C' : (i < 6 ? 'E' : 'G'),
            ),
        ],
      ),
    ];
    expect(_chords(ChordBlipFilter.apply(bars)).sublist(4, 6), ['G', 'G']);
  });

  test('a rest is kept, and a blip never turns into one', () {
    final song = _song('${_run('C', 4)} N N ${_run('G', 4)}');
    expect(_chords(ChordBlipFilter.apply(_bars(song))), song);

    final bars = _bars(_song('${_run('C', 4)} G ${_run('N', 4)}'));
    expect(_chords(ChordBlipFilter.apply(bars)).take(5).last, 'C');
  });

  test('the first and last chords are never removed', () {
    final song = _song('G ${_run('C', 4)} D');

    expect(_chords(ChordBlipFilter.apply(_bars(song))), song);
  });

  test('beat times and downbeats are unchanged', () {
    final original = _bars(_song('${_run('C', 4)} G ${_run('Am', 3)}'));
    final filtered = ChordBlipFilter.apply(original);

    expect(filtered.length, original.length);
    for (var bar = 0; bar < original.length; bar++) {
      for (var beat = 0; beat < original[bar].beats.length; beat++) {
        final before = original[bar].beats[beat];
        final after = filtered[bar].beats[beat];
        expect(after.time, before.time);
        expect(after.isDownbeat, before.isDownbeat);
        expect(after.beatNumber, before.beatNumber);
      }
    }
  });
}

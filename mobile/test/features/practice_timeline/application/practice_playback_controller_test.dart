import 'package:chordsync/features/practice_timeline/application/practice_playback_controller.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('starts at zero and updates state when the position changes', () {
    const timeline = SharedTimeline(
      schemaVersion: 1,
      bpm: 120,
      beatsPerBar: 4,
      beatSource: 'test',
      lyricSource: 'test',
      bars: [
        TimelineBar(
          barNumber: 1,
          startTime: 1,
          endTime: 3,
          beats: [
            TimelineEvent(time: 1, beatNumber: 1, isDownbeat: true, chord: 'C'),
            TimelineEvent(
              time: 2,
              beatNumber: 2,
              isDownbeat: false,
              chord: 'G',
            ),
          ],
        ),
      ],
      lyrics: [
        LyricSegment(
          start: 1,
          end: 3,
          text: 'Hello world',
          words: [
            LyricWord(start: 1, end: 1.5, text: 'Hello'),
            LyricWord(start: 2, end: 2.5, text: 'world'),
          ],
        ),
      ],
    );
    final controller = PracticePlaybackController(timeline);

    expect(controller.position, Duration.zero);
    expect(controller.state.playbackTime, 0);
    expect(controller.state.chord, 'N');

    controller.setPosition(const Duration(milliseconds: 1250));

    expect(controller.position, const Duration(milliseconds: 1250));
    expect(controller.state.playbackTime, 1.25);
    expect(controller.state.chord, 'C');
    expect(controller.state.beatNumber, 1);
    expect(controller.state.isDownbeat, isTrue);
    expect(controller.state.lyricWord, 'Hello');

    controller.setPosition(const Duration(milliseconds: 2250));
    expect(controller.state.chord, 'G');
    expect(controller.state.lyricWord, 'world');

    controller.setPosition(const Duration(milliseconds: 1750));
    expect(controller.state.chord, 'C');
    expect(controller.state.lyricWord, isNull);

    controller.setPosition(const Duration(milliseconds: -250));
    expect(controller.state.playbackTime, -0.25);
    expect(controller.state.chord, 'N');
    expect(controller.state.beatNumber, isNull);
  });
}

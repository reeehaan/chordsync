import 'package:chordsync/features/practice_timeline/application/practice_timeline_validator.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('accepts a single-beat partial final bar from real analysis', () {
    expect(
      () => PracticeTimelineValidator.validate(
        _timeline(
          bars: const [
            TimelineBar(
              barNumber: 1,
              startTime: 0,
              endTime: 4,
              beats: [
                TimelineEvent(
                  time: 0,
                  beatNumber: 1,
                  isDownbeat: true,
                  chord: 'C',
                ),
              ],
            ),
            TimelineBar(
              barNumber: 2,
              startTime: 4,
              endTime: 4,
              beats: [
                TimelineEvent(
                  time: 4,
                  beatNumber: 1,
                  isDownbeat: true,
                  chord: 'G',
                ),
              ],
            ),
          ],
        ),
      ),
      returnsNormally,
    );
  });

  test('still rejects a zero-duration bar before the final bar', () {
    expect(
      () => PracticeTimelineValidator.validate(
        _timeline(
          bars: const [
            TimelineBar(
              barNumber: 1,
              startTime: 0,
              endTime: 0,
              beats: [
                TimelineEvent(
                  time: 0,
                  beatNumber: 1,
                  isDownbeat: true,
                  chord: 'C',
                ),
              ],
            ),
            TimelineBar(
              barNumber: 2,
              startTime: 1,
              endTime: 2,
              beats: [
                TimelineEvent(
                  time: 1,
                  beatNumber: 1,
                  isDownbeat: true,
                  chord: 'G',
                ),
              ],
            ),
          ],
        ),
      ),
      throwsFormatException,
    );
  });
}

SharedTimeline _timeline({required List<TimelineBar> bars}) => SharedTimeline(
  schemaVersion: 1,
  bpm: 60,
  beatsPerBar: 4,
  beatSource: 'madmom',
  lyricSource: 'whisperx-small',
  bars: bars,
  lyrics: const [],
);

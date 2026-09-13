import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline_asset_loader.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('navigates using synthetic timeline bar boundaries', () async {
    final timeline = await SharedTimelineAssetLoader.load();

    expect(PlaybackLookup.previousBarStart(timeline, 0), isNull);
    expect(PlaybackLookup.nextBarStart(timeline, 0), 1);

    expect(PlaybackLookup.previousBarStart(timeline, 1), isNull);
    expect(PlaybackLookup.nextBarStart(timeline, 1), 5);

    expect(PlaybackLookup.previousBarStart(timeline, 3), 1);
    expect(PlaybackLookup.nextBarStart(timeline, 3), 5);

    expect(PlaybackLookup.previousBarStart(timeline, 5), 1);
    expect(PlaybackLookup.nextBarStart(timeline, 5), isNull);

    expect(PlaybackLookup.previousBarStart(timeline, 6), 5);
    expect(PlaybackLookup.nextBarStart(timeline, 6), isNull);

    expect(PlaybackLookup.previousBarStart(timeline, 9), 5);
    expect(PlaybackLookup.nextBarStart(timeline, 9), isNull);
  });

  test('uses explicit non-uniform bar starts instead of derived durations', () {
    const timeline = SharedTimeline(
      schemaVersion: 1,
      bpm: 120,
      beatsPerBar: 4,
      beatSource: 'test',
      lyricSource: 'test',
      bars: [
        TimelineBar(barNumber: 1, startTime: 0, endTime: 2, beats: []),
        TimelineBar(barNumber: 2, startTime: 2, endTime: 7, beats: []),
        TimelineBar(barNumber: 3, startTime: 7, endTime: 8, beats: []),
      ],
      lyrics: [],
    );

    expect(PlaybackLookup.previousBarStart(timeline, 4), 2);
    expect(PlaybackLookup.nextBarStart(timeline, 4), 7);
    expect(PlaybackLookup.previousBarStart(timeline, 7), 2);
  });
}

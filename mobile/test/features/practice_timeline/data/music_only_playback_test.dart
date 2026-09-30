import 'package:chordsync/features/practice_timeline/application/practice_playback_controller.dart';
import 'package:chordsync/features/practice_timeline/application/practice_timeline_validator.dart';
import 'package:chordsync/features/practice_timeline/data/playback_lookup.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses optional music-only regions and keeps old JSON compatible', () {
    final withRegion = SharedTimeline.fromJson(
      _json(
        practiceRegions: [
          {'start': 2, 'end': 4, 'mode': 'music_only'},
        ],
      ),
    );
    final withoutRegion = SharedTimeline.fromJson(_json());

    expect(withRegion.practiceRegions, hasLength(1));
    expect(withRegion.practiceRegions.single.mode, PracticeMode.musicOnly);
    expect(withoutRegion.practiceRegions, isEmpty);
    expect(
      () => SharedTimeline.fromJson(
        _json(
          practiceRegions: [
            {'start': 2, 'end': 4, 'mode': 'uncertain'},
          ],
        ),
      ),
      throwsFormatException,
    );
  });

  test(
    'resolves start-inclusive and end-exclusive boundaries and progress',
    () {
      final timeline = _timeline();

      expect(
        PlaybackLookup.playbackState(timeline, 1.999).isMusicOnly,
        isFalse,
      );
      final start = PlaybackLookup.playbackState(timeline, 2);
      expect(start.isMusicOnly, isTrue);
      expect(start.musicOnlyProgress, 0);
      expect(PlaybackLookup.playbackState(timeline, 3).musicOnlyProgress, 0.5);
      expect(PlaybackLookup.playbackState(timeline, 3.999).isMusicOnly, isTrue);
      expect(PlaybackLookup.playbackState(timeline, 4).isMusicOnly, isFalse);
      expect(
        PlaybackLookup.playbackState(timeline, 4.001).isMusicOnly,
        isFalse,
      );
    },
  );

  test('controller seeks directly into and out of music-only state', () {
    final controller = PracticePlaybackController(_timeline());

    controller.setPosition(const Duration(milliseconds: 2500));
    expect(controller.state.isMusicOnly, isTrue);
    expect(controller.state.beatNumber, 3);

    controller.setPosition(const Duration(milliseconds: 4500));
    expect(controller.state.isMusicOnly, isFalse);
    expect(controller.state.chord, 'F');
    expect(controller.state.lyricWord, 'Back');
  });

  test('supports music-only at song beginning and between lyric blocks', () {
    final timeline = _timeline(
      practiceRegions: const [
        PracticeRegion(start: 0, end: 1, mode: PracticeMode.musicOnly),
        PracticeRegion(start: 2, end: 4, mode: PracticeMode.musicOnly),
      ],
    );

    expect(PlaybackLookup.playbackState(timeline, 0).isMusicOnly, isTrue);
    expect(PlaybackLookup.playbackState(timeline, 1).isMusicOnly, isFalse);
    expect(PlaybackLookup.playbackState(timeline, 3).lyricWord, isNull);
    expect(PlaybackLookup.playbackState(timeline, 4.5).lyricWord, 'Back');
    expect(() => PracticeTimelineValidator.validate(timeline), returnsNormally);
  });

  test('validator rejects overlapping and invalid practice regions', () {
    final overlapping = _timeline(
      practiceRegions: const [
        PracticeRegion(start: 1, end: 3, mode: PracticeMode.musicOnly),
        PracticeRegion(start: 2, end: 4, mode: PracticeMode.musicOnly),
      ],
    );
    final pastEnd = _timeline(
      practiceRegions: const [
        PracticeRegion(start: 7, end: 9, mode: PracticeMode.musicOnly),
      ],
    );

    expect(
      () => PracticeTimelineValidator.validate(overlapping),
      throwsFormatException,
    );
    expect(
      () => PracticeTimelineValidator.validate(pastEnd),
      throwsFormatException,
    );
  });
}

SharedTimeline _timeline({
  List<PracticeRegion> practiceRegions = const [
    PracticeRegion(start: 2, end: 4, mode: PracticeMode.musicOnly),
  ],
}) => SharedTimeline(
  schemaVersion: 1,
  bpm: 60,
  beatsPerBar: 4,
  beatSource: 'synthetic',
  lyricSource: 'synthetic',
  bars: const [
    TimelineBar(
      barNumber: 1,
      startTime: 0,
      endTime: 4,
      beats: [
        TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
        TimelineEvent(time: 1, beatNumber: 2, isDownbeat: false, chord: 'G'),
        TimelineEvent(time: 2, beatNumber: 3, isDownbeat: false, chord: 'Am'),
        TimelineEvent(time: 3, beatNumber: 4, isDownbeat: false, chord: 'F'),
      ],
    ),
    TimelineBar(
      barNumber: 2,
      startTime: 4,
      endTime: 8,
      beats: [
        TimelineEvent(time: 4, beatNumber: 1, isDownbeat: true, chord: 'F'),
        TimelineEvent(time: 5, beatNumber: 2, isDownbeat: false, chord: 'G'),
        TimelineEvent(time: 6, beatNumber: 3, isDownbeat: false, chord: 'C'),
        TimelineEvent(time: 7, beatNumber: 4, isDownbeat: false, chord: 'C'),
      ],
    ),
  ],
  lyrics: const [
    LyricSegment(
      start: 0.5,
      end: 1.5,
      text: 'Before',
      words: [LyricWord(start: 0.5, end: 1.5, text: 'Before')],
    ),
    LyricSegment(
      start: 4,
      end: 5,
      text: 'Back',
      words: [LyricWord(start: 4, end: 5, text: 'Back')],
    ),
  ],
  practiceRegions: practiceRegions,
);

Map<String, dynamic> _json({List<Map<String, dynamic>>? practiceRegions}) {
  final json = <String, dynamic>{
    'schema_version': 1,
    'bpm': 60,
    'beats_per_bar': 4,
    'beat_source': 'synthetic',
    'lyric_source': 'synthetic',
    'bars': [
      {
        'bar_number': 1,
        'start_time': 0,
        'end_time': 8,
        'beats': [
          {'time': 0, 'beat_number': 1, 'is_downbeat': true, 'chord': 'C'},
        ],
      },
    ],
    'lyrics': <Map<String, dynamic>>[],
  };
  if (practiceRegions != null) {
    json['practice_regions'] = practiceRegions;
  }
  return json;
}

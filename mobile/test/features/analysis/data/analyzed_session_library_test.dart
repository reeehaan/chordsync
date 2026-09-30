import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory documents;
  late File audio;
  late LocalAnalyzedSessionLibrary library;

  setUp(() {
    documents = Directory.systemTemp.createTempSync('chordsync-library-test-');
    audio = File('${documents.path}/song.mp3')..writeAsBytesSync([1, 2, 3]);
    library = LocalAnalyzedSessionLibrary(
      documentsDirectory: () async => documents,
    );
  });

  tearDown(() => documents.deleteSync(recursive: true));

  test('persists and restores a completed practice session', () async {
    final session = _session(audio, jobId: 'job-one', title: 'Practice song');

    await library.save(session);
    final restored = await library.load();

    expect(restored, hasLength(1));
    expect(restored.single.title, 'Practice song');
    expect(restored.single.job.jobId, 'job-one');
    expect(restored.single.audioFile.path, audio.path);
    expect(restored.single.timeline.bpm, 90);
    expect(restored.single.timeline.totalBeatCount, 1);
    expect(restored.single.timeline.totalLyricWordCount, 1);
    expect(restored.single.timeline.practiceRegions, hasLength(1));
    expect(restored.single.timeline.practiceRegions.single.start, 2);
    expect(restored.single.timeline.practiceRegions.single.end, 4);
    expect(
      restored.single.timeline.practiceRegions.single.mode,
      PracticeMode.musicOnly,
    );
  });

  test('loads an old saved session without practice_regions', () async {
    final session = _session(audio, jobId: 'old-job', title: 'Old session');
    await library.save(session);
    final index = File('${documents.path}/analyzed_sessions/sessions.json');
    final contents = await index.readAsString();
    await index.writeAsString(
      contents.replaceFirst(
        ',"practice_regions":[{"start":2.0,"end":4.0,"mode":"music_only"}]',
        '',
      ),
    );

    final restored = await library.load();

    expect(restored, hasLength(1));
    expect(restored.single.timeline.practiceRegions, isEmpty);
  });

  test('replaces the same job and omits sessions with missing audio', () async {
    await library.save(_session(audio, jobId: 'job-one', title: 'Old title'));
    await library.save(_session(audio, jobId: 'job-one', title: 'New title'));

    expect((await library.load()).single.title, 'New title');

    audio.deleteSync();
    expect(await library.load(), isEmpty);
  });

  test('does not overwrite a corrupted session index', () async {
    final index = File('${documents.path}/analyzed_sessions/sessions.json')
      ..createSync(recursive: true);
    await index.writeAsString('{not valid json');

    expect(await library.load(), isEmpty);
    await expectLater(
      library.save(_session(audio, jobId: 'job-one', title: 'New title')),
      throwsA(isA<AnalyzedSessionLibraryException>()),
    );
    expect(await index.readAsString(), '{not valid json');
  });
}

AnalyzedPracticeSession _session(
  File audio, {
  required String jobId,
  required String title,
}) => AnalyzedPracticeSession(
  title: title,
  audioFile: audio,
  job: AnalysisJob(
    jobId: jobId,
    status: AnalysisJobStatus.completed,
    createdAt: DateTime.utc(2026, 9, 21),
    updatedAt: DateTime.utc(2026, 9, 21),
    error: null,
    resultAvailable: true,
  ),
  timeline: const SharedTimeline(
    schemaVersion: 1,
    bpm: 90,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'test',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 1,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
        ],
      ),
    ],
    lyrics: [
      LyricSegment(
        start: 0,
        end: 1,
        text: 'Hello',
        words: [LyricWord(start: 0, end: 1, text: 'Hello')],
      ),
    ],
    practiceRegions: [
      PracticeRegion(start: 2, end: 4, mode: PracticeMode.musicOnly),
    ],
  ),
);

import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/practice_timeline/application/practice_session_factory.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:chordsync/features/practice_timeline/presentation/chord_diagram.dart';
import 'package:chordsync/features/practice_timeline/presentation/practice_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../fakes/fake_practice_audio_player.dart';

void main() {
  testWidgets(
    'seeking into and out of music-only swaps the full practice view',
    (tester) async {
      final directory = Directory.systemTemp.createTempSync(
        'music-only-screen-',
      );
      addTearDown(() => directory.deleteSync(recursive: true));
      final audio = File('${directory.path}/synthetic.wav')
        ..writeAsBytesSync([1]);
      final player = FakePracticeAudioPlayer();
      final session = AnalyzedPracticeSession(
        title: 'Synthetic music-only practice',
        job: AnalysisJob(
          jobId: 'music-only',
          status: AnalysisJobStatus.completed,
          createdAt: DateTime.utc(2026),
          updatedAt: DateTime.utc(2026),
          error: null,
          resultAvailable: true,
        ),
        audioFile: audio,
        timeline: _timeline,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: PracticeScreen(
            analyzedSession: session,
            sessionFactory: PracticeSessionFactory(
              audioPlayerFactory: (_) => player,
            ),
          ),
        ),
      );
      await _waitForLoad(tester);

      expect(find.byType(ChordDiagram), findsWidgets);
      expect(find.byKey(const ValueKey('musicOnlyChordMessage')), findsNothing);

      await _seek(tester, 2);
      expect(find.text('NO CHORD TO PLAY'), findsOneWidget);
      expect(find.byKey(const ValueKey('musicOnlyLyrics')), findsOneWidget);
      expect(find.byType(ChordDiagram), findsNothing);
      expect(find.byKey(const ValueKey('chordProgressBar')), findsNothing);
      expect(find.byKey(const ValueKey('sheetWord0.5')), findsNothing);
      expect(find.byKey(const ValueKey('sheetWord4.0')), findsNothing);
      expect(find.text('Music only'), findsNothing); // the bar label is gone
      expect(find.byType(Slider), findsOneWidget);
      expect(find.byTooltip('Play'), findsOneWidget);

      final firstAtStart = tester.widget<Text>(
        find.byKey(const ValueKey('musicLetter0')),
      );
      final lastAtStart = tester.widget<Text>(
        find.byKey(const ValueKey('musicLetter4')),
      );
      expect(firstAtStart.style?.color, isNot(lastAtStart.style?.color));

      await _seek(tester, 2.75);
      final middleLetter = tester.widget<Text>(
        find.byKey(const ValueKey('musicLetter2')),
      );
      expect(middleLetter.style?.color, firstAtStart.style?.color);

      await _seek(tester, 4);
      expect(find.byKey(const ValueKey('musicOnlyLyrics')), findsNothing);
      expect(find.text('NO CHORD TO PLAY'), findsNothing);
      expect(find.byType(ChordDiagram), findsWidgets);
      expect(find.byKey(const ValueKey('chordProgressBar')), findsOneWidget);
      expect(find.byKey(const ValueKey('sheetWord4.0')), findsOneWidget);
      expect(
        tester
            .widget<Text>(find.byKey(const ValueKey('currentChordValue')))
            .data,
        'F',
      );
    },
  );
}

Future<void> _waitForLoad(WidgetTester tester) async {
  for (var attempt = 0; attempt < 100; attempt++) {
    await tester.pump(const Duration(milliseconds: 10));
    if (find.byType(Slider).evaluate().isNotEmpty) return;
  }
  fail('Practice screen did not load.');
}

Future<void> _seek(WidgetTester tester, double seconds) async {
  tester.widget<Slider>(find.byType(Slider)).onChanged!(seconds);
  await tester.pumpAndSettle();
}

const _timeline = SharedTimeline(
  schemaVersion: 1,
  bpm: 60,
  beatsPerBar: 4,
  beatSource: 'synthetic',
  lyricSource: 'synthetic',
  bars: [
    TimelineBar(
      barNumber: 1,
      startTime: 0,
      endTime: 4,
      beats: [
        TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
        TimelineEvent(time: 1, beatNumber: 2, isDownbeat: false, chord: 'G'),
        TimelineEvent(time: 2, beatNumber: 3, isDownbeat: false, chord: 'Am'),
        TimelineEvent(time: 3, beatNumber: 4, isDownbeat: false, chord: 'Dm'),
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
  lyrics: [
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
  practiceRegions: [
    PracticeRegion(start: 2, end: 4, mode: PracticeMode.musicOnly),
  ],
);

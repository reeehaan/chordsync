import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/presentation/library_home.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late Directory directory;
  late List<AnalyzedPracticeSession> sessions;
  AnalyzedPracticeSession? opened;

  setUp(() {
    directory = Directory.systemTemp.createTempSync('chordsync-library-home-');
    File('${directory.path}/a.mp3').writeAsBytesSync([1]);
    sessions = [
      _session(
        directory,
        id: 'sudu',
        title: 'Sudu Gawuma - La Signore - Spotimate.app',
      ),
      _session(directory, id: 'tum', title: 'Tum Hi Ho - Arijit Singh'),
      _session(directory, id: 'plain', title: 'safe_song'),
    ];
    opened = null;
  });

  tearDown(() => directory.deleteSync(recursive: true));

  Future<void> pumpLibrary(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: LibraryHome(
            sessions: sessions,
            onOpen: (session) => opened = session,
            onAddSong: () {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('cards show the song name and artist, not the file name', (
    tester,
  ) async {
    await pumpLibrary(tester);

    expect(find.text('Sudu Gawuma'), findsOneWidget);
    expect(find.text('La Signore'), findsOneWidget);
    expect(find.textContaining('Spotimate'), findsNothing);
    // A name with no artist stays whole.
    expect(find.text('safe_song'), findsOneWidget);
    // Length and tempo, then the first chords.
    expect(find.text('1:05 · 90 BPM'), findsNWidgets(3));
    expect(find.text('C'), findsNWidgets(3));
    expect(find.text('G'), findsNWidgets(3));
    // No embedded art in these files: a coloured tile with the first letter.
    expect(find.byKey(const ValueKey('coverFallback')), findsNWidgets(3));
    expect(find.text('S'), findsNWidgets(2));
  });

  testWidgets('search filters by title or artist, in any word order', (
    tester,
  ) async {
    await pumpLibrary(tester);
    final field = find.byKey(const ValueKey('songSearchField'));

    await tester.enterText(field, 'arijit');
    await tester.pump();
    expect(find.text('Tum Hi Ho'), findsOneWidget);
    expect(find.text('Sudu Gawuma'), findsNothing);
    expect(find.text('1 of 3'), findsOneWidget);

    await tester.enterText(field, 'signore SUDU');
    await tester.pump();
    expect(find.text('Sudu Gawuma'), findsOneWidget);
    expect(find.text('Tum Hi Ho'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('savedPractice-sudu')));
    expect(opened?.job.jobId, 'sudu');
  });

  testWidgets('a search with no result says so, and clearing restores all', (
    tester,
  ) async {
    await pumpLibrary(tester);
    final field = find.byKey(const ValueKey('songSearchField'));

    await tester.enterText(field, 'zzz');
    await tester.pump();
    expect(find.byKey(const ValueKey('noSongMatches')), findsOneWidget);
    expect(find.text('No songs match "zzz".'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('clearSongSearch')));
    await tester.pump();
    expect(find.byKey(const ValueKey('noSongMatches')), findsNothing);
    expect(find.text('3 saved'), findsOneWidget);
  });

  testWidgets('tapping outside the search box puts the keyboard away', (
    tester,
  ) async {
    await pumpLibrary(tester);
    final field = find.byKey(const ValueKey('songSearchField'));

    await tester.tap(field);
    await tester.pump();
    expect(tester.testTextInput.isVisible, isTrue);

    // A tap on the page itself, not on any control.
    await tester.tap(find.text('Home'));
    await tester.pump();
    expect(tester.testTextInput.isVisible, isFalse);
    expect(
      FocusManager.instance.primaryFocus?.context?.widget,
      isNot(isA<EditableText>()),
    );
  });

  testWidgets('the search key and scrolling the list also close it', (
    tester,
  ) async {
    await pumpLibrary(tester);
    final field = find.byKey(const ValueKey('songSearchField'));

    await tester.tap(field);
    await tester.pump();
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();
    expect(tester.testTextInput.isVisible, isFalse);

    await tester.tap(field);
    await tester.pump();
    expect(tester.testTextInput.isVisible, isTrue);
    await tester.drag(find.byType(ListView), const Offset(0, -120));
    await tester.pump();
    expect(tester.testTextInput.isVisible, isFalse);
  });

  testWidgets('a tap on a song card still opens it', (tester) async {
    await pumpLibrary(tester);
    await tester.tap(find.byKey(const ValueKey('songSearchField')));
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('savedPractice-tum')));
    await tester.pump();

    expect(opened?.job.jobId, 'tum');
  });

  testWidgets('no search box before there is a song', (tester) async {
    sessions = [];
    await pumpLibrary(tester);
    expect(find.byKey(const ValueKey('songSearchField')), findsNothing);
    expect(find.text('No analyzed songs yet'), findsOneWidget);
  });
}

AnalyzedPracticeSession _session(
  Directory directory, {
  required String id,
  required String title,
}) => AnalyzedPracticeSession(
  title: title,
  job: AnalysisJob(
    jobId: id,
    status: AnalysisJobStatus.completed,
    createdAt: DateTime.utc(2026, 10, 23),
    updatedAt: DateTime.utc(2026, 10, 23),
    error: null,
    resultAvailable: true,
  ),
  audioFile: File('${directory.path}/a.mp3'),
  timeline: const SharedTimeline(
    schemaVersion: 1,
    bpm: 90,
    beatsPerBar: 4,
    beatSource: 'test',
    lyricSource: 'none',
    bars: [
      TimelineBar(
        barNumber: 1,
        startTime: 0,
        endTime: 65,
        beats: [
          TimelineEvent(time: 0, beatNumber: 1, isDownbeat: true, chord: 'C'),
          TimelineEvent(time: 1, beatNumber: 2, isDownbeat: false, chord: 'G'),
          TimelineEvent(time: 2, beatNumber: 3, isDownbeat: false, chord: 'N'),
        ],
      ),
    ],
    lyrics: [],
  ),
);

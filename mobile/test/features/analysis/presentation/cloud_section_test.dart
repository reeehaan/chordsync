import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/application/cloud_library_controller.dart';
import 'package:chordsync/features/analysis/application/cloud_library_service.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/presentation/library_home.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _sudu = '11111111-aaaa-4bbb-8ccc-000000000001';
const _tum = '22222222-aaaa-4bbb-8ccc-000000000002';
const _lemon = '33333333-aaaa-4bbb-8ccc-000000000003';

class _Api implements CloudLibraryApi {
  Object? listError;
  List<CloudSong> songs = [
    _song(_sudu, 'Sudu Gawuma - La Signore'),
    _song(_tum, 'Tum Hi Ho - Arijit Singh'),
    _song(_lemon, 'Lemon - Kenshi Yonezu'),
  ];
  int listCalls = 0;

  @override
  Future<List<CloudSong>> listSongs() async {
    listCalls++;
    if (listError != null) throw listError!;
    return songs;
  }

  @override
  Future<SharedTimeline> getSongTimeline(String jobId) async => _timeline();

  @override
  Future<CloudAudioLink> getSongAudioLink(String jobId) async =>
      const CloudAudioLink(
        url: 'https://bucket.invalid/a.mp3?sig=1',
        expiresInSeconds: 600,
        fileType: 'mp3',
      );
}

class _Downloader implements AudioDownloader {
  Completer<void>? gate;
  Object? error;

  @override
  Future<void> download(
    String url,
    String destination, {
    void Function(double progress)? onProgress,
  }) async {
    onProgress?.call(0.4);
    await gate?.future;
    if (error != null) throw error!;
    await File(destination).writeAsBytes([1]);
  }
}

void main() {
  late Directory documents;
  late _Api api;
  late _Downloader downloader;
  late CloudLibraryController cloud;
  var sessions = <AnalyzedPracticeSession>[];

  setUp(() {
    documents = Directory.systemTemp.createTempSync('chordsync-cloud-ui-');
    api = _Api();
    downloader = _Downloader();
    sessions = [];
    cloud = CloudLibraryController(
      service: CloudLibraryService(
        api: api,
        library: LocalAnalyzedSessionLibrary(
          documentsDirectory: () async => documents,
        ),
        downloader: downloader,
        documentsDirectory: () async => documents,
      ),
    );
  });

  tearDown(() {
    cloud.dispose();
    documents.deleteSync(recursive: true);
  });

  /// The download mixes real file work with the test clock, so alternate:
  /// give the files real time, then let the widgets run what they now have.
  Future<void> letFilesSettle(WidgetTester tester) async {
    for (var step = 0; step < 30; step++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
      await tester.pump(const Duration(milliseconds: 20));
    }
  }

  Future<void> pump(WidgetTester tester, {bool withCloud = true}) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) {
              cloud.onDownloaded = (session) =>
                  setState(() => sessions = [...sessions, session]);
              return LibraryHome(
                sessions: sessions,
                onOpen: (_) {},
                onAddSong: () {},
                cloud: withCloud ? cloud : null,
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('lists the cloud songs under "From the cloud"', (tester) async {
    await pump(tester);

    expect(api.listCalls, 1);
    expect(find.text('From the cloud'), findsOneWidget);
    expect(find.text('Sudu Gawuma'), findsOneWidget);
    expect(find.text('La Signore'), findsOneWidget);
    expect(find.text('3:36'), findsNWidgets(3));
    expect(find.byKey(ValueKey('downloadCloudSong-$_sudu')), findsOneWidget);
  });

  testWidgets('songs already on the phone are not offered again', (
    tester,
  ) async {
    sessions = [_session(documents, _tum)];
    await pump(tester);

    expect(find.byKey(ValueKey('cloudSong-$_tum')), findsNothing);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsOneWidget);
    // Only the saved copy of that song is on screen.
    expect(find.text('Tum Hi Ho'), findsOneWidget);
  });

  testWidgets('downloading shows progress, then the song moves to the phone', (
    tester,
  ) async {
    downloader.gate = Completer<void>();
    await pump(tester);

    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(ValueKey('cloudProgress-$_sudu')), findsOneWidget);
    expect(find.byKey(ValueKey('downloadCloudSong-$_sudu')), findsNothing);

    downloader.gate!.complete();
    await letFilesSettle(tester);

    expect(sessions.single.job.jobId, _sudu);
    expect(sessions.single.audioFile.existsSync(), isTrue);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsNothing);
    expect(find.byKey(ValueKey('savedPractice-$_sudu')), findsOneWidget);
  });

  testWidgets('a failed download says so and offers a retry', (tester) async {
    downloader.error = const SocketException('offline');
    await pump(tester);

    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await letFilesSettle(tester);

    expect(find.byKey(ValueKey('cloudError-$_sudu')), findsOneWidget);
    expect(sessions, isEmpty);
    // The song is still offered, now as Retry.
    expect(find.text('Retry'), findsOneWidget);

    downloader.error = null;
    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await letFilesSettle(tester);
    expect(sessions.single.job.jobId, _sudu);
  });

  testWidgets('an unreachable cloud shows a message and can be retried', (
    tester,
  ) async {
    api.listError = const SocketException('offline');
    await pump(tester);
    expect(find.byKey(const ValueKey('cloudFailed')), findsOneWidget);

    api.listError = null;
    await tester.tap(find.byKey(const ValueKey('refreshCloudSongs')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('cloudFailed')), findsNothing);
    expect(find.text('Lemon'), findsOneWidget);
  });

  testWidgets('search also filters the cloud songs', (tester) async {
    sessions = [_session(documents, _tum)];
    await pump(tester);

    await tester.enterText(
      find.byKey(const ValueKey('songSearchField')),
      'kenshi',
    );
    await tester.pump();
    expect(find.byKey(ValueKey('cloudSong-$_lemon')), findsOneWidget);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('songSearchField')),
      'zzz',
    );
    await tester.pump();
    expect(find.text('No cloud songs match your search.'), findsOneWidget);
  });

  testWidgets('with nothing in the cloud and nothing on the phone', (
    tester,
  ) async {
    api.songs = [];
    await pump(tester);

    expect(find.text('No analyzed songs yet'), findsOneWidget);
    expect(find.byKey(const ValueKey('cloudEmpty')), findsOneWidget);
  });

  testWidgets('no cloud section when the app has no cloud', (tester) async {
    await pump(tester, withCloud: false);

    expect(find.text('From the cloud'), findsNothing);
    expect(api.listCalls, 0);
  });
}

CloudSong _song(String id, String title) => CloudSong(
  jobId: id,
  title: title,
  createdAt: DateTime.utc(2026, 10, 23),
  durationSeconds: 215.5,
);

SharedTimeline _timeline() => const SharedTimeline(
  schemaVersion: 1,
  bpm: 88,
  beatsPerBar: 4,
  beatSource: 'test',
  lyricSource: 'test',
  bars: [],
  lyrics: [],
);

AnalyzedPracticeSession _session(Directory directory, String id) {
  File('${directory.path}/$id.mp3').writeAsBytesSync([1]);
  return AnalyzedPracticeSession(
    title: 'Tum Hi Ho - Arijit Singh',
    job: AnalysisJob(
      jobId: id,
      status: AnalysisJobStatus.completed,
      createdAt: DateTime.utc(2026, 10, 22),
      updatedAt: DateTime.utc(2026, 10, 22),
      error: null,
      resultAvailable: true,
    ),
    audioFile: File('${directory.path}/$id.mp3'),
    timeline: _timeline(),
  );
}

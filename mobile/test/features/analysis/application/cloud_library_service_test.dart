import 'dart:io';

import 'package:chordsync/features/analysis/application/cloud_library_controller.dart';
import 'package:chordsync/features/analysis/application/cloud_library_service.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter_test/flutter_test.dart';

const _id = '659a6b1b-5e85-4f7f-8c9e-acfa420db980';

class _FakeApi implements CloudLibraryApi {
  final calls = <String>[];
  CloudAudioLink link = const CloudAudioLink(
    url: 'https://bucket.invalid/audio.mp3?sig=1',
    expiresInSeconds: 600,
    fileType: 'mp3',
  );
  Object? timelineError;
  List<CloudSong> mineSongs = [];

  @override
  Future<List<CloudSong>> listSongs() async => [_song()];

  @override
  Future<List<CloudSong>> listMySongs() async => mineSongs;

  @override
  Future<SharedTimeline> getSongTimeline(
    String jobId, {
    bool mine = false,
  }) async {
    calls.add(mine ? 'timeline-mine' : 'timeline');
    if (timelineError != null) throw timelineError!;
    return _timeline();
  }

  @override
  Future<CloudAudioLink> getSongAudioLink(
    String jobId, {
    bool mine = false,
  }) async {
    calls.add(mine ? 'audio-mine' : 'audio');
    return link;
  }
}

class _FakeDownloader implements AudioDownloader {
  Object? error;
  final urls = <String>[];

  @override
  Future<void> download(
    String url,
    String destination, {
    void Function(double progress)? onProgress,
  }) async {
    urls.add(url);
    onProgress?.call(0.5);
    await File(destination).writeAsBytes([1, 2, 3]);
    if (error != null) throw error!;
  }
}

void main() {
  late Directory documents;
  late _FakeApi api;
  late _FakeDownloader downloader;
  late LocalAnalyzedSessionLibrary library;
  late CloudLibraryService service;

  setUp(() {
    documents = Directory.systemTemp.createTempSync('chordsync-cloud-test-');
    api = _FakeApi();
    downloader = _FakeDownloader();
    library = LocalAnalyzedSessionLibrary(
      documentsDirectory: () async => documents,
    );
    service = CloudLibraryService(
      api: api,
      library: library,
      downloader: downloader,
      documentsDirectory: () async => documents,
    );
  });

  tearDown(() => documents.deleteSync(recursive: true));

  test(
    'downloads the audio and saves the song like one analysed here',
    () async {
      final progress = <double>[];

      final session = await service.download(_song(), onProgress: progress.add);

      expect(session.job.jobId, _id);
      expect(session.title, 'Sudu Gawuma - La Signore');
      expect(
        session.audioFile.path,
        '${documents.path}/imported_audio/cloud-$_id.mp3',
      );
      expect(await session.audioFile.readAsBytes(), [1, 2, 3]);
      expect(progress, [0.5]);
      // The audio comes from the link, and a partial file is never left behind.
      expect(downloader.urls.single, startsWith('https://bucket.invalid/'));
      expect(File('${session.audioFile.path}.part').existsSync(), isFalse);
      // It is now in the saved songs, found again after a reload.
      final saved = await library.load();
      expect(saved.single.job.jobId, _id);
      expect(saved.single.audioFile.existsSync(), isTrue);
    },
  );

  test('a song of your own is fetched from your own routes', () async {
    final own = CloudSong(
      jobId: _id,
      title: 'Payphone - Maroon 5',
      createdAt: DateTime.utc(2026, 10, 28),
      mine: true,
    );

    await service.download(own);

    expect(api.calls, ['timeline-mine', 'audio-mine']);
  });

  test('your own analyses are brought onto a new phone, once', () async {
    api.mineSongs = [
      CloudSong(
        jobId: _id,
        title: 'Payphone - Maroon 5',
        createdAt: DateTime.utc(2026, 10, 28),
        mine: true,
      ),
    ];
    final cloud = CloudLibraryController(service: service, syncMine: true);
    addTearDown(cloud.dispose);

    await cloud.refresh();
    expect((await library.load()).map((s) => s.job.jobId), [_id]);
    expect(api.calls, ['timeline-mine', 'audio-mine']);

    await cloud.refresh(); // already on the phone: nothing more is fetched
    expect(api.calls, ['timeline-mine', 'audio-mine']);
  });

  test('asks for the small timeline before the large audio', () async {
    await service.download(_song());
    expect(api.calls, ['timeline', 'audio']);
  });

  test('a failed download leaves no file and no saved song', () async {
    downloader.error = const SocketException('offline');

    await expectLater(
      service.download(_song()),
      throwsA(isA<SocketException>()),
    );

    expect(Directory('${documents.path}/imported_audio').listSync(), isEmpty);
    expect(await library.load(), isEmpty);
  });

  test('a failed timeline fetch downloads nothing', () async {
    api.timelineError = const SocketException('offline');

    await expectLater(
      service.download(_song()),
      throwsA(isA<SocketException>()),
    );

    expect(downloader.urls, isEmpty);
  });

  test('refuses an id that could escape the app folder', () async {
    for (final bad in ['../../etc/passwd', 'a/b', 'short', 'x' * 80, '']) {
      await expectLater(
        service.download(_song(id: bad)),
        throwsA(isA<FormatException>()),
        reason: bad,
      );
    }
    expect(api.calls, isEmpty);
  });

  test('an unknown file type falls back to mp3', () async {
    api.link = const CloudAudioLink(
      url: 'https://bucket.invalid/a?sig=1',
      expiresInSeconds: 600,
      fileType: '../../evil',
    );

    final session = await service.download(_song());

    expect(session.audioFile.path, endsWith('cloud-$_id.mp3'));
  });
}

CloudSong _song({String id = _id}) => CloudSong(
  jobId: id,
  title: 'Sudu Gawuma - La Signore',
  createdAt: DateTime.utc(2026, 10, 23, 7, 45),
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

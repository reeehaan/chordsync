import 'package:chordsync/features/analysis/application/cloud_library_controller.dart';
import 'package:chordsync/features/analysis/application/cloud_library_service.dart';
import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/data/cloud_song_list_cache.dart';
import 'package:flutter_test/flutter_test.dart';

class _Service extends Fake implements CloudLibraryService {
  int listCalls = 0;
  int mineCalls = 0;

  @override
  Future<List<CloudSong>> songs() async {
    listCalls++;
    return [_song('aaaaaaaa-1')];
  }

  @override
  Future<List<CloudSong>> mySongs() async {
    mineCalls++;
    return const [];
  }

  @override
  Future<Set<String>> savedIds() async => {};
}

class _MemoryCache implements CloudSongListCache {
  CloudSongSnapshot? snapshot;

  @override
  Future<CloudSongSnapshot?> load() async => snapshot;

  @override
  Future<void> save(CloudSongSnapshot value) async => snapshot = value;
}

CloudSong _song(String id) => CloudSong(
  jobId: id,
  title: 'Song $id',
  createdAt: DateTime.utc(2026, 10, 1),
);

void main() {
  late _Service service;
  late _MemoryCache cache;
  late DateTime now;

  CloudLibraryController controller() => CloudLibraryController(
    service: service,
    syncMine: true,
    cache: cache,
    clock: () => now,
  );

  setUp(() {
    service = _Service();
    cache = _MemoryCache();
    now = DateTime.utc(2026, 10, 29, 12);
  });

  test(
    'the first open asks the API once, for the list and for my songs',
    () async {
      final cloud = controller();
      await cloud.refresh();

      expect(service.listCalls, 1);
      expect(service.mineCalls, 1);
      expect(cloud.songs, hasLength(1));
      expect(cache.snapshot?.songs, hasLength(1));
    },
  );

  test('a fresh list is shown from the phone with no API call', () async {
    await controller().refresh();
    now = now.add(const Duration(minutes: 3));

    final reopened = controller();
    await reopened.refresh();

    expect(service.listCalls, 1);
    expect(service.mineCalls, 1);
    expect(reopened.status, CloudLibraryStatus.ready);
    expect(reopened.songs, hasLength(1));
  });

  test('an old list is shown at once, then updated', () async {
    await controller().refresh();
    now = now.add(const Duration(minutes: 30));

    final reopened = controller();
    await reopened.refresh();

    expect(service.listCalls, 2);
    expect(service.mineCalls, 1); // my songs are checked hourly, not every time
    expect(reopened.songs, hasLength(1));
  });

  test('my songs are checked again after an hour', () async {
    await controller().refresh();
    now = now.add(const Duration(hours: 2));

    await controller().refresh();

    expect(service.mineCalls, 2);
  });

  test('a refresh asked for by hand always asks the API', () async {
    final cloud = controller();
    await cloud.refresh();
    await cloud.refresh(force: true);

    expect(service.listCalls, 2);
    expect(service.mineCalls, 2);
  });

  test('a failed update keeps showing the saved list', () async {
    await controller().refresh();
    now = now.add(const Duration(minutes: 30));
    final failing = _FailingService();
    final reopened = CloudLibraryController(
      service: failing,
      cache: cache,
      clock: () => now,
    );

    await reopened.refresh();

    expect(reopened.status, CloudLibraryStatus.ready);
    expect(reopened.songs, hasLength(1));
  });
}

class _FailingService extends _Service {
  @override
  Future<List<CloudSong>> songs() async => throw Exception('offline');
}

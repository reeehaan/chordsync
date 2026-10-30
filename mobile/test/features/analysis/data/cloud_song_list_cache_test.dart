import 'dart:io';

import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/data/cloud_song_list_cache.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('a saved list comes back as it was', (tester) async {
    await tester.runAsync(() async {
      final folder = Directory.systemTemp.createTempSync('songlist');
      addTearDown(() => folder.deleteSync(recursive: true));
      final cache = FileCloudSongListCache(() async => folder);
      final fetched = DateTime.utc(2026, 10, 29, 12);

      await cache.save(CloudSnapshotFactory.make(fetched));
      final loaded = await cache.load();

      expect(loaded?.songs.single.title, 'Duvet');
      expect(loaded?.songs.single.artist, 'Boa');
      expect(loaded?.songs.single.genres, ['Rock']);
      expect(loaded?.fetchedAt, fetched);
      expect(loaded?.mineSyncedAt, isNull);
    });
  });

  testWidgets('a missing or damaged file means nothing cached', (tester) async {
    await tester.runAsync(() async {
      final folder = Directory.systemTemp.createTempSync('songlist');
      addTearDown(() => folder.deleteSync(recursive: true));
      final cache = FileCloudSongListCache(() async => folder);

      expect(await cache.load(), isNull);

      File('${folder.path}/cloud_song_list.json').writeAsStringSync('{oops');
      expect(await cache.load(), isNull);
    });
  });
}

class CloudSnapshotFactory {
  static CloudSongSnapshot make(DateTime fetched) => CloudSongSnapshot(
    fetchedAt: fetched,
    songs: [
      CloudSong(
        jobId: 'aaaaaaaa-1',
        title: 'Duvet',
        createdAt: DateTime.utc(2026, 10, 1),
        artist: 'Boa',
        genres: const ['Rock'],
      ),
    ],
  );
}

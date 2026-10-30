import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'cloud_library_api.dart';

/// The shared song list as last fetched, and when. Showing this first means
/// opening the app costs no API call while it is still fresh.
class CloudSongSnapshot {
  const CloudSongSnapshot({
    required this.songs,
    required this.fetchedAt,
    this.mineSyncedAt,
  });

  final List<CloudSong> songs;
  final DateTime fetchedAt;

  /// When the person's own analyses were last checked for, or null if never.
  final DateTime? mineSyncedAt;

  CloudSongSnapshot copyWith({
    List<CloudSong>? songs,
    DateTime? fetchedAt,
    DateTime? mineSyncedAt,
  }) => CloudSongSnapshot(
    songs: songs ?? this.songs,
    fetchedAt: fetchedAt ?? this.fetchedAt,
    mineSyncedAt: mineSyncedAt ?? this.mineSyncedAt,
  );
}

abstract interface class CloudSongListCache {
  Future<CloudSongSnapshot?> load();
  Future<void> save(CloudSongSnapshot snapshot);
}

/// Keeps the snapshot in one small file. Any problem reading or writing it is
/// treated as "nothing cached": the list is then simply fetched.
class FileCloudSongListCache implements CloudSongListCache {
  FileCloudSongListCache([Future<Directory> Function()? directory])
    : _directory = directory ?? getApplicationSupportDirectory;

  final Future<Directory> Function() _directory;

  Future<File> _file() async =>
      File(p.join((await _directory()).path, 'cloud_song_list.json'));

  @override
  Future<CloudSongSnapshot?> load() async {
    try {
      final file = await _file();
      if (!await file.exists()) return null;
      final json =
          jsonDecode(await file.readAsString()) as Map<String, dynamic>;
      return CloudSongSnapshot(
        songs: [
          for (final song in json['songs'] as List<dynamic>)
            CloudSong.fromJson(song as Map<String, dynamic>),
        ],
        fetchedAt: DateTime.parse(json['fetched_at'] as String),
        mineSyncedAt: switch (json['mine_synced_at']) {
          final String value => DateTime.parse(value),
          _ => null,
        },
      );
    } on Object {
      return null;
    }
  }

  @override
  Future<void> save(CloudSongSnapshot snapshot) async {
    try {
      final file = await _file();
      await file.parent.create(recursive: true);
      final partial = File('${file.path}.part');
      await partial.writeAsString(
        jsonEncode({
          'songs': [for (final song in snapshot.songs) song.toJson()],
          'fetched_at': snapshot.fetchedAt.toUtc().toIso8601String(),
          'mine_synced_at': snapshot.mineSyncedAt?.toUtc().toIso8601String(),
        }),
        flush: true,
      );
      await partial.rename(file.path);
    } on Object {
      // A cache that cannot be written only costs the next fetch.
    }
  }
}

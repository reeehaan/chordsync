import 'package:flutter/foundation.dart';

import '../data/cloud_library_api.dart';
import '../data/cloud_song_list_cache.dart';
import 'analyzed_practice_session.dart';
import 'cloud_library_service.dart';

enum CloudLibraryStatus { idle, loading, ready, failed }

/// What the "From the cloud" section shows: the songs in the shared library,
/// and the progress of any being downloaded to this phone.
class CloudLibraryController extends ChangeNotifier {
  CloudLibraryController({
    required this.service,
    this.onDownloaded,
    this.syncMine = false,
    this.cache,
    this.listMaxAge = const Duration(minutes: 10),
    this.mineMaxAge = const Duration(hours: 1),
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  /// Where the song list is kept between launches, or null to keep none.
  final CloudSongListCache? cache;

  /// How long a fetched list is shown without asking the API again.
  final Duration listMaxAge;

  /// How often the person's own analyses are checked for on a refresh that was
  /// not asked for by hand.
  final Duration mineMaxAge;

  final DateTime Function() _clock;
  CloudSongSnapshot? _snapshot;
  bool _cacheRead = false;

  /// When true, the songs the person analysed (on any phone) are brought onto
  /// this phone whenever the library refreshes, so a new install shows them.
  final bool syncMine;

  final CloudLibraryService service;

  /// Called with each song once it is saved on this phone.
  ValueChanged<AnalyzedPracticeSession>? onDownloaded;

  CloudLibraryStatus _status = CloudLibraryStatus.idle;
  List<CloudSong> _songs = const [];
  final Map<String, double> _progress = {};
  final Map<String, String> _errors = {};
  final Set<String> _saved = {};
  bool _disposed = false;
  bool _bringing = false;

  CloudLibraryStatus get status => _status;
  List<CloudSong> get songs => _songs;

  /// 0 to 1 for a song being downloaded, absent otherwise.
  double? progressOf(String jobId) => _progress[jobId];
  bool isDownloading(String jobId) => _progress.containsKey(jobId);
  String? errorOf(String jobId) => _errors[jobId];

  /// True once the song has been saved on this phone from here, so lists stop
  /// offering it even before the saved-songs list has caught up.
  bool isSaved(String jobId) => _saved.contains(jobId);

  /// Shows the list, asking the API only when it is older than [listMaxAge].
  /// A refresh asked for by hand ([force]) always asks, and also looks for the
  /// person's own songs on other phones.
  Future<void> refresh({bool force = false}) async {
    if (_status == CloudLibraryStatus.loading) return;
    if (!_cacheRead) {
      _cacheRead = true;
      _snapshot = await cache?.load();
      final saved = _snapshot;
      if (saved != null && _songs.isEmpty) {
        _songs = saved.songs;
        _status = CloudLibraryStatus.ready;
        _notify();
      }
    }
    final saved = _snapshot;
    final listIsFresh =
        !force &&
        saved != null &&
        _clock().difference(saved.fetchedAt) < listMaxAge;
    if (!listIsFresh) {
      final hadSongs = _songs.isNotEmpty;
      // With a list already on screen, update it quietly instead of
      // swapping it for a spinner.
      if (!hadSongs) {
        _status = CloudLibraryStatus.loading;
        _notify();
      }
      try {
        _songs = await service.songs();
        _status = CloudLibraryStatus.ready;
        _snapshot = CloudSongSnapshot(
          songs: _songs,
          fetchedAt: _clock(),
          mineSyncedAt: saved?.mineSyncedAt,
        );
        await cache?.save(_snapshot!);
      } on Object {
        _status = hadSongs
            ? CloudLibraryStatus.ready
            : CloudLibraryStatus.failed;
      }
      _notify();
    }
    if (!syncMine || _status != CloudLibraryStatus.ready) return;
    final lastMine = _snapshot?.mineSyncedAt;
    final mineIsFresh =
        !force &&
        lastMine != null &&
        _clock().difference(lastMine) < mineMaxAge;
    if (!mineIsFresh) await _bringMySongs();
  }

  /// Downloads the person's own analyses that are not on this phone yet, one at
  /// a time. A failure leaves the rest for the next refresh.
  Future<void> _bringMySongs() async {
    if (_bringing) return; // one pass at a time
    _bringing = true;
    try {
      final mine = await service.mySongs();
      final onPhone = await service.savedIds();
      for (final song in mine) {
        if (_disposed) return;
        if (onPhone.contains(song.jobId) || _saved.contains(song.jobId)) {
          continue;
        }
        await download(song);
      }
      final current = _snapshot;
      if (current != null) {
        _snapshot = current.copyWith(mineSyncedAt: _clock());
        await cache?.save(_snapshot!);
      }
    } on Object {
      // Offline, or signed in without an account: nothing to bring.
    } finally {
      _bringing = false;
    }
  }

  Future<void> download(CloudSong song) async {
    if (isDownloading(song.jobId)) return;
    _progress[song.jobId] = 0;
    _errors.remove(song.jobId);
    _notify();
    try {
      final session = await service.download(
        song,
        onProgress: (value) {
          _progress[song.jobId] = value;
          _notify();
        },
      );
      _progress.remove(song.jobId);
      _saved.add(song.jobId);
      _notify();
      onDownloaded?.call(session);
    } on Object {
      _progress.remove(song.jobId);
      _errors[song.jobId] = 'Could not download this song. Try again.';
      _notify();
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

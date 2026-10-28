import 'package:flutter/foundation.dart';

import '../data/cloud_library_api.dart';
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
  });

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

  Future<void> refresh() async {
    if (_status == CloudLibraryStatus.loading) return;
    _status = CloudLibraryStatus.loading;
    _notify();
    try {
      _songs = await service.songs();
      _status = CloudLibraryStatus.ready;
    } on Object {
      _status = CloudLibraryStatus.failed;
    }
    _notify();
    if (syncMine && _status == CloudLibraryStatus.ready) await _bringMySongs();
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

import 'dart:io';

import 'package:dio/dio.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../data/analysis_job.dart';
import '../data/analyzed_session_library.dart';
import '../data/cloud_library_api.dart';
import 'analyzed_practice_session.dart';

/// Saves a song's audio from a download link to a file.
abstract interface class AudioDownloader {
  Future<void> download(
    String url,
    String destination, {
    void Function(double progress)? onProgress,
  });
}

/// A plain client: the link carries its own permission, and the app's bearer
/// token must never be sent to storage.
class DioAudioDownloader implements AudioDownloader {
  DioAudioDownloader([Dio? dio]) : _dio = dio ?? Dio();

  final Dio _dio;

  @override
  Future<void> download(
    String url,
    String destination, {
    void Function(double progress)? onProgress,
  }) async {
    // Uploads stop at 25 MB, so nothing bigger than this is a real song.
    final cancel = CancelToken();
    await _dio.download(
      url,
      destination,
      cancelToken: cancel,
      onReceiveProgress: (received, total) {
        if (received > maxBytes || total > maxBytes) {
          cancel.cancel('The download is larger than a song can be.');
          return;
        }
        if (total > 0) onProgress?.call(received / total);
      },
    );
  }

  static const maxBytes = 30 * 1024 * 1024;
}

/// Brings a song from the shared library onto this phone: its timeline and its
/// audio, saved like a song analysed here.
class CloudLibraryService {
  CloudLibraryService({
    required this.api,
    required this.library,
    AudioDownloader? downloader,
    this.documentsDirectory = getApplicationDocumentsDirectory,
  }) : downloader = downloader ?? DioAudioDownloader();

  final CloudLibraryApi api;
  final AnalyzedSessionLibrary library;
  final AudioDownloader downloader;
  final Future<Directory> Function() documentsDirectory;

  static final _safeId = RegExp(r'^[A-Za-z0-9-]{8,64}$');
  static const _audioTypes = {'mp3', 'm4a', 'wav'};

  Future<List<CloudSong>> songs() => api.listSongs();

  Future<List<CloudSong>> mySongs() => api.listMySongs();

  /// The ids of the songs saved on this phone.
  Future<Set<String>> savedIds() async => {
    for (final session in await library.load()) session.job.jobId,
  };

  Future<AnalyzedPracticeSession> download(
    CloudSong song, {
    void Function(double progress)? onProgress,
  }) async {
    // The id becomes part of a file name, so a server that sent something
    // odd cannot make the app write outside its own folder.
    if (!_safeId.hasMatch(song.jobId)) {
      throw const FormatException('Unexpected song id.');
    }
    // The timeline is small and the audio is big: fetch it first, so a failure
    // does not leave a large file behind.
    final timeline = await api.getSongTimeline(song.jobId, mine: song.mine);
    final link = await api.getSongAudioLink(song.jobId, mine: song.mine);

    final documents = await documentsDirectory();
    final directory = Directory(p.join(documents.path, 'imported_audio'));
    await directory.create(recursive: true);
    final type = _audioTypes.contains(link.fileType) ? link.fileType : 'mp3';
    final file = File(p.join(directory.path, 'cloud-${song.jobId}.$type'));
    final partial = File('${file.path}.part');
    try {
      await downloader.download(link.url, partial.path, onProgress: onProgress);
      await partial.rename(file.path);
    } on Object {
      if (await partial.exists()) await partial.delete();
      rethrow;
    }

    final now = DateTime.now().toUtc();
    final session = AnalyzedPracticeSession(
      title: song.title,
      audioFile: file,
      job: AnalysisJob(
        jobId: song.jobId,
        status: AnalysisJobStatus.completed,
        createdAt: song.createdAt,
        updatedAt: now,
        error: null,
        resultAvailable: true,
      ),
      timeline: timeline,
    );
    await library.save(session);
    return session;
  }
}

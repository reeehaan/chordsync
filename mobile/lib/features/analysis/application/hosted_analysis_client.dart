import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';

import '../../practice_timeline/data/shared_timeline.dart';
import '../data/analysis_api_client.dart';
import '../data/analysis_cancellation.dart';
import '../data/analysis_client_errors.dart';
import '../data/analysis_job.dart';
import '../data/hosted_analysis_api.dart';
import '../data/hosted_upload_models.dart';
import '../data/presigned_uploader.dart';

typedef HostedRetryDelay = Future<void> Function(Duration duration);

/// Submits audio to the hosted backend: check the file, create a job, upload
/// straight to storage, confirm. It plugs in as an [AnalysisApiClient], so the
/// existing coordinator still does the rest (poll, fetch the result, build the
/// practice session) and widgets never see an HTTP call.
class HostedAnalysisClient implements AnalysisApiClient {
  HostedAnalysisClient({
    required this.api,
    required this.uploader,
    this.confirmAttempts = 3,
    this.confirmRetryDelay = const Duration(seconds: 1),
    this._delay = Future<void>.delayed,
    this.cancelCheckInterval = const Duration(milliseconds: 200),
  });

  static const _contentTypes = {
    'wav': 'audio/wav',
    'mp3': 'audio/mpeg',
    'm4a': 'audio/mp4',
  };

  final HostedAnalysisApi api;
  final PresignedUploader uploader;

  /// How many times to ask the server to confirm before giving up on
  /// "upload not received" (storage is consistent, so this is a safety net).
  final int confirmAttempts;
  final Duration confirmRetryDelay;
  final Duration cancelCheckInterval;
  final HostedRetryDelay _delay;

  @override
  Future<AnalysisJob> createJob({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onSendProgress,
    AnalysisPollingCancellationToken? cancellation,
  }) async {
    final request = await _validate(title, audioFile);
    _throwIfCancelled(cancellation);

    final target = await api.createUpload(request);
    try {
      _throwIfCancelled(cancellation);
      await _upload(target, audioFile, onSendProgress, cancellation);
      _throwIfCancelled(cancellation);
      final outcome = await _confirm(target.jobId, cancellation);
      return outcome.job;
    } on AnalysisPollingCancelledException {
      // The job exists on the server already; tell it to stop waiting.
      await _cancelQuietly(target.jobId);
      rethrow;
    }
  }

  @override
  Future<void> cancelJob(String jobId) async {
    await api.cancelJob(jobId);
  }

  Future<void> _cancelQuietly(String jobId) async {
    try {
      await api.cancelJob(jobId);
    } on Object {
      // Best effort: an unreachable server must not hide the cancellation.
    }
  }

  @override
  Future<AnalysisJob> getJob(String jobId) => api.getJob(jobId);

  @override
  Future<SharedTimeline> getResult(String jobId) => api.getResult(jobId);

  Future<CreateUploadRequest> _validate(String title, File audioFile) async {
    final filename = audioFile.uri.pathSegments.last;
    final extension = filename.contains('.')
        ? filename.split('.').last.toLowerCase()
        : '';
    final contentType = _contentTypes[extension];
    if (contentType == null) {
      throw const AnalysisApiException(
        statusCode: 400,
        code: 'unsupported_audio_format',
        message: 'Supported audio formats are WAV, MP3, and M4A.',
      );
    }
    final int size;
    try {
      size = await audioFile.length();
    } on FileSystemException {
      throw const AnalysisDataException('Could not read the audio file.');
    }
    if (size <= 0) {
      throw const AnalysisApiException(
        statusCode: 400,
        code: 'empty_audio',
        message: 'The audio file is empty.',
      );
    }
    if (size > maxAnalysisUploadBytes) {
      throw const AnalysisApiException(
        statusCode: 413,
        code: 'audio_too_large',
        message: 'Audio exceeds the 25 MB limit.',
      );
    }
    return CreateUploadRequest(
      title: title,
      filename: filename,
      declaredSizeBytes: size,
      contentType: contentType,
    );
  }

  Future<void> _upload(
    UploadTarget target,
    File file,
    AnalysisUploadProgress? onProgress,
    AnalysisPollingCancellationToken? cancellation,
  ) async {
    final cancelToken = CancelToken();
    // The token is a plain flag, so watch it while the upload is running.
    final watcher = cancellation == null
        ? null
        : Timer.periodic(cancelCheckInterval, (_) {
            if (cancellation.isCancelled) cancelToken.cancel();
          });
    try {
      await uploader.upload(
        target: target,
        file: file,
        onProgress: onProgress,
        cancelToken: cancelToken,
      );
    } finally {
      watcher?.cancel();
    }
  }

  Future<ConfirmOutcome> _confirm(
    String jobId,
    AnalysisPollingCancellationToken? cancellation,
  ) async {
    for (var attempt = 1; ; attempt++) {
      try {
        return await api.confirmUpload(jobId);
      } on AnalysisApiException catch (error) {
        final retryable =
            error.code == 'upload_not_received' && attempt < confirmAttempts;
        if (!retryable) rethrow;
      }
      await _delay(confirmRetryDelay);
      _throwIfCancelled(cancellation);
    }
  }

  void _throwIfCancelled(AnalysisPollingCancellationToken? cancellation) {
    if (cancellation?.isCancelled ?? false) {
      throw const AnalysisPollingCancelledException();
    }
  }
}

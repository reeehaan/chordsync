import 'dart:io';

import '../../practice_timeline/application/practice_timeline_validator.dart';
import '../data/analysis_api_client.dart';
import 'analysis_job_poller.dart';
import 'analyzed_practice_session.dart';
import 'practice_preparation_error.dart';

export 'analyzed_practice_session.dart';
export 'practice_preparation_error.dart';

abstract interface class AnalysisPracticePreparation {
  Future<AnalyzedPracticeSession> prepare({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onUploadProgress,
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  });
}

class AnalysisPracticeCoordinator implements AnalysisPracticePreparation {
  factory AnalysisPracticeCoordinator({
    required AnalysisApiClient client,
    required AnalysisJobPolling polling,
  }) => AnalysisPracticeCoordinator._(client, polling);

  const AnalysisPracticeCoordinator._(this._client, this._polling);

  final AnalysisApiClient _client;
  final AnalysisJobPolling _polling;

  @override
  Future<AnalyzedPracticeSession> prepare({
    required String title,
    required File audioFile,
    AnalysisUploadProgress? onUploadProgress,
    AnalysisPollingCancellationToken? cancellation,
    AnalysisJobUpdate? onJobUpdated,
  }) async {
    await _ensureReadable(audioFile);
    final createdJob = await _client.createJob(
      title: title,
      audioFile: audioFile,
      onSendProgress: onUploadProgress,
      cancellation: cancellation,
    );
    onJobUpdated?.call(createdJob);
    final completed = await _polling.pollUntilComplete(
      createdJob.jobId,
      cancellation: cancellation,
      onJobUpdated: onJobUpdated,
    );
    await _ensureReadable(audioFile);
    try {
      PracticeTimelineValidator.validate(completed.timeline);
    } on FormatException catch (_) {
      throw const PracticePreparationException(
        PracticePreparationErrorCode.timelineIncompatible,
        'The analyzed timeline cannot be used for practice.',
      );
    }
    return AnalyzedPracticeSession(
      title: title,
      job: completed.job,
      audioFile: audioFile,
      timeline: completed.timeline,
    );
  }

  Future<void> _ensureReadable(File audioFile) async {
    try {
      final handle = await audioFile.open(mode: FileMode.read);
      await handle.close();
    } on FileSystemException catch (_) {
      throw const PracticePreparationException(
        PracticePreparationErrorCode.localAudioUnavailable,
        'The selected local audio file is no longer available.',
      );
    }
  }
}

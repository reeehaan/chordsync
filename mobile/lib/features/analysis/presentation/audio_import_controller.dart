import 'dart:io';

import 'package:flutter/foundation.dart';

import '../application/analysis_job_poller.dart';
import '../application/analysis_practice_coordinator.dart';
import '../data/analysis_client_errors.dart';
import '../data/analysis_job.dart';
import '../data/analyzed_session_library.dart';

enum AudioImportPhase {
  idle,
  fileSelected,
  uploading,
  queued,
  processing,
  preparing,
  ready,
  failed,
  cancelled,
}

class AudioImportController extends ChangeNotifier {
  factory AudioImportController({
    required AnalysisPracticePreparation preparation,
    AnalyzedSessionLibrary? sessionLibrary,
  }) => AudioImportController._(preparation, sessionLibrary);

  AudioImportController._(this._preparation, this._sessionLibrary);

  static const supportedExtensions = {'wav', 'mp3', 'm4a'};

  final AnalysisPracticePreparation _preparation;
  final AnalyzedSessionLibrary? _sessionLibrary;
  AudioImportPhase _phase = AudioImportPhase.idle;
  File? _selectedFile;
  String? _displayName;
  String _title = '';
  int? _fileSizeBytes;
  double? _uploadProgress;
  String? _errorMessage;
  AnalyzedPracticeSession? _session;
  AnalysisPollingCancellationToken? _cancellation;
  bool _active = false;
  bool _disposed = false;
  int _attempt = 0;

  AudioImportPhase get phase => _phase;
  File? get selectedFile => _selectedFile;
  String? get filename => _displayName;
  String? get extension {
    final name = filename;
    if (name == null || !name.contains('.')) return null;
    return name.split('.').last.toLowerCase();
  }

  int? get fileSizeBytes => _fileSizeBytes;
  String get title => _title;
  double? get uploadProgress => _uploadProgress;
  String? get errorMessage => _errorMessage;
  AnalyzedPracticeSession? get session => _session;
  bool get isActive => _active;
  bool get isDisposed => _disposed;
  bool get canAnalyze =>
      !_active &&
      _selectedFile != null &&
      _title.trim().isNotEmpty &&
      _title.trim().length <= 200;

  bool selectFile(File file, {String? displayName}) {
    if (_active) return false;
    final name = displayName ?? file.uri.pathSegments.last;
    final storedName = file.uri.pathSegments.last;
    final suffix = storedName.contains('.')
        ? storedName.split('.').last.toLowerCase()
        : '';
    if (!supportedExtensions.contains(suffix)) {
      _selectedFile = null;
      _displayName = null;
      _fileSizeBytes = null;
      _session = null;
      _phase = AudioImportPhase.failed;
      _errorMessage = 'Choose a WAV, MP3, or M4A audio file.';
      _notify();
      return false;
    }

    _selectedFile = file;
    _displayName = name;
    try {
      _fileSizeBytes = file.lengthSync();
    } on FileSystemException {
      _fileSizeBytes = null;
    }
    final titleSuffix = name.contains('.') ? name.split('.').last : '';
    _title = titleSuffix.isEmpty
        ? name
        : name.substring(0, name.length - titleSuffix.length - 1);
    _uploadProgress = null;
    _errorMessage = null;
    _session = null;
    _phase = AudioImportPhase.fileSelected;
    _notify();
    return true;
  }

  void setTitle(String value) {
    if (_active) return;
    _title = value;
    _notify();
  }

  Future<void> analyze() async {
    if (!canAnalyze) return;
    final file = _selectedFile!;
    final title = _title.trim();
    final attempt = ++_attempt;
    final cancellation = AnalysisPollingCancellationToken();
    _cancellation = cancellation;
    _active = true;
    _session = null;
    _errorMessage = null;
    _uploadProgress = null;
    _phase = AudioImportPhase.uploading;
    _notify();

    try {
      final session = await _preparation.prepare(
        title: title,
        audioFile: file,
        cancellation: cancellation,
        onUploadProgress: (sent, total) {
          if (!_isCurrent(attempt) || total <= 0) return;
          _uploadProgress = (sent / total).clamp(0, 1);
          _notify();
        },
        onJobUpdated: (job) {
          if (!_isCurrent(attempt)) return;
          _phase = switch (job.status) {
            AnalysisJobStatus.queued => AudioImportPhase.queued,
            AnalysisJobStatus.processing => AudioImportPhase.processing,
            AnalysisJobStatus.completed => AudioImportPhase.preparing,
            AnalysisJobStatus.failed => AudioImportPhase.failed,
          };
          _notify();
        },
      );
      if (!_isCurrent(attempt)) return;
      _session = session;
      try {
        await _sessionLibrary?.save(session);
      } on FileSystemException {
        // A local-library write failure must not discard a valid practice.
      } on AnalyzedSessionLibraryException {
        // A local-library write failure must not discard a valid practice.
      }
      _phase = AudioImportPhase.ready;
    } on Object catch (error) {
      if (!_isCurrent(attempt)) return;
      if (error is AnalysisPollingCancelledException) {
        _phase = AudioImportPhase.cancelled;
      } else {
        _phase = AudioImportPhase.failed;
        _errorMessage = _friendlyMessage(error);
      }
    } finally {
      if (_isCurrent(attempt)) {
        _active = false;
        _cancellation = null;
        _notify();
      }
    }
  }

  void cancel() {
    if (!_active) return;
    _cancellation?.cancel();
    _active = false;
    _attempt += 1;
    _phase = AudioImportPhase.cancelled;
    _uploadProgress = null;
    _notify();
  }

  bool _isCurrent(int attempt) => !_disposed && attempt == _attempt;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  String _friendlyMessage(Object error) {
    if (error is AnalysisTransportException) {
      return "ChordSync can't reach the analysis service.";
    }
    if (error is AnalysisPollingTimeoutException) {
      return 'Analysis is taking longer than expected.';
    }
    if (error is PracticePreparationException) {
      return switch (error.code) {
        PracticePreparationErrorCode.localAudioUnavailable =>
          'The selected audio file is no longer available.',
        PracticePreparationErrorCode.timelineIncompatible ||
        PracticePreparationErrorCode.initializationFailed =>
          'The practice session could not be prepared.',
      };
    }
    if (error is AnalysisApiException) {
      return switch (error.code) {
        'unsupported_audio_format' => 'Choose a WAV, MP3, or M4A audio file.',
        'audio_too_large' => 'The selected audio file is too large.',
        _ => 'The song could not be analyzed.',
      };
    }
    if (error is AnalysisDataException) {
      return 'ChordSync received an invalid analysis result.';
    }
    return 'The song could not be analyzed.';
  }

  @override
  void dispose() {
    if (_disposed) return;
    _cancellation?.cancel();
    _disposed = true;
    _active = false;
    _attempt += 1;
    super.dispose();
  }
}

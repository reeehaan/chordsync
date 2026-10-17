import 'package:flutter/material.dart';

import 'design_system/chordsync_design_system.dart';
import 'features/analysis/application/analysis_job_poller.dart';
import 'features/analysis/application/analysis_practice_coordinator.dart';
import 'features/analysis/data/analysis_api_client.dart';
import 'features/analysis/application/hosted_analysis_client.dart';
import 'features/analysis/data/analysis_api_config.dart';
import 'features/analysis/data/hosted_analysis_api.dart';
import 'features/analysis/data/presigned_uploader.dart';
import 'features/analysis/data/analyzed_session_library.dart';
import 'features/analysis/presentation/audio_file_selector.dart';
import 'features/analysis/presentation/audio_import_controller.dart';
import 'features/analysis/presentation/audio_import_screen.dart';
import 'features/practice_timeline/application/practice_audio_player.dart';
import 'features/practice_timeline/application/practice_session_factory.dart';
import 'features/practice_timeline/presentation/practice_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatefulWidget {
  const MyApp({
    super.key,
    this.audioPlayer,
    this.analyzedSession,
    this.sessionFactory,
    this.importController,
    this.fileSelector,
  });

  final PracticeAudioPlayer? audioPlayer;
  final AnalyzedPracticeSession? analyzedSession;
  final PracticeSessionFactory? sessionFactory;
  final AudioImportController? importController;
  final AudioFileSelector? fileSelector;

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  AudioImportController? _importController;
  AnalyzedSessionLibrary? _sessionLibrary;

  bool get _usesPracticeFixture =>
      widget.audioPlayer != null || widget.analyzedSession != null;

  @override
  void initState() {
    super.initState();
    if (!_usesPracticeFixture) {
      _sessionLibrary = LocalAnalyzedSessionLibrary();
      _importController = widget.importController ?? _createImportController();
    }
  }

  AudioImportController _createImportController() {
    final config = AnalysisApiConfig.development;
    final client = _createAnalysisClient(config);
    return AudioImportController(
      preparation: AnalysisPracticeCoordinator(
        client: client,
        polling: AnalysisJobPoller(
          client: client,
          // The hosted API is rate limited and a job takes minutes.
          pollingInterval: Duration(seconds: config.isHosted ? 3 : 1),
        ),
      ),
      sessionLibrary: _sessionLibrary,
    );
  }

  /// Local development keeps the one-request multipart upload. The hosted API
  /// uses a presigned upload: create the job, send the audio straight to
  /// storage, then confirm.
  AnalysisApiClient _createAnalysisClient(AnalysisApiConfig config) {
    if (!config.isHosted) {
      return DioAnalysisApiClient(baseUrl: config.baseUrl);
    }
    return HostedAnalysisClient(
      api: DioHostedAnalysisApi(
        baseUrl: config.baseUrl,
        tokenProvider: () => config.authToken,
      ),
      // A separate plain client: the bearer token must never reach storage.
      uploader: DioPresignedUploader(),
    );
  }

  @override
  void dispose() {
    _importController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ChordSync',
      theme: ChordSyncTheme.light(),
      home: _usesPracticeFixture
          ? PracticeScreen(
              audioPlayer: widget.audioPlayer,
              analyzedSession: widget.analyzedSession,
              sessionFactory: widget.sessionFactory,
            )
          : AudioImportScreen(
              controller: _importController!,
              fileSelector:
                  widget.fileSelector ?? const NativeAudioFileSelector(),
              practiceSessionFactory: widget.sessionFactory,
              sessionLibrary: _sessionLibrary,
            ),
    );
  }
}

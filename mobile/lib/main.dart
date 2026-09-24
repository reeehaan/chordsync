import 'package:flutter/material.dart';

import 'design_system/chordsync_design_system.dart';
import 'features/analysis/application/analysis_job_poller.dart';
import 'features/analysis/application/analysis_practice_coordinator.dart';
import 'features/analysis/data/analysis_api_client.dart';
import 'features/analysis/data/analysis_api_config.dart';
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
    final client = DioAnalysisApiClient(
      baseUrl: AnalysisApiConfig.development.baseUrl,
    );
    return AudioImportController(
      preparation: AnalysisPracticeCoordinator(
        client: client,
        polling: AnalysisJobPoller(client: client),
      ),
      sessionLibrary: _sessionLibrary,
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

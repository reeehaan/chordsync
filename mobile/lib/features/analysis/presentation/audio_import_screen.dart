import 'dart:async';

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../practice_timeline/application/practice_session_factory.dart';
import '../../practice_timeline/presentation/practice_screen.dart';
import '../application/analyzed_practice_session.dart';
import '../data/analyzed_session_library.dart';
import 'analysis_journey.dart';
import 'app_shell.dart';
import 'audio_file_selector.dart';
import 'audio_import_controller.dart';
import 'library_home.dart';
import 'song_source_grid.dart';
import 'tuner_home.dart';
import 'upload_theme.dart';

class AudioImportScreen extends StatefulWidget {
  const AudioImportScreen({
    super.key,
    required this.controller,
    required this.fileSelector,
    this.practiceSessionFactory,
    this.sessionLibrary,
  });

  final AudioImportController controller;
  final AudioFileSelector fileSelector;
  final PracticeSessionFactory? practiceSessionFactory;
  final AnalyzedSessionLibrary? sessionLibrary;

  @override
  State<AudioImportScreen> createState() => _AudioImportScreenState();
}

class _AudioImportScreenState extends State<AudioImportScreen> {
  List<AnalyzedPracticeSession> _savedSessions = const [];
  String? _loadedReadyJobId;
  String? _openedReadyJobId;
  int _selectedTab = 1;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_refresh);
    _loadSavedSessions();
  }

  @override
  void didUpdateWidget(covariant AudioImportScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller == widget.controller) return;
    oldWidget.controller.removeListener(_refresh);
    widget.controller.addListener(_refresh);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_refresh);
    super.dispose();
  }

  void _refresh() {
    if (!mounted) return;
    final session = widget.controller.session;
    if (widget.controller.phase == AudioImportPhase.ready &&
        session != null &&
        session.job.jobId != _loadedReadyJobId) {
      _loadedReadyJobId = session.job.jobId;
      _loadSavedSessions();
    }
    if (widget.controller.phase == AudioImportPhase.ready &&
        session != null &&
        session.job.jobId != _openedReadyJobId) {
      _openedReadyJobId = session.job.jobId;
      unawaited(_openCompletedPractice(session));
      return;
    }
    setState(() {});
  }

  Future<void> _openCompletedPractice(AnalyzedPracticeSession session) async {
    if (!mounted || widget.controller.session != session) return;
    await _startPractice();
    if (mounted) widget.controller.reset();
  }

  Future<void> _loadSavedSessions() async {
    final library = widget.sessionLibrary;
    if (library == null) return;
    final sessions = await library.load();
    if (mounted) setState(() => _savedSessions = sessions);
  }

  Future<void> _chooseAudio() async {
    SelectedAudioFile? selection;
    try {
      selection = await widget.fileSelector.chooseAudio();
    } on Object {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Could not import that audio file. Please try again.',
            ),
          ),
        );
      }
      return;
    }
    if (!mounted || selection == null) return;
    final selected = widget.controller.selectFile(
      selection.file,
      displayName: selection.displayName,
    );
    // A valid file goes straight into analysis — there is no separate
    // review step to confirm first.
    if (selected) unawaited(widget.controller.analyze());
  }

  void _showSourceNotice(String title, String message) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 10),
            Text(message),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Got it'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _startPractice() async {
    final session = widget.controller.session;
    if (session == null) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => PracticeScreen(
          analyzedSession: session,
          sessionFactory: widget.practiceSessionFactory,
        ),
      ),
    );
  }

  Future<void> _openSavedPractice(AnalyzedPracticeSession session) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => PracticeScreen(
          analyzedSession: session,
          sessionFactory: widget.practiceSessionFactory,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    if (controller.isActive) {
      return Scaffold(
        body: SafeArea(
          child: AnalysisJourney(
            controller: controller,
            onCancel: controller.cancel,
          ),
        ),
      );
    }
    if (_selectedTab == 0) {
      return AppShell(
        selectedIndex: _selectedTab,
        onSelected: (index) => setState(() => _selectedTab = index),
        child: LibraryHome(
          sessions: _savedSessions,
          onOpen: _openSavedPractice,
          onAddSong: () => setState(() => _selectedTab = 1),
        ),
      );
    }
    if (_selectedTab == 2) {
      return AppShell(
        selectedIndex: _selectedTab,
        onSelected: (index) => setState(() => _selectedTab = index),
        child: const TunerHome(),
      );
    }
    final isFocusedState =
        controller.isActive || controller.phase == AudioImportPhase.ready;
    final compactViewport = MediaQuery.sizeOf(context).height <= 700;
    return Theme(
      data: uploadTheme(context),
      // A Builder hands every descendant a context positioned below this
      // Theme. Without it, `Theme.of(context)` calls further down would
      // keep resolving the outer (light) theme — reusing this method's own
      // `context` parameter, which sits above the Theme we just inserted —
      // and text relying on that theme's colour would render using the
      // wrong palette.
      child: Builder(
        builder: (context) => Scaffold(
          body: SafeArea(
            child: SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(
                20,
                compactViewport ? 20 : 28,
                20,
                compactViewport ? 24 : 40,
              ),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 620),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        'Upload',
                        style: isFocusedState
                            ? Theme.of(context).textTheme.headlineSmall
                            : Theme.of(context).textTheme.displayMedium,
                      ),
                      if (!isFocusedState) ...[
                        SizedBox(height: compactViewport ? 8 : 12),
                        const Text('Get the chords for any audio track'),
                        SizedBox(height: compactViewport ? 16 : 24),
                        SongSourceGrid(
                          compact: compactViewport,
                          onFiles: _chooseAudio,
                          onYouTube: () => _showSourceNotice(
                            'YouTube',
                            'YouTube can help identify or open a song, but '
                                'ChordSync does not download arbitrary YouTube '
                                'audio. Choose an audio file you own for analysis.',
                          ),
                          onCameraRoll: () => _showSourceNotice(
                            'Camera Roll',
                            'Video import is not connected yet. For now, save or '
                                'export its audio to Files and choose it there.',
                          ),
                          onRecord: () => _showSourceNotice(
                            'Record audio',
                            'Microphone recording is not connected yet. You can '
                                'record with Voice Memos, save it to Files, and '
                                'analyze the exported audio.',
                          ),
                          onShazam: () => _showSourceNotice(
                            'Shazam',
                            'Shazam can help identify a song, but ChordSync does '
                                'not connect to it directly yet. Identify the '
                                'song there, then choose a matching audio file '
                                'you own for analysis.',
                          ),
                        ),
                      ],
                      if (controller.selectedFile != null) ...[
                        SizedBox(height: compactViewport ? 12 : 16),
                        _SelectedAudioCard(controller: controller),
                      ],
                      SizedBox(height: compactViewport ? 8 : 12),
                      _AnalysisStatus(controller: controller),
                      SizedBox(height: compactViewport ? 12 : 16),
                      if (controller.phase == AudioImportPhase.ready)
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            FilledButton.icon(
                              key: const ValueKey('startPracticeButton'),
                              onPressed: _startPractice,
                              icon: const Icon(Icons.play_arrow),
                              label: const Text('Start Practice'),
                            ),
                            TextButton(
                              onPressed: _chooseAudio,
                              child: const Text('Choose another file'),
                            ),
                          ],
                        )
                      else if ((controller.phase == AudioImportPhase.failed ||
                              controller.phase == AudioImportPhase.cancelled) &&
                          controller.selectedFile != null)
                        // A failed or cancelled analysis is the only case
                        // left needing a manual trigger — picking a file
                        // always starts analysis by itself now.
                        FilledButton(
                          key: const ValueKey('retryAnalysisButton'),
                          onPressed: controller.canAnalyze
                              ? controller.analyze
                              : null,
                          child: const Text('Retry Analysis'),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          bottomNavigationBar: BottomDock(
            selectedIndex: _selectedTab,
            onSelected: (index) => setState(() => _selectedTab = index),
          ),
        ),
      ),
    );
  }
}

class _SelectedAudioCard extends StatelessWidget {
  const _SelectedAudioCard({required this.controller});

  final AudioImportController controller;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.music_note_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    controller.filename!,
                    key: const ValueKey('selectedFilename'),
                    style: Theme.of(context).textTheme.titleMedium,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const Divider(height: 22),
            Text(
              '${controller.extension!.toUpperCase()} • '
              '${_formatBytes(controller.fileSizeBytes)}',
            ),
          ],
        ),
      ),
    );
  }

  String _formatBytes(int? bytes) {
    if (bytes == null) return 'Size unavailable';
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}

class _AnalysisStatus extends StatelessWidget {
  const _AnalysisStatus({required this.controller});

  final AudioImportController controller;

  @override
  Widget build(BuildContext context) {
    final label = switch (controller.phase) {
      AudioImportPhase.idle || AudioImportPhase.fileSelected => null,
      AudioImportPhase.uploading => 'Uploading your song…',
      AudioImportPhase.finishingUpload => 'Finishing upload…',
      AudioImportPhase.queued => 'Waiting to analyze…',
      AudioImportPhase.processing => 'Analyzing your song…',
      AudioImportPhase.preparing => 'Preparing your practice sheet…',
      AudioImportPhase.ready => 'Ready to practice',
      AudioImportPhase.failed => controller.errorMessage,
      AudioImportPhase.cancelled => 'Stopped waiting. You can try again.',
    };
    if (label == null) return const SizedBox.shrink();

    final progress = controller.uploadProgress;
    final isReady = controller.phase == AudioImportPhase.ready;
    final isFailure = controller.phase == AudioImportPhase.failed;
    return Semantics(
      liveRegion: true,
      label: label,
      value: progress == null ? null : '${(progress * 100).round()} percent',
      child: Column(
        children: [
          if (isReady || isFailure) ...[
            Icon(
              isReady ? Icons.check_circle_outline : Icons.error_outline,
              color: isReady ? ChordSyncColors.success : ChordSyncColors.error,
              size: 32,
            ),
            const SizedBox(height: 8),
          ],
          if (controller.isActive) ...[
            LinearProgressIndicator(
              value: controller.phase == AudioImportPhase.uploading
                  ? progress
                  : null,
            ),
            const SizedBox(height: 10),
          ],
          Text(
            progress != null && controller.phase == AudioImportPhase.uploading
                ? 'Uploading your song… ${(progress * 100).round()}%'
                : label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          if (isReady)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('Your practice sheet is ready.'),
            ),
        ],
      ),
    );
  }
}

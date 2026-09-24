import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../practice_timeline/application/practice_session_factory.dart';
import '../../practice_timeline/presentation/practice_screen.dart';
import '../application/analyzed_practice_session.dart';
import '../data/analyzed_session_library.dart';
import 'audio_file_selector.dart';
import 'audio_import_controller.dart';

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
    setState(() {});
    final session = widget.controller.session;
    if (widget.controller.phase == AudioImportPhase.ready &&
        session != null &&
        session.job.jobId != _loadedReadyJobId) {
      _loadedReadyJobId = session.job.jobId;
      _loadSavedSessions();
    }
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
    widget.controller.selectFile(
      selection.file,
      displayName: selection.displayName,
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
    final isFocusedState =
        controller.isActive || controller.phase == AudioImportPhase.ready;
    final compactViewport = MediaQuery.sizeOf(context).height <= 700;
    return Scaffold(
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
                  Row(
                    children: [
                      const Icon(Icons.music_note, size: 25),
                      const SizedBox(width: 8),
                      Text(
                        'ChordSync',
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Practice with purpose.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: ChordSyncColors.textSecondary,
                    ),
                  ),
                  const SizedBox(height: 22),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          'Previously analyzed',
                          style: Theme.of(context).textTheme.titleLarge,
                        ),
                      ),
                      Text(
                        '${_savedSessions.length} saved',
                        style: Theme.of(context).textTheme.labelMedium
                            ?.copyWith(color: ChordSyncColors.textSecondary),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  if (_savedSessions.isEmpty)
                    Container(
                      key: const ValueKey('savedPracticeEmpty'),
                      height: 104,
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      decoration: BoxDecoration(
                        color: ChordSyncColors.surfaceAlt,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.history),
                          SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              'Your completed songs will appear here for quick practice.',
                            ),
                          ),
                        ],
                      ),
                    )
                  else
                    SizedBox(
                      height: 104,
                      child: ListView.separated(
                        key: const ValueKey('savedPracticeList'),
                        scrollDirection: Axis.horizontal,
                        itemCount: _savedSessions.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 10),
                        itemBuilder: (context, index) {
                          final session = _savedSessions[index];
                          return _SavedPracticeCard(
                            session: session,
                            onOpen: () => _openSavedPractice(session),
                          );
                        },
                      ),
                    ),
                  SizedBox(
                    height: isFocusedState ? 20 : (compactViewport ? 24 : 36),
                  ),
                  Text(
                    'Add a song',
                    style: isFocusedState
                        ? Theme.of(context).textTheme.headlineSmall
                        : Theme.of(context).textTheme.displayMedium,
                  ),
                  if (!isFocusedState) ...[
                    SizedBox(height: compactViewport ? 8 : 12),
                    const Text(
                      'Turn your recording into a guided guitar practice sheet.',
                    ),
                    SizedBox(height: compactViewport ? 16 : 24),
                    Card(
                      color: ChordSyncColors.surfaceAlt,
                      child: Padding(
                        padding: EdgeInsets.all(compactViewport ? 14 : 20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Icon(
                              Icons.library_music_outlined,
                              size: compactViewport ? 28 : 36,
                            ),
                            SizedBox(height: compactViewport ? 8 : 14),
                            OutlinedButton.icon(
                              key: const ValueKey('chooseAudioButton'),
                              onPressed: controller.isActive
                                  ? null
                                  : _chooseAudio,
                              icon: const Icon(Icons.audio_file_outlined),
                              label: Text(
                                controller.selectedFile == null
                                    ? 'Choose audio file'
                                    : 'Choose another file',
                              ),
                            ),
                            SizedBox(height: compactViewport ? 8 : 10),
                            Text(
                              'WAV · MP3 · M4A',
                              textAlign: TextAlign.center,
                              style: Theme.of(context).textTheme.labelMedium
                                  ?.copyWith(
                                    color: ChordSyncColors.textSecondary,
                                  ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                  if (controller.selectedFile != null) ...[
                    SizedBox(height: compactViewport ? 12 : 16),
                    _SelectedAudioCard(controller: controller),
                    if (!isFocusedState) ...[
                      SizedBox(height: compactViewport ? 12 : 16),
                      TextFormField(
                        key: ValueKey('title-${controller.filename}'),
                        initialValue: controller.title,
                        enabled: !controller.isActive,
                        maxLength: 200,
                        decoration: const InputDecoration(
                          labelText: 'Song title',
                          prefixIcon: Icon(Icons.edit_outlined),
                        ),
                        onChanged: controller.setTitle,
                      ),
                    ],
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
                  else if (controller.isActive)
                    TextButton(
                      key: const ValueKey('cancelAnalysisButton'),
                      onPressed: controller.cancel,
                      child: const Text('Stop waiting'),
                    )
                  else ...[
                    FilledButton(
                      key: const ValueKey('analyzeButton'),
                      onPressed: controller.canAnalyze
                          ? controller.analyze
                          : null,
                      child: Text(
                        controller.phase == AudioImportPhase.failed
                            ? 'Retry Analysis'
                            : 'Analyze Song',
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SavedPracticeCard extends StatelessWidget {
  const _SavedPracticeCard({required this.session, required this.onOpen});

  final AnalyzedPracticeSession session;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 230,
      child: Card(
        child: InkWell(
          key: ValueKey('savedPractice-${session.job.jobId}'),
          borderRadius: BorderRadius.circular(16),
          onTap: onOpen,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
            child: Row(
              children: [
                const CircleAvatar(child: Icon(Icons.music_note)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        session.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${session.timeline.bpm.toStringAsFixed(0)} BPM · Practice',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: ChordSyncColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
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

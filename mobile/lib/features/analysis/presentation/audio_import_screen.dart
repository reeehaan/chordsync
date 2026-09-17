import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../practice_timeline/application/practice_session_factory.dart';
import '../../practice_timeline/presentation/practice_screen.dart';
import 'audio_file_selector.dart';
import 'audio_import_controller.dart';

class AudioImportScreen extends StatefulWidget {
  const AudioImportScreen({
    super.key,
    required this.controller,
    required this.fileSelector,
    this.practiceSessionFactory,
  });

  final AudioImportController controller;
  final AudioFileSelector fileSelector;
  final PracticeSessionFactory? practiceSessionFactory;

  @override
  State<AudioImportScreen> createState() => _AudioImportScreenState();
}

class _AudioImportScreenState extends State<AudioImportScreen> {
  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_refresh);
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
    if (mounted) setState(() {});
  }

  Future<void> _chooseAudio() async {
    final file = await widget.fileSelector.chooseAudio();
    if (!mounted || file == null) return;
    widget.controller.selectFile(file);
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
                  SizedBox(
                    height: isFocusedState ? 20 : (compactViewport ? 24 : 48),
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

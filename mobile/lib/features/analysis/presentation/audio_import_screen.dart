import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../practice_timeline/application/practice_session_factory.dart';
import '../../practice_timeline/presentation/practice_screen.dart';
import '../application/analyzed_practice_session.dart';
import '../data/analyzed_session_library.dart';
import 'audio_file_selector.dart';
import 'audio_import_controller.dart';

abstract final class _UploadPalette {
  static const background = Color(0xFF171411);
  static const card = Color(0xFF241E1A);
  static const dock = Color(0xFF181512);
  static const selected = Color(0xFF403A36);
  static const border = Color(0xFF3B3531);
  static const primaryText = Color(0xFFF6F2ED);
  static const secondaryText = Color(0xFFB8AEA6);
  static const coral = Color(0xFFFF7779);
}

ThemeData _uploadTheme(BuildContext context) {
  final base = Theme.of(context);
  return base.copyWith(
    scaffoldBackgroundColor: _UploadPalette.background,
    textTheme: base.textTheme.apply(
      bodyColor: _UploadPalette.primaryText,
      displayColor: _UploadPalette.primaryText,
    ),
    iconTheme: const IconThemeData(color: _UploadPalette.primaryText),
    cardTheme: CardThemeData(
      color: _UploadPalette.card,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ChordSyncRadii.card),
        side: const BorderSide(color: _UploadPalette.border),
      ),
    ),
  );
}

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
    widget.controller.selectFile(
      selection.file,
      displayName: selection.displayName,
    );
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
          child: _AnalysisJourney(
            controller: controller,
            onCancel: controller.cancel,
          ),
        ),
      );
    }
    if (_selectedTab == 0) {
      return _AppShell(
        selectedIndex: _selectedTab,
        onSelected: (index) => setState(() => _selectedTab = index),
        child: _LibraryHome(
          sessions: _savedSessions,
          onOpen: _openSavedPractice,
          onAddSong: () => setState(() => _selectedTab = 1),
        ),
      );
    }
    if (_selectedTab == 2) {
      return _AppShell(
        selectedIndex: _selectedTab,
        onSelected: (index) => setState(() => _selectedTab = index),
        child: const _TunerHome(),
      );
    }
    final isFocusedState =
        controller.isActive || controller.phase == AudioImportPhase.ready;
    final compactViewport = MediaQuery.sizeOf(context).height <= 700;
    return Theme(
      data: _uploadTheme(context),
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
                        _SongSourceGrid(
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
          bottomNavigationBar: _BottomDock(
            selectedIndex: _selectedTab,
            onSelected: (index) => setState(() => _selectedTab = index),
          ),
        ),
      ),
    );
  }
}

class _AppShell extends StatelessWidget {
  const _AppShell({
    required this.child,
    required this.selectedIndex,
    required this.onSelected,
  });

  final Widget child;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: _uploadTheme(context),
      child: Scaffold(
        body: SafeArea(child: child),
        bottomNavigationBar: _BottomDock(
          selectedIndex: selectedIndex,
          onSelected: onSelected,
        ),
      ),
    );
  }
}

class _BottomDock extends StatelessWidget {
  const _BottomDock({required this.selectedIndex, required this.onSelected});

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    const items = [
      ('assets/icons/source_providers/home.svg', 'Home'),
      ('assets/icons/source_providers/plus.svg', 'Add song'),
      ('assets/icons/source_providers/tuner.svg', 'Tuner'),
    ];
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(24, 8, 24, 12),
      child: Container(
        height: 68,
        decoration: BoxDecoration(
          color: _UploadPalette.dock,
          borderRadius: BorderRadius.circular(34),
          border: Border.all(color: _UploadPalette.border),
          boxShadow: const [
            BoxShadow(
              color: Color(0x292B1B12),
              blurRadius: 18,
              offset: Offset(0, 8),
            ),
          ],
        ),
        child: Row(
          children: List.generate(items.length, (index) {
            final selected = selectedIndex == index;
            return Expanded(
              child: Semantics(
                selected: selected,
                label: items[index].$2,
                button: true,
                child: InkWell(
                  key: ValueKey('bottomNav$index'),
                  borderRadius: BorderRadius.circular(32),
                  onTap: () => onSelected(index),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 220),
                    margin: const EdgeInsets.all(7),
                    decoration: BoxDecoration(
                      color: selected
                          ? _UploadPalette.selected
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(28),
                    ),
                    child: Center(
                      child: SvgPicture.asset(
                        items[index].$1,
                        width: index == 1 ? 32 : 27,
                        height: index == 1 ? 32 : 27,
                        colorFilter: ColorFilter.mode(
                          selected
                              ? _UploadPalette.coral
                              : _UploadPalette.primaryText,
                          BlendMode.srcIn,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}

class _LibraryHome extends StatelessWidget {
  const _LibraryHome({
    required this.sessions,
    required this.onOpen,
    required this.onAddSong,
  });

  final List<AnalyzedPracticeSession> sessions;
  final ValueChanged<AnalyzedPracticeSession> onOpen;
  final VoidCallback onAddSong;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 28, 20, 32),
      children: [
        Text('Your songs', style: Theme.of(context).textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Pick up where you left off.',
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: _UploadPalette.secondaryText),
        ),
        const SizedBox(height: 28),
        if (sessions.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  const Icon(Icons.library_music_outlined, size: 42),
                  const SizedBox(height: 12),
                  Text(
                    'No analyzed songs yet',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Add an audio file to create your first practice sheet.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: onAddSong,
                    icon: const Icon(Icons.add),
                    label: const Text('Add a song'),
                  ),
                ],
              ),
            ),
          )
        else ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  'Previously analyzed',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Text(
                '${sessions.length} saved',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: _UploadPalette.secondaryText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (final session in sessions)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _SavedPracticeCard(
                session: session,
                onOpen: () => onOpen(session),
              ),
            ),
        ],
      ],
    );
  }
}

class _TunerHome extends StatelessWidget {
  const _TunerHome();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Tuner', style: Theme.of(context).textTheme.displayMedium),
          const SizedBox(height: 8),
          Text(
            'Tune before you play.',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
              color: _UploadPalette.secondaryText,
            ),
          ),
          const Spacer(),
          const Icon(Icons.graphic_eq_rounded, size: 58),
          const SizedBox(height: 20),
          Text(
            '—  E  —',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.displayLarge,
          ),
          const SizedBox(height: 12),
          Text(
            'Microphone tuner coming next',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            'The navigation is ready; pitch detection still needs microphone permission and audio processing.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: _UploadPalette.secondaryText,
            ),
          ),
          const Spacer(flex: 2),
        ],
      ),
    );
  }
}

/// True on iOS/macOS, so source badges can use the Cupertino icon set and
/// otherwise fall back to Material icons for Android and other platforms.
bool _prefersCupertinoIcons(BuildContext context) {
  final platform = Theme.of(context).platform;
  return platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
}

class _SongSourceGrid extends StatelessWidget {
  const _SongSourceGrid({
    required this.compact,
    required this.onFiles,
    required this.onYouTube,
    required this.onCameraRoll,
    required this.onRecord,
    required this.onShazam,
  });

  final bool compact;
  final VoidCallback onFiles;
  final VoidCallback onYouTube;
  final VoidCallback onCameraRoll;
  final VoidCallback onRecord;
  final VoidCallback onShazam;

  @override
  Widget build(BuildContext context) {
    final cupertino = _prefersCupertinoIcons(context);
    final sources = [
      _SongSource(
        key: 'youtubeSource',
        title: 'YouTube',
        description: 'Pick any song or video',
        onTap: onYouTube,
        badgeBuilder: (size) => _AssetBadge(
          'assets/icons/source_providers/youtube_icon.png',
          size: size,
        ),
      ),
      _SongSource(
        key: 'cameraRollSource',
        title: 'Camera Roll',
        description: 'Upload a video from your photo library',
        onTap: onCameraRoll,
        badgeBuilder: (size) => _IconBadge(
          icon: cupertino ? CupertinoIcons.photo : Icons.photo_library_rounded,
          background: _UploadPalette.primaryText,
          foreground: _UploadPalette.card,
          size: size,
        ),
      ),
      _SongSource(
        key: 'filesSource',
        title: 'Files',
        description: 'Upload from local files',
        onTap: onFiles,
        badgeBuilder: (size) => _IconBadge(
          icon: cupertino ? CupertinoIcons.folder_fill : Icons.folder_rounded,
          background: _UploadPalette.primaryText,
          foreground: const Color(0xFF3A7BD5),
          size: size,
        ),
      ),
      _SongSource(
        key: 'recordSource',
        title: 'Record',
        description: 'Record your own audio',
        onTap: onRecord,
        badgeBuilder: (size) => _IconBadge(
          icon: cupertino ? CupertinoIcons.mic_fill : Icons.mic_rounded,
          foreground: Colors.white,
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFFFF6A3D), Color(0xFFE53935)],
          ),
          size: size,
        ),
      ),
      _SongSource(
        key: 'shazamSource',
        title: 'Shazam',
        description: 'Identify a song with Shazam',
        onTap: onShazam,
        badgeBuilder: (size) => _ShazamBadge(size: size),
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GridView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: sources.length,
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: compact ? 0.9 : 1.05,
          ),
          itemBuilder: (context, index) => _SourceCard(source: sources[index]),
        ),
        const SizedBox(height: 12),
        Text(
          'Phone audio: WAV · MP3 · M4A',
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: _UploadPalette.secondaryText,
          ),
        ),
      ],
    );
  }
}

class _SongSource {
  const _SongSource({
    required this.key,
    required this.title,
    required this.description,
    required this.onTap,
    required this.badgeBuilder,
  });

  final String key;
  final String title;
  final String description;
  final VoidCallback onTap;

  /// Builds this source's badge at the given square size. Sizing is driven
  /// by the card's own LayoutBuilder (see `_SourceCard`) so the badge still
  /// shrinks to fit a tight/compact card instead of overflowing it.
  final Widget Function(double size) badgeBuilder;
}

const _badgeRadius = 16.0;

/// A source's square app-icon-style mark. Each source owns its own badge so
/// brand marks (an image, or Shazam's circular mark) and generic utility
/// icons (Camera Roll, Files, Record) can each use the right shape.
class _AssetBadge extends StatelessWidget {
  const _AssetBadge(this.assetPath, {required this.size});

  final String assetPath;
  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Image.asset(assetPath, fit: BoxFit.contain),
    );
  }
}

class _IconBadge extends StatelessWidget {
  const _IconBadge({
    required this.icon,
    required this.foreground,
    required this.size,
    this.background,
    this.gradient,
  }) : assert(
         background != null || gradient != null,
         'An icon badge needs either a solid background or a gradient.',
       );

  final IconData icon;
  final Color foreground;
  final double size;
  final Color? background;
  final Gradient? gradient;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: background,
        gradient: gradient,
        borderRadius: BorderRadius.circular(_badgeRadius),
      ),
      child: Icon(icon, color: foreground, size: size * 0.46),
    );
  }
}

/// A simple stand-in mark for Shazam: its real logo is a trademarked asset
/// we don't ship, so this uses only its brand colour and a generic listening
/// glyph rather than reproducing the logo itself.
class _ShazamBadge extends StatelessWidget {
  const _ShazamBadge({required this.size});

  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: const BoxDecoration(
        color: Color(0xFF0088FF),
        shape: BoxShape.circle,
      ),
      child: Icon(
        Icons.graphic_eq_rounded,
        color: Colors.white,
        size: size * 0.5,
      ),
    );
  }
}

class _SourceCard extends StatelessWidget {
  const _SourceCard({required this.source});

  final _SongSource source;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: _UploadPalette.card,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ChordSyncRadii.card),
        side: const BorderSide(color: _UploadPalette.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        key: ValueKey(source.key),
        onTap: source.onTap,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final tight = constraints.maxHeight < 180;
            final badgeSize = tight ? 46.0 : 54.0;
            return Padding(
              padding: EdgeInsets.all(tight ? 8 : 16),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  source.badgeBuilder(badgeSize),
                  SizedBox(height: tight ? 6 : 11),
                  Text(
                    source.title,
                    style: tight
                        ? Theme.of(context).textTheme.titleSmall
                        : Theme.of(context).textTheme.titleMedium,
                  ),
                  SizedBox(height: tight ? 2 : 3),
                  Text(
                    source.description,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: _UploadPalette.secondaryText,
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _AnalysisJourney extends StatefulWidget {
  const _AnalysisJourney({required this.controller, required this.onCancel});

  final AudioImportController controller;
  final VoidCallback onCancel;

  @override
  State<_AnalysisJourney> createState() => _AnalysisJourneyState();
}

class _AnalysisJourneyState extends State<_AnalysisJourney>
    with SingleTickerProviderStateMixin {
  late final AnimationController _spin;

  @override
  void initState() {
    super.initState();
    _spin = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 7),
    )..repeat();
  }

  @override
  void dispose() {
    _spin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final phase = widget.controller.phase;
    final activeStep = switch (phase) {
      AudioImportPhase.uploading => 0,
      AudioImportPhase.queued => 1,
      AudioImportPhase.processing => 2,
      AudioImportPhase.preparing => 3,
      _ => 0,
    };
    final uploadProgress = widget.controller.uploadProgress;
    final label = switch (phase) {
      AudioImportPhase.uploading when uploadProgress != null =>
        'Uploading your song… ${(uploadProgress * 100).round()}%',
      AudioImportPhase.uploading => 'Uploading your song…',
      AudioImportPhase.queued => 'Waiting to analyze…',
      AudioImportPhase.processing => 'Analyzing your song…',
      AudioImportPhase.preparing => 'Preparing your practice sheet…',
      _ => 'Preparing your song…',
    };
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 28),
          child: Column(
            children: [
              const Spacer(flex: 2),
              RotationTransition(turns: _spin, child: const _RecordMark()),
              const Spacer(flex: 2),
              Semantics(
                liveRegion: true,
                label: label,
                child: Text(
                  label,
                  key: const ValueKey('analysisJourneyLabel'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              const SizedBox(height: 24),
              _JourneySteps(activeStep: activeStep),
              const SizedBox(height: 22),
              OutlinedButton.icon(
                key: const ValueKey('cancelAnalysisButton'),
                onPressed: widget.onCancel,
                icon: const Icon(Icons.close),
                label: const Text('Stop waiting'),
              ),
              const SizedBox(height: 16),
              Text(
                'You can leave this screen; analysis continues on the server.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: _UploadPalette.secondaryText,
                ),
              ),
              const Spacer(),
            ],
          ),
        ),
      ),
    );
  }
}

class _RecordMark extends StatelessWidget {
  const _RecordMark();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 190,
      height: 190,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: ChordSyncColors.brandDark,
        border: Border.all(color: ChordSyncColors.brandAccent, width: 2),
        boxShadow: const [
          BoxShadow(
            color: Color(0x332B1B12),
            blurRadius: 28,
            offset: Offset(0, 14),
          ),
        ],
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (final size in [156.0, 128.0, 98.0, 68.0])
            Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0x337F695A)),
              ),
            ),
          Container(
            width: 48,
            height: 48,
            decoration: const BoxDecoration(
              color: ChordSyncColors.honey,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.music_note,
              color: ChordSyncColors.brandDark,
            ),
          ),
        ],
      ),
    );
  }
}

class _JourneySteps extends StatelessWidget {
  const _JourneySteps({required this.activeStep});

  final int activeStep;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(4, (index) {
        final complete = index < activeStep;
        final active = index == activeStep;
        return Row(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 280),
              width: active ? 20 : 10,
              height: 10,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(9),
                color: complete
                    ? ChordSyncColors.success
                    : active
                    ? ChordSyncColors.brand
                    : ChordSyncColors.border,
              ),
              child: complete
                  ? const Icon(Icons.check, size: 9, color: Colors.white)
                  : null,
            ),
            if (index < 3)
              Container(
                width: 28,
                height: 2,
                color: complete
                    ? ChordSyncColors.success
                    : ChordSyncColors.border,
              ),
          ],
        );
      }),
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
                          color: _UploadPalette.secondaryText,
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

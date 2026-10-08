import 'dart:async';

import 'package:flutter/material.dart';

import '../../analysis/application/analyzed_practice_session.dart';
import '../application/practice_audio_player.dart';
import '../application/practice_playback_controller.dart';
import '../application/practice_playback_status.dart';
import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_synchronizer.dart';
import '../application/practice_session_factory.dart';
import '../data/playback_state.dart';
import '../data/chord_transposition.dart';
import '../data/shared_timeline_asset_loader.dart';
import '../data/shared_timeline.dart';
import 'chord_diagram_strip.dart';
import 'practice_stage_colors.dart';
import 'song_sheet_lyrics.dart';

class PracticeScreen extends StatefulWidget {
  const PracticeScreen({
    super.key,
    this.audioPlayer,
    this.analyzedSession,
    this.sessionFactory,
  }) : assert(
         audioPlayer == null || analyzedSession == null,
         'Provide either a fixture audio player or an analyzed session.',
       );

  final PracticeAudioPlayer? audioPlayer;
  final AnalyzedPracticeSession? analyzedSession;
  final PracticeSessionFactory? sessionFactory;

  @override
  State<PracticeScreen> createState() => _PracticeScreenState();
}

class _PracticeScreenState extends State<PracticeScreen> {
  PracticeAudioPlayer? _audioPlayer;
  PracticePlaybackController? _controller;
  PracticePlaybackSynchronizer? _synchronizer;
  PreparedPracticeSession? _preparedSession;
  SharedTimeline? _timeline;
  double _maximumPosition = 0;
  bool _isLoaded = false;
  Object? _loadError;
  int _capoFret = 0;

  @override
  void initState() {
    super.initState();
    _loadPractice();
  }

  Future<void> _loadPractice() async {
    try {
      final analyzedSession = widget.analyzedSession;
      if (analyzedSession != null) {
        await _loadAnalyzedPractice(analyzedSession);
        return;
      }

      final timeline = await SharedTimelineAssetLoader.load();
      final audioPlayer = widget.audioPlayer ?? JustAudioPracticeAudioPlayer();
      final controller = PracticePlaybackController(timeline);
      final synchronizer = PracticePlaybackSynchronizer(
        audioPlayer: audioPlayer,
        playbackController: controller,
        onPositionChanged: _refreshFromAudio,
        onStatusChanged: _refreshFromAudio,
        onLoopChanged: _refreshFromAudio,
      );

      _audioPlayer = audioPlayer;
      _controller = controller;
      _synchronizer = synchronizer;
      _timeline = timeline;
      synchronizer.start();
      await audioPlayer.load();

      if (!mounted) return;
      final audioDuration = audioPlayer.duration;
      setState(() {
        _maximumPosition = audioDuration == null
            ? timeline.endTime
            : audioDuration.inMicroseconds / Duration.microsecondsPerSecond;
        _isLoaded = true;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() => _loadError = error);
    }
  }

  Future<void> _loadAnalyzedPractice(
    AnalyzedPracticeSession analyzedSession,
  ) async {
    final prepared = await (widget.sessionFactory ?? PracticeSessionFactory())
        .create(
          analyzedSession,
          onPositionChanged: _refreshFromAudio,
          onStatusChanged: _refreshFromAudio,
          onLoopChanged: _refreshFromAudio,
        );
    if (!mounted) {
      await prepared.dispose();
      return;
    }

    _preparedSession = prepared;
    _audioPlayer = prepared.audioPlayer;
    _controller = prepared.playbackController;
    _synchronizer = prepared.synchronizer;
    _timeline = analyzedSession.timeline;
    final audioDuration = prepared.audioPlayer.duration;
    setState(() {
      _maximumPosition = audioDuration == null
          ? analyzedSession.timeline.endTime
          : audioDuration.inMicroseconds / Duration.microsecondsPerSecond;
      _isLoaded = true;
    });
  }

  void _refreshFromAudio() {
    if (mounted) setState(() {});
  }

  Future<void> _runAudioAction(Future<void> Function() action) async {
    try {
      await action();
    } on Object catch (error) {
      if (mounted) setState(() => _loadError = error);
    }
  }

  Future<void> _seek(double seconds) {
    return _runAudioAction(
      () => _synchronizer!.seek(
        Duration(
          microseconds: (seconds * Duration.microsecondsPerSecond).round(),
        ),
      ),
    );
  }

  Future<void> _setSpeed(double speed) async {
    await _runAudioAction(() async {
      await _synchronizer!.setSpeed(speed);
    });
    if (mounted) setState(() {});
  }

  String _formatLoopPosition(Duration position) {
    final seconds = position.inMicroseconds / Duration.microsecondsPerSecond;
    return '${seconds.toStringAsFixed(1)} s';
  }

  String _loopRangeLabel(PracticePlaybackSynchronizer synchronizer) {
    final start = synchronizer.loopStart;
    final end = synchronizer.loopEnd;
    if (start == null) return 'Not set';
    if (end == null) return 'A: ${_formatLoopPosition(start)} | B: —';
    return '${_formatLoopPosition(start)} → ${_formatLoopPosition(end)}';
  }

  @override
  void dispose() {
    final preparedSession = _preparedSession;
    if (preparedSession != null) {
      unawaited(preparedSession.dispose());
      super.dispose();
      return;
    }
    final synchronizer = _synchronizer;
    if (synchronizer != null) {
      unawaited(synchronizer.dispose());
    } else {
      unawaited(_audioPlayer?.dispose());
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final baseTheme = Theme.of(context);
    final stageScheme = baseTheme.colorScheme.copyWith(
      brightness: Brightness.dark,
      primary: PracticeStageColors.amber,
      onPrimary: PracticeStageColors.background,
      secondary: PracticeStageColors.amberBright,
      surface: PracticeStageColors.surface,
      onSurface: PracticeStageColors.textPrimary,
      outline: PracticeStageColors.border,
      outlineVariant: PracticeStageColors.border,
    );
    final stageTheme = baseTheme.copyWith(
      colorScheme: stageScheme,
      scaffoldBackgroundColor: PracticeStageColors.background,
      textTheme: baseTheme.textTheme.apply(
        bodyColor: PracticeStageColors.textPrimary,
        displayColor: PracticeStageColors.textPrimary,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: PracticeStageColors.background,
        foregroundColor: PracticeStageColors.textPrimary,
        elevation: 0,
      ),
      cardTheme: baseTheme.cardTheme.copyWith(
        color: PracticeStageColors.surface,
        surfaceTintColor: Colors.transparent,
      ),
      dividerColor: PracticeStageColors.border,
      sliderTheme: baseTheme.sliderTheme.copyWith(
        activeTrackColor: PracticeStageColors.amberBright,
        inactiveTrackColor: PracticeStageColors.border,
        thumbColor: PracticeStageColors.amberBright,
        trackHeight: 3,
        overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
        thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
      ),
    );

    return Theme(
      data: stageTheme,
      child: Builder(
        builder: (stageContext) => Scaffold(body: _buildBody(stageContext)),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loadError != null) {
      return const Center(child: Text('Unable to load practice audio.'));
    }

    final controller = _controller;
    final synchronizer = _synchronizer;
    if (!_isLoaded || controller == null || synchronizer == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final state = controller.state;
    final timeline = _timeline!;
    final displayTimeline = ChordTransposition.timelineForCapo(
      timeline,
      _capoFret,
    );
    final songChords = ChordTransposition.songChords(
      timeline,
      capoFret: _capoFret,
    );
    final isBeforePlayback = controller.position == Duration.zero;
    return SafeArea(
      child: Column(
        children: [
          _SheetHeader(
            title: widget.analyzedSession?.title ?? 'Practice sheet',
            subtitle: _headerSubtitle(),
            status: synchronizer.status,
            loopRange: _loopRangeLabel(synchronizer),
            isLooping: synchronizer.loop?.enabled == true,
            onSetLoopStart: () =>
                synchronizer.setLoopStart(controller.position),
            onSetLoopEnd: () => synchronizer.setLoopEnd(controller.position),
            onToggleLoop: () {
              if (synchronizer.loop?.enabled == true) {
                synchronizer.disableLoop();
              } else {
                synchronizer.enableLoop();
              }
            },
            onClearLoop: synchronizer.clearLoop,
            capoFret: _capoFret,
            onCapoPressed: () => _showCapoSettings(timeline),
            onSimplifyPressed: () {
              setState(() {
                _capoFret = ChordTransposition.recommendedCapo(timeline);
              });
            },
          ),
          if (state.isMusicOnly)
            const _MusicOnlyChordFocus()
          else
            ChordDiagramStrip(
              previousChord: state.previousChord == null
                  ? null
                  : ChordTransposition.forCapo(state.previousChord!, _capoFret),
              currentChord: ChordTransposition.forCapo(
                state.currentChord,
                _capoFret,
              ),
              nextChord: state.nextChord == null
                  ? null
                  : ChordTransposition.forCapo(state.nextChord!, _capoFret),
              progression: isBeforePlayback
                  ? songChords
                  : state.chordProgression
                        .map(
                          (chord) =>
                              ChordTransposition.forCapo(chord, _capoFret),
                        )
                        .toList(),
              chordProgress: state.chordProgress,
              chordStart: state.currentChordStart,
              showAllChords: isBeforePlayback,
            ),
          const Divider(height: 1, thickness: 1),
          Expanded(
            child: Container(
              key: const ValueKey('lyricsSection'),
              color: PracticeStageColors.background,
              child: state.isMusicOnly
                  ? _MusicOnlyLyrics(state: state)
                  : SongSheetLyrics(
                      timeline: displayTimeline,
                      playbackTime: state.playbackTime,
                    ),
            ),
          ),
          _TransportBar(
            status: synchronizer.status,
            position:
                controller.position.inMicroseconds /
                Duration.microsecondsPerSecond,
            maximumPosition: _maximumPosition,
            speed: synchronizer.speed,
            chordLabel: state.isMusicOnly
                ? 'Music only'
                : 'Current ${ChordTransposition.forCapo(state.currentChord, _capoFret)}',
            canGoPrevious: synchronizer.canSeekToPreviousBar,
            canGoNext: synchronizer.canSeekToNextBar,
            onPrevious: () => _runAudioAction(() async {
              await synchronizer.seekToPreviousBar();
            }),
            onPlayPause: () => _runAudioAction(
              synchronizer.status == PracticePlaybackStatus.playing
                  ? synchronizer.pause
                  : synchronizer.play,
            ),
            onNext: () => _runAudioAction(() async {
              await synchronizer.seekToNextBar();
            }),
            onSeek: _seek,
            onSpeedChanged: _setSpeed,
          ),
        ],
      ),
    );
  }

  Future<void> _showCapoSettings(SharedTimeline timeline) async {
    var selected = _capoFret;
    final recommended = ChordTransposition.recommendedCapo(timeline);
    final result = await showModalBottomSheet<int>(
      context: context,
      backgroundColor: PracticeStageColors.surface,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) {
          final chords = ChordTransposition.songChords(
            timeline,
            capoFret: selected,
          );
          return SafeArea(
            child: DefaultTextStyle.merge(
              style: const TextStyle(color: Colors.white),
              child: IconTheme.merge(
                data: const IconThemeData(color: Colors.white),
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Capo settings',
                        style: Theme.of(
                          context,
                        ).textTheme.titleLarge?.copyWith(color: Colors.white),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Recommended: ${recommended == 0 ? 'No capo' : 'fret $recommended'}',
                      ),
                      const SizedBox(height: 14),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            selected == 0 ? 'No capo' : 'Capo: fret $selected',
                          ),
                          Row(
                            children: [
                              IconButton(
                                tooltip: 'Lower capo',
                                color: Colors.white,
                                disabledColor: Colors.white54,
                                onPressed: selected == 0
                                    ? null
                                    : () => setModalState(() => selected--),
                                icon: const Icon(Icons.remove),
                              ),
                              IconButton(
                                tooltip: 'Raise capo',
                                color: Colors.white,
                                disabledColor: Colors.white54,
                                onPressed: selected == 11
                                    ? null
                                    : () => setModalState(() => selected++),
                                icon: const Icon(Icons.add),
                              ),
                            ],
                          ),
                        ],
                      ),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text('Shapes: ${chords.join('  ·  ')}'),
                      ),
                      const SizedBox(height: 18),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          style: FilledButton.styleFrom(
                            foregroundColor: Colors.white,
                            backgroundColor: PracticeStageColors.surfaceRaised,
                          ),
                          onPressed: () => Navigator.pop(context, selected),
                          child: const Text('Apply'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
    if (result != null && mounted) setState(() => _capoFret = result);
  }

  String _headerSubtitle() {
    final timeline = _timeline;
    if (timeline == null) return '—';
    return '${timeline.bpm.toStringAsFixed(0)} BPM · '
        '${timeline.beatsPerBar}/4';
  }
}

/// Song identity plus the A–B loop tools, styled as the pill row from the
/// practice sheet design.
class _SheetHeader extends StatelessWidget {
  const _SheetHeader({
    required this.title,
    required this.subtitle,
    required this.status,
    required this.loopRange,
    required this.isLooping,
    required this.onSetLoopStart,
    required this.onSetLoopEnd,
    required this.onToggleLoop,
    required this.onClearLoop,
    required this.capoFret,
    required this.onCapoPressed,
    required this.onSimplifyPressed,
  });

  final String title;
  final String subtitle;
  final PracticePlaybackStatus status;
  final String loopRange;
  final bool isLooping;
  final VoidCallback onSetLoopStart;
  final VoidCallback onSetLoopEnd;
  final VoidCallback onToggleLoop;
  final VoidCallback onClearLoop;
  final int capoFret;
  final VoidCallback onCapoPressed;
  final VoidCallback onSimplifyPressed;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Container(
      key: const ValueKey('fixedChordHeader'),
      color: PracticeStageColors.background,
      padding: const EdgeInsets.fromLTRB(4, 4, 8, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const BackButton(),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      key: const ValueKey('songSheetTitle'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w700,
                        height: 1.15,
                      ),
                    ),
                    Text(
                      subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.labelMedium?.copyWith(
                        color: PracticeStageColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                status.label,
                key: const ValueKey('playbackStatusValue'),
                style: textTheme.labelMedium?.copyWith(
                  color: PracticeStageColors.textSecondary,
                ),
              ),
              IconButton(
                key: const ValueKey('clearLoopButton'),
                onPressed: onClearLoop,
                tooltip: 'Clear Loop',
                visualDensity: VisualDensity.compact,
                color: PracticeStageColors.textSecondary,
                icon: const Icon(Icons.more_horiz, size: 22),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                _ToolPill(
                  label: capoFret == 0 ? 'Capo' : 'Capo $capoFret',
                  icon: Icons.tune,
                  isActive: capoFret > 0,
                  onPressed: onCapoPressed,
                ),
                const SizedBox(width: 8),
                _ToolPill(
                  label: 'Simplify',
                  icon: Icons.star_rounded,
                  onPressed: onSimplifyPressed,
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Row(
            key: const ValueKey('practiceToolsSection'),
            children: [
              Expanded(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Row(
                    children: [
                      _ToolPill(
                        label: isLooping ? 'Loop Off' : 'Loop On',
                        icon: Icons.repeat_rounded,
                        isActive: isLooping,
                        onPressed: onToggleLoop,
                      ),
                      const SizedBox(width: 8),
                      _ToolPill(
                        label: 'Set A',
                        icon: Icons.flag_outlined,
                        onPressed: onSetLoopStart,
                      ),
                      const SizedBox(width: 8),
                      _ToolPill(
                        label: 'Set B',
                        icon: Icons.outlined_flag_rounded,
                        onPressed: onSetLoopEnd,
                      ),
                    ],
                  ),
                ),
              ),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 124),
                child: Text(
                  loopRange,
                  key: const ValueKey('loopRangeValue'),
                  maxLines: 1,
                  textAlign: TextAlign.right,
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.labelSmall?.copyWith(
                    color: PracticeStageColors.textFaint,
                  ),
                ),
              ),
              const SizedBox(width: 4),
            ],
          ),
        ],
      ),
    );
  }
}

class _ToolPill extends StatelessWidget {
  const _ToolPill({
    required this.label,
    required this.icon,
    required this.onPressed,
    this.isActive = false,
  });

  final String label;
  final IconData icon;
  final VoidCallback onPressed;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: isActive ? PracticeStageColors.surfaceRaised : Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(20),
        side: BorderSide(
          color: isActive
              ? PracticeStageColors.textSecondary
              : PracticeStageColors.border,
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 15,
                color: isActive
                    ? PracticeStageColors.textPrimary
                    : PracticeStageColors.textSecondary,
              ),
              const SizedBox(width: 6),
              Text(
                label,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: isActive
                      ? PracticeStageColors.textPrimary
                      : PracticeStageColors.textSecondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Rounded transport pill: bar navigation, play/pause, scrub line, and the
/// speed control kept as a compact circular button.
class _TransportBar extends StatelessWidget {
  const _TransportBar({
    required this.status,
    required this.position,
    required this.maximumPosition,
    required this.speed,
    required this.chordLabel,
    required this.canGoPrevious,
    required this.canGoNext,
    required this.onPrevious,
    required this.onPlayPause,
    required this.onNext,
    required this.onSeek,
    required this.onSpeedChanged,
  });

  final PracticePlaybackStatus status;
  final double position;
  final double maximumPosition;
  final double speed;
  final String chordLabel;
  final bool canGoPrevious;
  final bool canGoNext;
  final VoidCallback onPrevious;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;
  final ValueChanged<double> onSeek;
  final ValueChanged<double> onSpeedChanged;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final isPlaying = status == PracticePlaybackStatus.playing;
    final playLabel = status == PracticePlaybackStatus.completed
        ? 'Replay'
        : 'Play';

    return Container(
      key: const ValueKey('transportSection'),
      color: PracticeStageColors.background,
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  chordLabel,
                  key: const ValueKey('persistentChordValue'),
                  overflow: TextOverflow.ellipsis,
                  style: textTheme.labelSmall?.copyWith(
                    color: PracticeStageColors.textFaint,
                  ),
                ),
              ),
              Text(
                '${position.toStringAsFixed(1)} s',
                key: const ValueKey('positionValue'),
                style: textTheme.labelSmall?.copyWith(
                  color: PracticeStageColors.textFaint,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: Container(
                  height: 60,
                  decoration: BoxDecoration(
                    color: PracticeStageColors.surface,
                    border: Border.all(color: PracticeStageColors.border),
                    borderRadius: BorderRadius.circular(30),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: Row(
                    children: [
                      IconButton(
                        key: const ValueKey('previousBarButton'),
                        onPressed: canGoPrevious ? onPrevious : null,
                        tooltip: 'Previous bar',
                        iconSize: 20,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.textSecondary,
                        icon: const Icon(Icons.skip_previous_rounded),
                      ),
                      IconButton(
                        onPressed: onPlayPause,
                        tooltip: isPlaying ? 'Pause' : playLabel,
                        iconSize: 30,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.textPrimary,
                        icon: Icon(
                          isPlaying
                              ? Icons.pause_rounded
                              : Icons.play_arrow_rounded,
                        ),
                      ),
                      IconButton(
                        key: const ValueKey('nextBarButton'),
                        onPressed: canGoNext ? onNext : null,
                        tooltip: 'Next bar',
                        iconSize: 20,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.textSecondary,
                        icon: const Icon(Icons.skip_next_rounded),
                      ),
                      Expanded(
                        child: SliderTheme(
                          data: SliderTheme.of(context),
                          child: Slider(
                            value: position.clamp(0, maximumPosition),
                            min: 0,
                            max: maximumPosition,
                            onChanged: onSeek,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 10),
              _SpeedSelector(speed: speed, onChanged: onSpeedChanged),
            ],
          ),
        ],
      ),
    );
  }
}

class _SpeedSelector extends StatelessWidget {
  const _SpeedSelector({required this.speed, required this.onChanged});

  final double speed;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleSmall?.copyWith(
      color: PracticeStageColors.textPrimary,
      fontWeight: FontWeight.w700,
    );
    return Container(
      width: 60,
      height: 60,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: PracticeStageColors.surface,
        border: Border.all(color: PracticeStageColors.border),
        shape: BoxShape.circle,
      ),
      child: DropdownButtonHideUnderline(
        child: SizedBox(
          width: 46,
          child: DropdownButton<double>(
            key: const ValueKey('speedSelector'),
            value: speed,
            isDense: true,
            isExpanded: true,
            alignment: Alignment.center,
            icon: const SizedBox.shrink(),
            dropdownColor: PracticeStageColors.surfaceRaised,
            borderRadius: BorderRadius.circular(14),
            onChanged: (value) {
              if (value != null) onChanged(value);
            },
            selectedItemBuilder: (context) => [
              for (final option in PracticePlaybackSpeeds.supported)
                Center(
                  child: Text(
                    PracticePlaybackSpeeds.label(option),
                    style: style,
                  ),
                ),
            ],
            items: [
              for (final option in PracticePlaybackSpeeds.supported)
                DropdownMenuItem(
                  value: option,
                  child: Text(
                    PracticePlaybackSpeeds.label(option),
                    textAlign: TextAlign.center,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MusicOnlyChordFocus extends StatelessWidget {
  const _MusicOnlyChordFocus();

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label: 'No chord to play',
      child: SizedBox(
        key: const ValueKey('musicOnlyChordFocus'),
        height: ChordDiagramStrip.compactHeight,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.music_note_rounded,
                size: 32,
                color: PracticeStageColors.amber,
              ),
              const SizedBox(height: 8),
              Text(
                'NO CHORD TO PLAY',
                key: const ValueKey('musicOnlyChordMessage'),
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: PracticeStageColors.textPrimary,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MusicOnlyLyrics extends StatelessWidget {
  const _MusicOnlyLyrics({required this.state});

  final PlaybackState state;

  @override
  Widget build(BuildContext context) {
    const word = 'MUSIC';
    final beatProgress = state.beatProgress ?? 0.0;
    final revealedLetters = (beatProgress * word.length).floor() + 1;
    final pulse = 1.0 + (1.0 - beatProgress) * (state.isDownbeat ? 0.06 : 0.03);

    return Semantics(
      container: true,
      label: 'Music only section',
      value: '${((state.musicOnlyProgress ?? 0) * 100).round()} percent',
      child: Center(
        child: Transform.scale(
          scale: pulse,
          child: Row(
            key: const ValueKey('musicOnlyLyrics'),
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                '♪ ',
                style: TextStyle(
                  color: PracticeStageColors.amber,
                  fontSize: 30,
                ),
              ),
              for (var index = 0; index < word.length; index++)
                Text(
                  word[index],
                  key: ValueKey('musicLetter$index'),
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    color: index < revealedLetters
                        ? PracticeStageColors.amberBright
                        : PracticeStageColors.textFaint,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2,
                  ),
                ),
              const Text(
                ' ♪',
                style: TextStyle(
                  color: PracticeStageColors.amber,
                  fontSize: 30,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'dart:async';

import 'package:flutter/material.dart';

import '../../analysis/application/analyzed_practice_session.dart';
import '../application/practice_audio_player.dart';
import '../application/practice_playback_controller.dart';
import '../application/practice_playback_status.dart';
import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_synchronizer.dart';
import '../application/practice_session_factory.dart';
import '../data/shared_timeline_asset_loader.dart';
import '../data/shared_timeline.dart';
import 'chord_diagram.dart';
import 'practice_beat_indicator.dart';
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
        activeTrackColor: PracticeStageColors.amber,
        inactiveTrackColor: PracticeStageColors.border,
        thumbColor: PracticeStageColors.amberBright,
      ),
    );

    return Theme(
      data: stageTheme,
      child: Builder(
        builder: (stageContext) => Scaffold(body: _buildBody(stageContext)),
      ),
    );
  }

  Widget? _buildTransportBar(BuildContext context) {
    final controller = _controller;
    final synchronizer = _synchronizer;
    if (!_isLoaded || controller == null || synchronizer == null) return null;
    final status = synchronizer.status;
    final state = controller.state;
    final position =
        controller.position.inMicroseconds / Duration.microsecondsPerSecond;
    return Container(
      key: const ValueKey('transportSection'),
      color: PracticeStageColors.background,
      padding: const EdgeInsets.fromLTRB(14, 6, 14, 10),
      child: Center(
        heightFactor: 1,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Current ${state.currentChord}',
                      key: const ValueKey('persistentChordValue'),
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: PracticeStageColors.textSecondary,
                      ),
                    ),
                  ),
                  Text(
                    status.label,
                    key: const ValueKey('playbackStatusValue'),
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                  const SizedBox(width: 10),
                  Text(
                    '${position.toStringAsFixed(1)} s',
                    key: const ValueKey('positionValue'),
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              ),
              const SizedBox(height: 5),
              Container(
                decoration: BoxDecoration(
                  color: PracticeStageColors.surface,
                  border: Border.all(color: PracticeStageColors.border),
                  borderRadius: BorderRadius.circular(32),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Row(
                  children: [
                    _TransportControls(
                      status: status,
                      canGoPrevious: synchronizer.canSeekToPreviousBar,
                      canGoNext: synchronizer.canSeekToNextBar,
                      onPrevious: () => _runAudioAction(() async {
                        await synchronizer.seekToPreviousBar();
                      }),
                      onPlayPause: () => _runAudioAction(
                        status == PracticePlaybackStatus.playing
                            ? synchronizer.pause
                            : synchronizer.play,
                      ),
                      onNext: () => _runAudioAction(() async {
                        await synchronizer.seekToNextBar();
                      }),
                    ),
                    Expanded(
                      child: Slider(
                        value: position.clamp(0, _maximumPosition),
                        min: 0,
                        max: _maximumPosition,
                        onChanged: _seek,
                      ),
                    ),
                    _SpeedSelector(
                      speed: synchronizer.speed,
                      onChanged: _setSpeed,
                    ),
                  ],
                ),
              ),
              Container(
                key: const ValueKey('practiceToolsSection'),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        _loopRangeLabel(synchronizer),
                        key: const ValueKey('loopRangeValue'),
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.labelSmall,
                      ),
                    ),
                    _CompactAction(
                      label: 'Set A',
                      onPressed: () =>
                          synchronizer.setLoopStart(controller.position),
                    ),
                    _CompactAction(
                      label: 'Set B',
                      onPressed: () =>
                          synchronizer.setLoopEnd(controller.position),
                    ),
                    _CompactAction(
                      label: synchronizer.loop?.enabled == true
                          ? 'Loop Off'
                          : 'Loop On',
                      onPressed: () {
                        if (synchronizer.loop?.enabled == true) {
                          synchronizer.disableLoop();
                        } else {
                          synchronizer.enableLoop();
                        }
                      },
                    ),
                    IconButton(
                      onPressed: synchronizer.clearLoop,
                      tooltip: 'Clear Loop',
                      visualDensity: VisualDensity.compact,
                      constraints: const BoxConstraints.tightFor(
                        width: 30,
                        height: 34,
                      ),
                      padding: EdgeInsets.zero,
                      icon: const Icon(Icons.close, size: 18),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loadError != null) {
      return const Center(child: Text('Unable to load practice audio.'));
    }

    final controller = _controller;
    if (!_isLoaded || controller == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final state = controller.state;
    return SafeArea(
      child: Column(
        children: [
          Container(
            key: const ValueKey('fixedChordHeader'),
            padding: const EdgeInsets.fromLTRB(16, 5, 16, 6),
            decoration: const BoxDecoration(
              color: PracticeStageColors.background,
              border: Border(
                bottom: BorderSide(color: PracticeStageColors.border),
              ),
            ),
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: Column(
                  children: [
                    Row(
                      children: [
                        const BackButton(),
                        Expanded(
                          child: Text(
                            widget.analyzedSession?.title ?? 'Practice sheet',
                            key: const ValueKey('songSheetTitle'),
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.titleLarge,
                          ),
                        ),
                        Text(
                          '${_timeline?.bpm.toStringAsFixed(0) ?? '—'} BPM',
                          style: Theme.of(context).textTheme.labelMedium
                              ?.copyWith(
                                color: PracticeStageColors.textSecondary,
                              ),
                        ),
                      ],
                    ),
                    _ChordFocus(
                      previousChord: state.previousChord,
                      currentChord: state.currentChord,
                      nextChord: state.nextChord,
                      chordProgress: state.chordProgress,
                      chordStart: state.currentChordStart,
                    ),
                    const Divider(height: 10),
                    Column(
                      key: const ValueKey('rhythmSection'),
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            _CompactMetric(
                              label: 'Bar',
                              value: state.currentBarNumber?.toString() ?? '—',
                              valueKey: const ValueKey('barValue'),
                            ),
                            _CompactMetric(
                              label: 'Beat',
                              value:
                                  '${state.beatNumber?.toString() ?? '—'} / '
                                  '${state.beatsPerBar}',
                              valueKey: const ValueKey('beatValue'),
                            ),
                            _CompactMetric(
                              label: 'Downbeat',
                              value: state.isDownbeat ? 'Yes' : 'No',
                              valueKey: const ValueKey('downbeatValue'),
                            ),
                          ],
                        ),
                        SizedBox(
                          height: 28,
                          child: PracticeBeatIndicator(
                            beatNumber: state.beatNumber,
                            beatsPerBar: state.beatsPerBar,
                            isDownbeat: state.isDownbeat,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(
                      key: const ValueKey('progressionSection'),
                      height: 32,
                      child: _ChordProgression(
                        chords: state.chordProgression,
                        hasCurrentChord: state.currentChord != 'N',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          Expanded(
            child: Container(
              key: const ValueKey('lyricsSection'),
              color: PracticeStageColors.background,
              child: SongSheetLyrics(
                timeline: _timeline!,
                playbackTime: state.playbackTime,
              ),
            ),
          ),
          _buildTransportBar(context)!,
        ],
      ),
    );
  }
}

class _ChordFocus extends StatelessWidget {
  const _ChordFocus({
    required this.previousChord,
    required this.currentChord,
    required this.nextChord,
    required this.chordProgress,
    required this.chordStart,
  });

  final String? previousChord;
  final String currentChord;
  final String? nextChord;
  final double? chordProgress;
  final double? chordStart;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      container: true,
      label:
          'Previous chord ${previousChord ?? 'none'}, current chord '
          '$currentChord, next chord ${nextChord ?? 'none'}',
      child: Container(
        key: const ValueKey('chordFocus'),
        decoration: const BoxDecoration(color: PracticeStageColors.background),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(0, 4, 0, 5),
          child: Column(
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    flex: 2,
                    child: _ChordSlot(
                      chord: previousChord,
                      valueKey: const ValueKey('previousChordValue'),
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 3,
                    child: _ChordSlot(
                      chord: currentChord,
                      valueKey: const ValueKey('currentChordValue'),
                      isCurrent: true,
                      chordProgress: chordProgress,
                      chordStart: chordStart,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    flex: 2,
                    child: _ChordSlot(
                      key: const ValueKey('nextChordPreview'),
                      chord: nextChord,
                      valueKey: const ValueKey('nextChordValue'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ChordSlot extends StatelessWidget {
  const _ChordSlot({
    super.key,
    required this.chord,
    required this.valueKey,
    this.isCurrent = false,
    this.chordProgress,
    this.chordStart,
  });

  final String? chord;
  final Key valueKey;
  final bool isCurrent;
  final double? chordProgress;
  final double? chordStart;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final displayChord = chord ?? '—';
    return Opacity(
      opacity: isCurrent
          ? 1
          : chord != null
          ? 0.68
          : 0.35,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: EdgeInsets.fromLTRB(6, isCurrent ? 8 : 18, 6, 7),
        decoration: BoxDecoration(
          color: isCurrent
              ? PracticeStageColors.surfaceRaised
              : Colors.transparent,
          border: isCurrent
              ? Border.all(color: PracticeStageColors.textSecondary, width: 1.5)
              : null,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          children: [
            Text(
              displayChord,
              key: valueKey,
              maxLines: 1,
              style: isCurrent
                  ? textTheme.headlineMedium?.copyWith(
                      color: PracticeStageColors.textPrimary,
                      fontWeight: FontWeight.w800,
                      height: 1,
                    )
                  : textTheme.titleMedium?.copyWith(
                      color: PracticeStageColors.textSecondary,
                      fontWeight: FontWeight.w600,
                    ),
            ),
            SizedBox(
              height: isCurrent ? 102 : 60,
              child: chord == null
                  ? const SizedBox.shrink()
                  : FittedBox(
                      fit: BoxFit.contain,
                      child: ChordDiagram(
                        chord: chord!,
                        foregroundColor: isCurrent
                            ? PracticeStageColors.textPrimary
                            : PracticeStageColors.textSecondary,
                        accentColor: isCurrent
                            ? PracticeStageColors.textPrimary
                            : PracticeStageColors.textSecondary,
                      ),
                    ),
            ),
            if (isCurrent) ...[
              const SizedBox(height: 7),
              _ChordProgressBar(
                key: const ValueKey('chordProgressBar'),
                progress: chordProgress,
                chordStart: chordStart,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ChordProgressBar extends StatelessWidget {
  const _ChordProgressBar({
    super.key,
    required this.progress,
    required this.chordStart,
  });

  final double? progress;
  final double? chordStart;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: progress == null
          ? 'No chord duration to show'
          : 'Chord ${(progress! * 100).round()} percent played',
      child: TweenAnimationBuilder<double>(
        key: ValueKey(chordStart),
        tween: Tween(end: progress ?? 0),
        duration: const Duration(milliseconds: 180),
        curve: Curves.linear,
        builder: (context, value, child) => ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: value,
            minHeight: 6,
            backgroundColor: PracticeStageColors.border,
            valueColor: const AlwaysStoppedAnimation(PracticeStageColors.amber),
          ),
        ),
      ),
    );
  }
}

class _CompactMetric extends StatelessWidget {
  const _CompactMetric({
    required this.label,
    required this.value,
    required this.valueKey,
  });

  final String label;
  final String value;
  final Key valueKey;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: PracticeStageColors.textSecondary,
            ),
          ),
          Text(
            value,
            key: valueKey,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: PracticeStageColors.textPrimary,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _TransportControls extends StatelessWidget {
  const _TransportControls({
    required this.status,
    required this.canGoPrevious,
    required this.canGoNext,
    required this.onPrevious,
    required this.onPlayPause,
    required this.onNext,
  });

  final PracticePlaybackStatus status;
  final bool canGoPrevious;
  final bool canGoNext;
  final VoidCallback onPrevious;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) {
    final isPlaying = status == PracticePlaybackStatus.playing;
    final playLabel = status == PracticePlaybackStatus.completed
        ? 'Replay'
        : 'Play';
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          key: const ValueKey('previousBarButton'),
          onPressed: canGoPrevious ? onPrevious : null,
          tooltip: 'Previous bar',
          icon: const Icon(Icons.skip_previous),
        ),
        IconButton(
          onPressed: onPlayPause,
          tooltip: isPlaying ? 'Pause' : playLabel,
          iconSize: 26,
          color: PracticeStageColors.textPrimary,
          icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow),
        ),
        IconButton(
          key: const ValueKey('nextBarButton'),
          onPressed: canGoNext ? onNext : null,
          tooltip: 'Next bar',
          icon: const Icon(Icons.skip_next),
        ),
      ],
    );
  }
}

class _SpeedSelector extends StatelessWidget {
  const _SpeedSelector({required this.speed, required this.onChanged});

  final double speed;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 66,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            'Speed',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: PracticeStageColors.textFaint,
              fontSize: 9,
            ),
          ),
          DropdownButtonHideUnderline(
            child: DropdownButton<double>(
              key: const ValueKey('speedSelector'),
              value: speed,
              isExpanded: true,
              isDense: true,
              onChanged: (value) {
                if (value != null) onChanged(value);
              },
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
        ],
      ),
    );
  }
}

class _ChordProgression extends StatelessWidget {
  const _ChordProgression({
    required this.chords,
    required this.hasCurrentChord,
  });

  final List<String> chords;
  final bool hasCurrentChord;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    if (chords.isEmpty) {
      return const Text('—', key: ValueKey('progressionEmpty'));
    }
    return Row(
      children: [
        for (var index = 0; index < chords.length; index++)
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Container(
                alignment: Alignment.center,
                padding: const EdgeInsets.symmetric(vertical: 5),
                decoration: BoxDecoration(
                  color: index == 0 && hasCurrentChord
                      ? PracticeStageColors.surfaceRaised
                      : PracticeStageColors.surface,
                  border: Border.all(
                    color: index == 0 && hasCurrentChord
                        ? PracticeStageColors.amber
                        : PracticeStageColors.border,
                    width: index == 0 && hasCurrentChord ? 1.5 : 1,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  chords[index],
                  key: ValueKey('progressionChord$index'),
                  style: index == 0 && hasCurrentChord
                      ? textTheme.labelLarge?.copyWith(
                          color: PracticeStageColors.amberBright,
                          fontWeight: FontWeight.bold,
                        )
                      : textTheme.labelMedium?.copyWith(
                          color: PracticeStageColors.textSecondary,
                        ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _CompactAction extends StatelessWidget {
  const _CompactAction({required this.label, required this.onPressed});

  final String label;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        visualDensity: VisualDensity.compact,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        minimumSize: const Size(30, 34),
        padding: const EdgeInsets.symmetric(horizontal: 2),
      ),
      child: Text(label, style: Theme.of(context).textTheme.labelSmall),
    );
  }
}

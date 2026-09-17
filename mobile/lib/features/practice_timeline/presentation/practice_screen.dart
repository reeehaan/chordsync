import 'dart:async';

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../analysis/application/analyzed_practice_session.dart';
import '../application/practice_audio_player.dart';
import '../application/practice_playback_controller.dart';
import '../application/practice_playback_status.dart';
import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_synchronizer.dart';
import '../application/practice_session_factory.dart';
import '../data/shared_timeline_asset_loader.dart';
import '../data/shared_timeline.dart';
import '../data/playback_lookup.dart';
import 'chord_diagram.dart';
import 'practice_beat_indicator.dart';

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
    return Scaffold(
      appBar: AppBar(title: const Text('ChordSync Practice')),
      body: _buildBody(),
      bottomNavigationBar: _buildTransportBar(),
    );
  }

  Widget? _buildTransportBar() {
    final controller = _controller;
    final synchronizer = _synchronizer;
    if (!_isLoaded || controller == null || synchronizer == null) return null;
    final status = synchronizer.status;
    final state = controller.state;
    final position =
        controller.position.inMicroseconds / Duration.microsecondsPerSecond;
    return SafeArea(
      top: false,
      child: Container(
        key: const ValueKey('transportSection'),
        decoration: const BoxDecoration(
          color: ChordSyncColors.surface,
          border: Border(top: BorderSide(color: ChordSyncColors.border)),
        ),
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
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
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(fontWeight: FontWeight.w800),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      'Next ${state.nextChord ?? '—'}',
                      key: const ValueKey('persistentNextChordValue'),
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    Text(
                      'Position',
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                    const Spacer(),
                    Text(
                      '${position.toStringAsFixed(1)} s',
                      key: const ValueKey('positionValue'),
                    ),
                  ],
                ),
                Row(
                  children: [
                    Text(
                      'Playback',
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                    const Spacer(),
                    Text(
                      status.label,
                      key: const ValueKey('playbackStatusValue'),
                    ),
                  ],
                ),
                Slider(
                  value: position.clamp(0, _maximumPosition),
                  min: 0,
                  max: _maximumPosition,
                  onChanged: _seek,
                ),
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
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBody() {
    if (_loadError != null) {
      return const Center(child: Text('Unable to load practice audio.'));
    }

    final controller = _controller;
    if (!_isLoaded || controller == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final state = controller.state;
    final synchronizer = _synchronizer!;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 40),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                widget.analyzedSession?.title ?? 'Practice sheet',
                key: const ValueKey('songSheetTitle'),
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 6),
              Text(
                'SONG SHEET  •  ${_timeline?.bpm.toStringAsFixed(0) ?? '—'} BPM',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: ChordSyncColors.textSecondary,
                  letterSpacing: 1.2,
                ),
              ),
              const Divider(height: 28, thickness: 1.5),
              _ChordFocus(
                currentChord: state.currentChord,
                nextChord: state.nextChord,
              ),
              const SizedBox(height: 16),
              _PracticeSection(
                key: const ValueKey('lyricsSection'),
                title: 'Lyrics',
                icon: Icons.lyrics_outlined,
                sheetStyle: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    if (_timeline!.lyrics.isEmpty)
                      const Text(
                        'No lyrics detected',
                        key: ValueKey('noLyricsFallback'),
                      )
                    else
                      _SongSheetLyrics(
                        timeline: _timeline!,
                        playbackTime: state.playbackTime,
                      ),
                    if (_timeline!.lyrics.isNotEmpty) ...[
                      const SizedBox(height: 14),
                      _LyricContext(
                        previous: state.previousLyricWord,
                        active: state.activeLyricWord,
                        next: state.nextLyricWord,
                      ),
                    ],
                  ],
                ),
              ),
              _PracticeSection(
                key: const ValueKey('rhythmSection'),
                title: 'Rhythm',
                icon: Icons.graphic_eq,
                sheetStyle: true,
                child: Column(
                  children: [
                    Wrap(
                      alignment: WrapAlignment.spaceEvenly,
                      spacing: 28,
                      runSpacing: 12,
                      children: [
                        _Metric(
                          label: 'Bar',
                          value: state.currentBarNumber?.toString() ?? '—',
                          valueKey: const ValueKey('barValue'),
                        ),
                        _Metric(
                          label: 'Beat',
                          value:
                              '${state.beatNumber?.toString() ?? '—'} / '
                              '${state.beatsPerBar}',
                          valueKey: const ValueKey('beatValue'),
                        ),
                        _Metric(
                          label: 'Downbeat',
                          value: state.isDownbeat ? 'Yes' : 'No',
                          valueKey: const ValueKey('downbeatValue'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    PracticeBeatIndicator(
                      beatNumber: state.beatNumber,
                      beatsPerBar: state.beatsPerBar,
                      isDownbeat: state.isDownbeat,
                    ),
                  ],
                ),
              ),
              _PracticeSection(
                key: const ValueKey('progressionSection'),
                title: 'Progression',
                icon: Icons.queue_music,
                sheetStyle: true,
                child: _ChordProgression(
                  chords: state.chordProgression,
                  hasCurrentChord: state.currentChord != 'N',
                ),
              ),
              _PracticeSection(
                key: const ValueKey('practiceToolsSection'),
                title: 'Practice tools',
                icon: Icons.tune,
                child: Column(
                  children: [
                    _SpeedSelector(
                      speed: synchronizer.speed,
                      onChanged: _setSpeed,
                    ),
                    const Divider(height: 24),
                    _StateRow(
                      label: 'Loop',
                      value: _loopRangeLabel(synchronizer),
                      valueKey: const ValueKey('loopRangeValue'),
                    ),
                    Wrap(
                      alignment: WrapAlignment.center,
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        OutlinedButton(
                          onPressed: () =>
                              synchronizer.setLoopStart(controller.position),
                          child: const Text('Set A'),
                        ),
                        OutlinedButton(
                          onPressed: () =>
                              synchronizer.setLoopEnd(controller.position),
                          child: const Text('Set B'),
                        ),
                        FilledButton.tonal(
                          onPressed: () {
                            if (synchronizer.loop?.enabled == true) {
                              synchronizer.disableLoop();
                            } else {
                              synchronizer.enableLoop();
                            }
                          },
                          child: Text(
                            synchronizer.loop?.enabled == true
                                ? 'Loop Off'
                                : 'Loop On',
                          ),
                        ),
                        TextButton(
                          onPressed: synchronizer.clearLoop,
                          child: const Text('Clear Loop'),
                        ),
                      ],
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
}

class _ChordFocus extends StatelessWidget {
  const _ChordFocus({required this.currentChord, required this.nextChord});

  final String currentChord;
  final String? nextChord;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      container: true,
      label: 'Current chord $currentChord, next chord ${nextChord ?? 'none'}',
      child: Card(
        key: const ValueKey('chordFocus'),
        color: ChordSyncColors.surfaceAlt,
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
          child: Column(
            children: [
              Text(
                'Current chord',
                style: textTheme.labelLarge?.copyWith(
                  color: ChordSyncColors.textSecondary,
                ),
              ),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  currentChord,
                  key: const ValueKey('currentChordValue'),
                  style: textTheme.displayLarge?.copyWith(
                    color: ChordSyncColors.currentChord,
                    fontWeight: FontWeight.w800,
                    height: 1,
                  ),
                ),
              ),
              const SizedBox(height: 10),
              ChordDiagram(chord: currentChord),
              const SizedBox(height: 16),
              Text(
                'Next chord',
                style: textTheme.labelMedium?.copyWith(
                  color: ChordSyncColors.textSecondary,
                ),
              ),
              Text(
                nextChord ?? '—',
                key: const ValueKey('nextChordValue'),
                style: textTheme.headlineSmall?.copyWith(
                  color: ChordSyncColors.textPrimary,
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

class _PracticeSection extends StatelessWidget {
  const _PracticeSection({
    required this.title,
    required this.icon,
    required this.child,
    this.sheetStyle = false,
    super.key,
  });

  final String title;
  final IconData icon;
  final Widget child;
  final bool sheetStyle;

  @override
  Widget build(BuildContext context) {
    final content = Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, size: 20, color: ChordSyncColors.brand),
              const SizedBox(width: 8),
              Text(title, style: Theme.of(context).textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
    if (sheetStyle) {
      return Container(
        margin: const EdgeInsets.only(bottom: 8),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: ChordSyncColors.border)),
        ),
        child: content,
      );
    }
    return Card(margin: const EdgeInsets.only(bottom: 12), child: content);
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    required this.valueKey,
  });

  final String label;
  final String value;
  final Key valueKey;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 88,
      child: Column(
        children: [
          Text(label, style: Theme.of(context).textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(
            value,
            key: valueKey,
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
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
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        IconButton.filledTonal(
          key: const ValueKey('previousBarButton'),
          onPressed: canGoPrevious ? onPrevious : null,
          tooltip: 'Previous bar',
          icon: const Icon(Icons.skip_previous),
        ),
        const SizedBox(width: 16),
        IconButton.filled(
          onPressed: onPlayPause,
          tooltip: isPlaying ? 'Pause' : playLabel,
          iconSize: 32,
          padding: const EdgeInsets.all(16),
          style: IconButton.styleFrom(
            backgroundColor: ChordSyncColors.brandDark,
            foregroundColor: ChordSyncColors.background,
            side: const BorderSide(color: ChordSyncColors.honey, width: 2),
          ),
          icon: Icon(isPlaying ? Icons.pause : Icons.play_arrow),
        ),
        const SizedBox(width: 16),
        IconButton.filledTonal(
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          const Text('Speed'),
          DropdownButton<double>(
            key: const ValueKey('speedSelector'),
            value: speed,
            onChanged: (value) {
              if (value != null) onChanged(value);
            },
            items: [
              for (final option in PracticePlaybackSpeeds.supported)
                DropdownMenuItem(
                  value: option,
                  child: Text(PracticePlaybackSpeeds.label(option)),
                ),
            ],
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
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (var index = 0; index < chords.length; index++)
            Padding(
              padding: const EdgeInsets.only(right: 10),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 9,
                ),
                decoration: BoxDecoration(
                  color: index == 0 && hasCurrentChord
                      ? ChordSyncColors.surfaceAlt
                      : ChordSyncColors.surface,
                  border: Border.all(
                    color: index == 0 && hasCurrentChord
                        ? ChordSyncColors.brand
                        : ChordSyncColors.border,
                    width: index == 0 && hasCurrentChord ? 2 : 1,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  chords[index],
                  key: ValueKey('progressionChord$index'),
                  style: index == 0 && hasCurrentChord
                      ? textTheme.titleLarge?.copyWith(
                          color: ChordSyncColors.brandDark,
                          fontWeight: FontWeight.bold,
                        )
                      : textTheme.titleMedium?.copyWith(
                          color: ChordSyncColors.textSecondary,
                        ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _SongSheetLyrics extends StatelessWidget {
  const _SongSheetLyrics({required this.timeline, required this.playbackTime});

  final SharedTimeline timeline;
  final double playbackTime;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var index = 0; index < timeline.lyrics.length; index++)
          Padding(
            padding: const EdgeInsets.only(bottom: 22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (PlaybackLookup.currentBeat(
                      timeline,
                      timeline.lyrics[index].start,
                    )
                    case final beat?)
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: ChordSyncColors.surfaceAlt,
                      border: Border.all(color: ChordSyncColors.border),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      beat.chord,
                      style: textTheme.labelMedium?.copyWith(
                        color: ChordSyncColors.brandDark,
                      ),
                    ),
                  ),
                Wrap(
                  spacing: 6,
                  runSpacing: 7,
                  children: [
                    for (final word in timeline.lyrics[index].words)
                      Text(
                        word.text,
                        key: ValueKey('sheetWord${word.start}'),
                        style: textTheme.bodyLarge?.copyWith(
                          color: word.end <= playbackTime
                              ? ChordSyncColors.textSecondary
                              : ChordSyncColors.textPrimary,
                          fontWeight:
                              word.start <= playbackTime &&
                                  playbackTime < word.end
                              ? FontWeight.w700
                              : FontWeight.normal,
                          decoration:
                              word.start <= playbackTime &&
                                  playbackTime < word.end
                              ? TextDecoration.underline
                              : TextDecoration.none,
                          decorationColor: ChordSyncColors.honey,
                          decorationThickness: 2,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _LyricContext extends StatelessWidget {
  const _LyricContext({
    required this.previous,
    required this.active,
    required this.next,
  });

  final String? previous;
  final String? active;
  final String? next;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _LyricWord(
          label: 'Previous',
          value: previous,
          valueKey: const ValueKey('previousLyricValue'),
        ),
        _LyricWord(
          label: 'Active',
          value: active,
          valueKey: const ValueKey('lyricValue'),
          isActive: true,
        ),
        _LyricWord(
          label: 'Next',
          value: next,
          valueKey: const ValueKey('nextLyricValue'),
        ),
      ],
    );
  }
}

class _LyricWord extends StatelessWidget {
  const _LyricWord({
    required this.label,
    required this.value,
    required this.valueKey,
    this.isActive = false,
  });

  final String label;
  final String? value;
  final Key valueKey;
  final bool isActive;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Expanded(
      child: Column(
        children: [
          Text(label, style: textTheme.labelMedium),
          const SizedBox(height: 4),
          Text(
            value ?? '—',
            key: valueKey,
            textAlign: TextAlign.center,
            style: isActive
                ? textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: ChordSyncColors.textPrimary,
                    decoration: TextDecoration.underline,
                    decorationColor: ChordSyncColors.honey,
                    decorationThickness: 2,
                  )
                : textTheme.titleMedium?.copyWith(
                    color: label == 'Previous'
                        ? ChordSyncColors.textSecondary
                        : ChordSyncColors.textPrimary,
                  ),
          ),
        ],
      ),
    );
  }
}

class _StateRow extends StatelessWidget {
  const _StateRow({
    required this.label,
    required this.value,
    required this.valueKey,
  });

  final String label;
  final String value;
  final Key valueKey;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Text(label),
          const SizedBox(width: 16),
          Expanded(
            child: Text(
              value,
              key: valueKey,
              textAlign: TextAlign.end,
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
        ],
      ),
    );
  }
}

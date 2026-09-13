import 'dart:async';

import 'package:flutter/material.dart';

import '../application/practice_audio_player.dart';
import '../application/practice_playback_controller.dart';
import '../application/practice_playback_status.dart';
import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_synchronizer.dart';
import '../data/shared_timeline_asset_loader.dart';
import 'practice_beat_indicator.dart';

class PracticeScreen extends StatefulWidget {
  const PracticeScreen({super.key, this.audioPlayer});

  final PracticeAudioPlayer? audioPlayer;

  @override
  State<PracticeScreen> createState() => _PracticeScreenState();
}

class _PracticeScreenState extends State<PracticeScreen> {
  PracticeAudioPlayer? _audioPlayer;
  PracticePlaybackController? _controller;
  PracticePlaybackSynchronizer? _synchronizer;
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
    final status = synchronizer.status;
    final position =
        controller.position.inMicroseconds / Duration.microsecondsPerSecond;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 840),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _ChordFocus(
                currentChord: state.currentChord,
                nextChord: state.nextChord,
              ),
              const SizedBox(height: 16),
              _PracticeSection(
                key: const ValueKey('lyricsSection'),
                title: 'Lyrics',
                icon: Icons.lyrics_outlined,
                child: _LyricContext(
                  previous: state.previousLyricWord,
                  active: state.activeLyricWord,
                  next: state.nextLyricWord,
                ),
              ),
              _PracticeSection(
                key: const ValueKey('rhythmSection'),
                title: 'Rhythm',
                icon: Icons.graphic_eq,
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
                child: _ChordProgression(
                  chords: state.chordProgression,
                  hasCurrentChord: state.currentChord != 'N',
                ),
              ),
              _PracticeSection(
                key: const ValueKey('transportSection'),
                title: 'Transport',
                icon: Icons.play_circle_outline,
                child: Column(
                  children: [
                    _StateRow(
                      label: 'Position',
                      value: '${position.toStringAsFixed(1)} s',
                      valueKey: const ValueKey('positionValue'),
                    ),
                    _StateRow(
                      label: 'Playback',
                      value: status.label,
                      valueKey: const ValueKey('playbackStatusValue'),
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
    final colors = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      container: true,
      label: 'Current chord $currentChord, next chord ${nextChord ?? 'none'}',
      child: Card(
        key: const ValueKey('chordFocus'),
        color: colors.primaryContainer,
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
          child: Column(
            children: [
              Text(
                'Current chord',
                style: textTheme.labelLarge?.copyWith(
                  color: colors.onPrimaryContainer,
                ),
              ),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(
                  currentChord,
                  key: const ValueKey('currentChordValue'),
                  style: textTheme.displayLarge?.copyWith(
                    color: colors.onPrimaryContainer,
                    fontWeight: FontWeight.w800,
                    height: 1,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Next chord',
                style: textTheme.labelMedium?.copyWith(
                  color: colors.onPrimaryContainer.withValues(alpha: 0.72),
                ),
              ),
              Text(
                nextChord ?? '—',
                key: const ValueKey('nextChordValue'),
                style: textTheme.headlineSmall?.copyWith(
                  color: colors.onPrimaryContainer,
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
    super.key,
  });

  final String title;
  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(icon, size: 20),
                const SizedBox(width: 8),
                Text(title, style: Theme.of(context).textTheme.titleMedium),
              ],
            ),
            const SizedBox(height: 16),
            child,
          ],
        ),
      ),
    );
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
    final colorScheme = Theme.of(context).colorScheme;

    if (chords.isEmpty) {
      return const Text('—', key: ValueKey('progressionEmpty'));
    }
    return Wrap(
      spacing: 12,
      runSpacing: 8,
      children: [
        for (var index = 0; index < chords.length; index++) ...[
          if (index > 0) const Text('|'),
          Text(
            chords[index],
            key: ValueKey('progressionChord$index'),
            style: index == 0 && hasCurrentChord
                ? textTheme.titleLarge?.copyWith(
                    color: colorScheme.primary,
                    fontWeight: FontWeight.bold,
                  )
                : textTheme.titleMedium?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                  ),
          ),
        ],
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
                    color: Theme.of(context).colorScheme.primary,
                  )
                : textTheme.titleMedium,
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

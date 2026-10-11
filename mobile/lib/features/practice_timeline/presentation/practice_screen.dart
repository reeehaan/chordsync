import 'dart:async';

import 'package:flutter/material.dart';

import '../../analysis/application/analyzed_practice_session.dart';
import '../application/practice_audio_player.dart';
import '../application/practice_playback_controller.dart';
import '../application/practice_playback_status.dart';
import '../application/practice_playback_synchronizer.dart';
import '../application/practice_session_factory.dart';
import '../data/chord_transposition.dart';
import '../data/shared_timeline_asset_loader.dart';
import '../data/shared_timeline.dart';
import 'capo_settings_sheet.dart';
import 'chord_diagram_strip.dart';
import 'music_only_views.dart';
import 'practice_sheet_header.dart';
import 'practice_stage_colors.dart';
import 'practice_stage_theme.dart';
import 'practice_transport_bar.dart';
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
    final stageTheme = practiceStageTheme(Theme.of(context));

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
          PracticeSheetHeader(
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
            const MusicOnlyChordFocus()
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
                  ? MusicOnlyLyrics(state: state)
                  : SongSheetLyrics(
                      timeline: displayTimeline,
                      playbackTime: state.playbackTime,
                    ),
            ),
          ),
          PracticeTransportBar(
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
    final result = await showCapoSettingsSheet(
      context,
      timeline: timeline,
      currentFret: _capoFret,
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

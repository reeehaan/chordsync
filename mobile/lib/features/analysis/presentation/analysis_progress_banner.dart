import 'dart:async';
import 'dart:ui';

import 'package:flutter/foundation.dart';

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/motion.dart';
import '../application/analyzed_practice_session.dart';
import 'audio_import_controller.dart';

/// A banner at the top of the home screens that follows a song being analyzed
/// after the person has left the progress screen. It names the song and its
/// step, and becomes "Tap to play" once the practice sheet is ready. It slides
/// away on the practice screen, comes back on return while there is still
/// something to show, and leaves by itself a while after a song is ready.
class AnalysisProgressBanner extends StatefulWidget {
  const AnalysisProgressBanner({
    super.key,
    required this.controller,
    required this.onPlay,
    this.atHome,
    this.readyLinger = const Duration(seconds: 30),
  });

  final AudioImportController controller;

  /// Opens the finished song for practice.
  final void Function(AnalyzedPracticeSession session) onPlay;

  /// False while a page such as the practice screen covers the home screens.
  /// Null means always home.
  final ValueListenable<bool>? atHome;

  /// How long a finished song stays on the banner before it slides away.
  final Duration readyLinger;

  @override
  State<AnalysisProgressBanner> createState() => _AnalysisProgressBannerState();
}

enum _Mode { running, ready, failed }

class _AnalysisProgressBannerState extends State<AnalysisProgressBanner> {
  AudioImportPhase _lastPhase = AudioImportPhase.idle;
  Timer? _linger;
  bool _visible = false;

  // What the banner last showed, kept so it can slide away with its words
  // still on it after the controller has moved on.
  String _title = '';
  String _subtitle = '';
  _Mode _mode = _Mode.running;
  int _step = 1;

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
    widget.atHome?.addListener(_changed);
    _sync();
  }

  @override
  void didUpdateWidget(AnalysisProgressBanner old) {
    super.didUpdateWidget(old);
    if (old.controller != widget.controller) {
      old.controller.removeListener(_changed);
      widget.controller.addListener(_changed);
    }
    if (old.atHome != widget.atHome) {
      old.atHome?.removeListener(_changed);
      widget.atHome?.addListener(_changed);
    }
  }

  @override
  void dispose() {
    _linger?.cancel();
    widget.controller.removeListener(_changed);
    widget.atHome?.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    final controller = widget.controller;
    if (controller.inBackground &&
        controller.phase == AudioImportPhase.ready &&
        _lastPhase != AudioImportPhase.ready) {
      Haptics.success();
    }
    _lastPhase = controller.phase;
    if (mounted) setState(_sync);
  }

  static String _stepName(AudioImportPhase phase) => switch (phase) {
    AudioImportPhase.uploading ||
    AudioImportPhase.finishingUpload => 'Uploading',
    AudioImportPhase.queued => 'Waiting in line',
    AudioImportPhase.processing => 'Analyzing',
    AudioImportPhase.preparing => 'Preparing the practice sheet',
    _ => 'Working',
  };

  void _sync() {
    final controller = widget.controller;
    final phase = controller.phase;
    final ready = phase == AudioImportPhase.ready && controller.session != null;
    final failed = phase == AudioImportPhase.failed;
    final home = widget.atHome?.value ?? true;
    final wanted =
        controller.inBackground && (controller.isActive || ready || failed);
    _visible = wanted && home;

    if (wanted) {
      _title = controller.title;
      _step = controller.stepNumber;
      if (ready) {
        _mode = _Mode.ready;
        _subtitle = 'Ready · Tap to play';
      } else if (failed) {
        _mode = _Mode.failed;
        _subtitle =
            '${controller.errorMessage ?? 'Could not analyze'} · Tap to dismiss';
      } else {
        _mode = _Mode.running;
        _subtitle =
            'Step ${controller.stepNumber} of ${AudioImportController.stepCount}'
            ' · ${_stepName(phase)}';
      }
    }

    // A finished or failed song waits for a tap, but not for ever. The clock
    // runs only while the banner is on screen.
    final lingering = _visible && (ready || failed);
    if (!lingering) {
      _linger?.cancel();
      _linger = null;
    } else {
      _linger ??= Timer(widget.readyLinger, () {
        _linger = null;
        // The song is already saved in the library; this only clears the
        // banner.
        if (mounted) widget.controller.reset();
      });
    }
  }

  void _tap() {
    final controller = widget.controller;
    switch (_mode) {
      case _Mode.ready:
        final session = controller.session;
        if (session != null) widget.onPlay(session);
      case _Mode.failed:
        controller.reset();
      case _Mode.running:
        controller.bringToFront();
    }
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !_visible,
      child: AnimatedSlide(
        duration: ChordSyncMotion.of(context, ChordSyncMotion.emphasized),
        curve: _visible ? ChordSyncMotion.spring : ChordSyncMotion.exit,
        offset: _visible ? Offset.zero : const Offset(0, -1.6),
        child: AnimatedOpacity(
          duration: ChordSyncMotion.of(context, ChordSyncMotion.standard),
          opacity: _visible ? 1 : 0,
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              12,
              MediaQuery.paddingOf(context).top + 6,
              12,
              0,
            ),
            child: Material(
              type: MaterialType.transparency,
              child: Semantics(
                button: true,
                liveRegion: true,
                label: '$_title. $_subtitle',
                child: GestureDetector(
                  key: const ValueKey('analysisProgressBanner'),
                  behavior: HitTestBehavior.opaque,
                  onTap: _tap,
                  // A hidden banner must not keep its disc turning.
                  child: TickerMode(
                    enabled: _visible,
                    child: _BannerBody(
                      title: _title,
                      subtitle: _subtitle,
                      step: _step,
                      mode: _mode,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _BannerBody extends StatelessWidget {
  const _BannerBody({
    required this.title,
    required this.subtitle,
    required this.step,
    required this.mode,
  });

  final String title;
  final String subtitle;
  final int step;
  final _Mode mode;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(28);
    final ready = mode == _Mode.ready;
    final failed = mode == _Mode.failed;
    final textTheme = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: radius,
        boxShadow: const [
          BoxShadow(
            color: Color(0x4D000000),
            blurRadius: 28,
            offset: Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            padding: const EdgeInsets.fromLTRB(14, 14, 16, 14),
            decoration: BoxDecoration(
              color: ChordSyncColors.brandDark.withValues(alpha: 0.95),
              borderRadius: radius,
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.12),
                width: 0.8,
              ),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    _SpinningDisc(
                      spinning: mode == _Mode.running,
                      ready: ready,
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title.isEmpty ? 'Your song' : title,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: textTheme.titleLarge?.copyWith(
                              color: Colors.white,
                              fontSize: 19,
                              fontWeight: FontWeight.w700,
                              height: 1.15,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            subtitle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: textTheme.bodyMedium?.copyWith(
                              fontSize: 15,
                              fontWeight: FontWeight.w500,
                              color: ready
                                  ? ChordSyncColors.brandAccent
                                  : failed
                                  ? const Color(0xFFFFB4A2)
                                  : const Color(0xFFEADFCF),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(
                      Icons.chevron_right_rounded,
                      color: Color(0xFFEADFCF),
                      size: 26,
                    ),
                  ],
                ),
                if (!failed) ...[
                  const SizedBox(height: 12),
                  _StepBar(filled: ready ? 4 : step),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Four rounded segments, one per step; the finished ones fill with amber.
class _StepBar extends StatelessWidget {
  const _StepBar({required this.filled});

  final int filled;

  @override
  Widget build(BuildContext context) {
    final duration = ChordSyncMotion.of(context, ChordSyncMotion.emphasized);
    return Row(
      children: List.generate(AudioImportController.stepCount, (index) {
        return Expanded(
          child: Padding(
            padding: EdgeInsets.only(left: index == 0 ? 0 : 5),
            child: AnimatedContainer(
              duration: duration,
              curve: ChordSyncMotion.enter,
              height: 5,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(3),
                color: index < filled
                    ? ChordSyncColors.brandAccent
                    : Colors.white.withValues(alpha: 0.18),
              ),
            ),
          ),
        );
      }),
    );
  }
}

/// A record that turns while the song is being analyzed. A sweep of light
/// across its grooves makes the turning visible; the centre is an amber label.
class _SpinningDisc extends StatefulWidget {
  const _SpinningDisc({required this.spinning, required this.ready});

  final bool spinning;
  final bool ready;

  @override
  State<_SpinningDisc> createState() => _SpinningDiscState();
}

class _SpinningDiscState extends State<_SpinningDisc>
    with SingleTickerProviderStateMixin {
  late final AnimationController _turn = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 3),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _updateSpin();
  }

  @override
  void didUpdateWidget(_SpinningDisc old) {
    super.didUpdateWidget(old);
    _updateSpin();
  }

  void _updateSpin() {
    if (widget.spinning && !ChordSyncMotion.reduced(context)) {
      if (!_turn.isAnimating) _turn.repeat();
    } else {
      _turn.stop();
    }
  }

  @override
  void dispose() {
    _turn.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const size = 56.0;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          RotationTransition(
            turns: _turn,
            child: Container(
              width: size,
              height: size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: ChordSyncColors.brandAccent,
                  width: 2,
                ),
                gradient: const SweepGradient(
                  colors: [
                    Color(0xFF1B1411),
                    Color(0xFF4A3A30),
                    Color(0xFF1B1411),
                    Color(0xFF1B1411),
                    Color(0xFF3A2D25),
                    Color(0xFF1B1411),
                  ],
                  stops: [0, 0.12, 0.3, 0.5, 0.62, 1],
                ),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  for (final ring in [44.0, 34.0])
                    Container(
                      width: ring,
                      height: ring,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(color: const Color(0x26EAD9C3)),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Container(
            width: 24,
            height: 24,
            decoration: const BoxDecoration(
              color: ChordSyncColors.honey,
              shape: BoxShape.circle,
            ),
            child: Icon(
              widget.ready ? Icons.play_arrow_rounded : Icons.music_note,
              size: 17,
              color: ChordSyncColors.brandDark,
            ),
          ),
        ],
      ),
    );
  }
}

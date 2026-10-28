import 'dart:async';

import 'package:flutter/material.dart';

import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_status.dart';
import 'practice_stage_colors.dart';

/// Rounded transport pill: bar navigation, play/pause, scrub line, and the
/// speed control kept as a compact circular button.
class PracticeTransportBar extends StatefulWidget {
  const PracticeTransportBar({
    super.key,
    required this.status,
    required this.position,
    required this.maximumPosition,
    required this.speed,
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
  final bool canGoPrevious;
  final bool canGoNext;
  final VoidCallback onPrevious;
  final VoidCallback onPlayPause;
  final VoidCallback onNext;

  /// Called once, when the person lets go of the scrub line (or taps it).
  final ValueChanged<double> onSeek;
  final ValueChanged<double> onSpeedChanged;

  @override
  State<PracticeTransportBar> createState() => _PracticeTransportBarState();
}

class _PracticeTransportBarState extends State<PracticeTransportBar> {
  // Where the handle sits while a finger is on it, and for a moment after, so
  // playback updates cannot pull it back before the seek has landed.
  double? _scrub;
  double? _positionAtRelease;
  bool _dragging = false;
  Timer? _settle;

  @override
  void didUpdateWidget(PracticeTransportBar old) {
    super.didUpdateWidget(old);
    final scrub = _scrub;
    // Let go only once the player has reported a new position close to where
    // the finger left the handle: that is the seek landing.
    if (scrub != null &&
        !_dragging &&
        widget.position != _positionAtRelease &&
        (widget.position - scrub).abs() < 1.0) {
      _release();
    }
  }

  @override
  void dispose() {
    _settle?.cancel();
    super.dispose();
  }

  void _release() {
    _settle?.cancel();
    _settle = null;
    _scrub = null;
  }

  void _start(double value) {
    _settle?.cancel();
    setState(() {
      _dragging = true;
      _scrub = value;
    });
  }

  void _end(double value) {
    // One seek per gesture. Seeking on every move floods the player and makes
    // the playback stutter.
    widget.onSeek(value);
    _positionAtRelease = widget.position;
    setState(() => _dragging = false);
    // If playback never reports a position near the target (for example the
    // song is paused), let go of the hold shortly anyway.
    _settle = Timer(const Duration(milliseconds: 1500), () {
      if (mounted) setState(_release);
    });
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.status;
    final position = widget.position;
    final maximumPosition = widget.maximumPosition;
    final speed = widget.speed;
    final canGoPrevious = widget.canGoPrevious;
    final canGoNext = widget.canGoNext;
    final onPrevious = widget.onPrevious;
    final onPlayPause = widget.onPlayPause;
    final onNext = widget.onNext;
    final onSpeedChanged = widget.onSpeedChanged;
    final isPlaying = status == PracticePlaybackStatus.playing;
    final playLabel = status == PracticePlaybackStatus.completed
        ? 'Replay'
        : 'Play';

    return Container(
      key: const ValueKey('transportSection'),
      color: PracticeStageColors.background,
      // The bar sits a little lower than the safe area: it takes less than the
      // full home-indicator inset.
      padding: EdgeInsets.fromLTRB(
        40,
        4,
        40,
        2 + MediaQuery.viewPaddingOf(context).bottom * 0.4,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Expanded(
                child: Container(
                  height: 56,
                  decoration: BoxDecoration(
                    color: PracticeStageColors.player,
                    borderRadius: BorderRadius.circular(28),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 6),
                  child: Row(
                    children: [
                      IconButton(
                        key: const ValueKey('previousBarButton'),
                        onPressed: canGoPrevious ? onPrevious : null,
                        tooltip: 'Previous bar',
                        iconSize: 18,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.onPlayerMuted,
                        disabledColor: PracticeStageColors.playerTrack,
                        icon: const Icon(Icons.skip_previous_rounded),
                      ),
                      IconButton(
                        onPressed: onPlayPause,
                        tooltip: isPlaying ? 'Pause' : playLabel,
                        iconSize: 26,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.onPlayer,
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
                        iconSize: 18,
                        visualDensity: VisualDensity.compact,
                        color: PracticeStageColors.onPlayerMuted,
                        disabledColor: PracticeStageColors.playerTrack,
                        icon: const Icon(Icons.skip_next_rounded),
                      ),
                      Expanded(
                        child: SliderTheme(
                          data: SliderTheme.of(context),
                          child: Slider(
                            value: (_scrub ?? position).clamp(
                              0,
                              maximumPosition,
                            ),
                            min: 0,
                            max: maximumPosition,
                            onChangeStart: _start,
                            onChanged: (value) =>
                                setState(() => _scrub = value),
                            onChangeEnd: _end,
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
      color: PracticeStageColors.onPlayer,
      fontWeight: FontWeight.w700,
    );
    return Container(
      width: 56,
      height: 56,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: PracticeStageColors.player,
        shape: BoxShape.circle,
      ),
      child: DropdownButtonHideUnderline(
        // The whole 56pt circle is the touch target, not just the label.
        child: SizedBox(
          width: 56,
          height: 56,
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

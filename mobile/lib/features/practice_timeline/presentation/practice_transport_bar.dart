import 'package:flutter/material.dart';

import '../application/practice_playback_speeds.dart';
import '../application/practice_playback_status.dart';
import 'practice_stage_colors.dart';

/// Rounded transport pill: bar navigation, play/pause, scrub line, and the
/// speed control kept as a compact circular button.
class PracticeTransportBar extends StatelessWidget {
  const PracticeTransportBar({
    super.key,
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

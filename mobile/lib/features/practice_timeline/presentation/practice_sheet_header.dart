import 'package:flutter/material.dart';

import '../application/practice_playback_status.dart';
import 'practice_stage_colors.dart';

/// Song identity plus the A–B loop tools, styled as the pill row from the
/// practice sheet design.
class PracticeSheetHeader extends StatelessWidget {
  const PracticeSheetHeader({
    super.key,
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

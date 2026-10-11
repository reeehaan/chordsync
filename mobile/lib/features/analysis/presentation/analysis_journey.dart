import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import 'audio_import_controller.dart';
import 'upload_theme.dart';

/// Full-screen progress view shown while an upload is being analyzed.
class AnalysisJourney extends StatefulWidget {
  const AnalysisJourney({
    super.key,
    required this.controller,
    required this.onCancel,
  });

  final AudioImportController controller;
  final VoidCallback onCancel;

  @override
  State<AnalysisJourney> createState() => _AnalysisJourneyState();
}

class _AnalysisJourneyState extends State<AnalysisJourney>
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
                  color: UploadPalette.secondaryText,
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

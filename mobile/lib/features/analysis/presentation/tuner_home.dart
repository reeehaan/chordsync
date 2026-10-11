import 'package:flutter/material.dart';

import 'upload_theme.dart';

/// Placeholder tuner tab until microphone pitch detection is connected.
class TunerHome extends StatelessWidget {
  const TunerHome({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 28, 24, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Tuner', style: Theme.of(context).textTheme.displayMedium),
          const SizedBox(height: 8),
          Text(
            'Tune before you play.',
            style: Theme.of(
              context,
            ).textTheme.bodyLarge?.copyWith(color: UploadPalette.secondaryText),
          ),
          const Spacer(),
          const Icon(Icons.graphic_eq_rounded, size: 58),
          const SizedBox(height: 20),
          Text(
            '—  E  —',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.displayLarge,
          ),
          const SizedBox(height: 12),
          Text(
            'Microphone tuner coming next',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 6),
          Text(
            'The navigation is ready; pitch detection still needs microphone permission and audio processing.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: UploadPalette.secondaryText,
            ),
          ),
          const Spacer(flex: 2),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../data/chord_transposition.dart';
import '../data/shared_timeline.dart';
import 'practice_stage_colors.dart';

/// Lets the player pick a capo fret. Resolves to the chosen fret, or null when
/// the sheet is dismissed without applying.
Future<int?> showCapoSettingsSheet(
  BuildContext context, {
  required SharedTimeline timeline,
  required int currentFret,
}) {
  var selected = currentFret;
  final recommended = ChordTransposition.recommendedCapo(timeline);
  return showModalBottomSheet<int>(
    context: context,
    backgroundColor: PracticeStageColors.surface,
    isScrollControlled: true,
    builder: (context) => StatefulBuilder(
      builder: (context, setModalState) {
        final chords = ChordTransposition.songChords(
          timeline,
          capoFret: selected,
        );
        return SafeArea(
          child: DefaultTextStyle.merge(
            style: const TextStyle(color: PracticeStageColors.textPrimary),
            child: IconTheme.merge(
              data: const IconThemeData(color: PracticeStageColors.textPrimary),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      'Capo settings',
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: PracticeStageColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      'Recommended: ${recommended == 0 ? 'No capo' : 'fret $recommended'}',
                    ),
                    const SizedBox(height: 14),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          selected == 0 ? 'No capo' : 'Capo: fret $selected',
                        ),
                        Row(
                          children: [
                            IconButton(
                              tooltip: 'Lower capo',
                              color: PracticeStageColors.textPrimary,
                              disabledColor: PracticeStageColors.textFaint,
                              onPressed: selected == 0
                                  ? null
                                  : () => setModalState(() => selected--),
                              icon: const Icon(Icons.remove),
                            ),
                            IconButton(
                              tooltip: 'Raise capo',
                              color: PracticeStageColors.textPrimary,
                              disabledColor: PracticeStageColors.textFaint,
                              onPressed: selected == 11
                                  ? null
                                  : () => setModalState(() => selected++),
                              icon: const Icon(Icons.add),
                            ),
                          ],
                        ),
                      ],
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text('Shapes: ${chords.join('  ·  ')}'),
                    ),
                    const SizedBox(height: 18),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: () => Navigator.pop(context, selected),
                        child: const Text('Apply'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    ),
  );
}

import 'package:flutter/material.dart';

import '../data/chord_transposition.dart';
import '../data/shared_timeline.dart';
import 'chord_diagram.dart';
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
            style: TextStyle(color: PracticeStageColors.textPrimary),
            child: IconTheme.merge(
              data: IconThemeData(color: PracticeStageColors.textPrimary),
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
                      child: Text(
                        'Chords:',
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(color: PracticeStageColors.textPrimary),
                      ),
                    ),
                    const SizedBox(height: 8),
                    SizedBox(
                      height: 128,
                      child: ListView.separated(
                        key: const ValueKey('capoShapeDiagrams'),
                        scrollDirection: Axis.horizontal,
                        physics: const BouncingScrollPhysics(),
                        itemCount: chords.length,
                        separatorBuilder: (_, _) => const SizedBox(width: 10),
                        itemBuilder: (context, index) =>
                            _CapoShape(chord: chords[index]),
                      ),
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

/// One chord shape in the capo sheet: the diagram above the shape's name.
class _CapoShape extends StatelessWidget {
  const _CapoShape({required this.chord});

  final String chord;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 92,
      child: Column(
        children: [
          Expanded(
            child: FittedBox(
              fit: BoxFit.contain,
              child: ChordDiagram(
                chord: chord,
                foregroundColor: PracticeStageColors.textPrimary,
                accentColor: PracticeStageColors.textPrimary,
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            chord,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: PracticeStageColors.amberBright,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

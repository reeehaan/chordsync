import 'package:chordsync/design_system/chordsync_design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('warm theme has readable semantic surface and controls', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ChordSyncTheme.light(),
        home: Scaffold(
          body: Column(
            children: [
              const Text('ChordSync'),
              FilledButton(onPressed: () {}, child: const Text('Analyze Song')),
            ],
          ),
        ),
      ),
    );
    final theme = Theme.of(tester.element(find.text('ChordSync')));
    expect(theme.scaffoldBackgroundColor, ChordSyncColors.background);
    expect(theme.colorScheme.primary, ChordSyncColors.brand);
    expect(theme.colorScheme.onSurface, ChordSyncColors.textPrimary);
    expect(theme.textTheme.displayLarge?.fontFamily, 'Newsreader');
    expect(theme.textTheme.bodyMedium?.fontFamily, 'DM Sans');
    expect(find.widgetWithText(FilledButton, 'Analyze Song'), findsOneWidget);
  });
}

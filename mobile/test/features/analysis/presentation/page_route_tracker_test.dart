import 'package:chordsync/features/analysis/presentation/page_route_tracker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('knows when a page covers home, but not a dialog', (
    tester,
  ) async {
    final tracker = PageRouteTracker();
    await tester.pumpWidget(
      MaterialApp(
        navigatorObservers: [tracker],
        home: Builder(
          builder: (context) => Scaffold(
            body: Column(
              children: [
                TextButton(
                  onPressed: () => Navigator.of(context).push<void>(
                    MaterialPageRoute(
                      builder: (_) => const Scaffold(body: Text('practice')),
                    ),
                  ),
                  child: const Text('open page'),
                ),
                TextButton(
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => const AlertDialog(title: Text('dialog')),
                  ),
                  child: const Text('open dialog'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(tracker.atHome.value, isTrue);

    await tester.tap(find.text('open dialog'));
    await tester.pumpAndSettle();
    expect(tracker.atHome.value, isTrue);
    Navigator.of(tester.element(find.text('dialog'))).pop();
    await tester.pumpAndSettle();

    await tester.tap(find.text('open page'));
    await tester.pumpAndSettle();
    expect(tracker.atHome.value, isFalse);

    Navigator.of(tester.element(find.text('practice'))).pop();
    await tester.pumpAndSettle();
    expect(tracker.atHome.value, isTrue);
  });

  testWidgets('uncovered is false under a dialog or a page, true otherwise', (
    tester,
  ) async {
    final tracker = PageRouteTracker();
    await tester.pumpWidget(
      MaterialApp(
        navigatorObservers: [tracker],
        home: Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                builder: (_) =>
                    const SizedBox(height: 100, child: Text('sheet')),
              ),
              child: const Text('open sheet'),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    expect(tracker.uncovered.value, isTrue);

    await tester.tap(find.text('open sheet'));
    await tester.pumpAndSettle();
    expect(tracker.uncovered.value, isFalse);
    expect(tracker.atHome.value, isTrue); // a sheet is not a page

    Navigator.of(tester.element(find.text('sheet'))).pop();
    await tester.pumpAndSettle();
    expect(tracker.uncovered.value, isTrue);
  });
}

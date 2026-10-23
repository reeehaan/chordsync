import 'package:chordsync/features/practice_timeline/presentation/marquee_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pump(WidgetTester tester, String text) => tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 120,
          child: MarqueeText(
            text,
            textKey: const ValueKey('title'),
            style: const TextStyle(fontSize: 20),
          ),
        ),
      ),
    ),
  );

  testWidgets('a long title glides sideways to show all of it', (tester) async {
    await pump(tester, 'A very long song title that cannot fit on one line');
    await tester.pump();
    await tester.pump();
    final start = tester.getTopLeft(find.byKey(const ValueKey('title'))).dx;

    // After the rest at the start the text has moved left.
    await tester.pump(const Duration(milliseconds: 2500));
    final moved = tester.getTopLeft(find.byKey(const ValueKey('title'))).dx;
    expect(moved, lessThan(start));

    // It is a single line with no ellipsis, and nothing overflows.
    final text = tester.widget<Text>(find.byKey(const ValueKey('title')));
    expect(text.overflow, isNot(TextOverflow.ellipsis));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a short title stays still', (tester) async {
    await pump(tester, 'Lemon');
    await tester.pump();
    final start = tester.getTopLeft(find.byKey(const ValueKey('title'))).dx;
    await tester.pump(const Duration(seconds: 3));
    expect(tester.getTopLeft(find.byKey(const ValueKey('title'))).dx, start);
    // Nothing is animating, so the screen settles.
    await tester.pumpAndSettle();
  });

  testWidgets('a title that changes from long to short stops gliding', (
    tester,
  ) async {
    await pump(tester, 'A very long song title that cannot fit on one line');
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    await pump(tester, 'Lemon');
    await tester.pump();
    await tester.pump();
    final start = tester.getTopLeft(find.byKey(const ValueKey('title'))).dx;
    await tester.pump(const Duration(seconds: 3));
    expect(tester.getTopLeft(find.byKey(const ValueKey('title'))).dx, start);
    // Nothing keeps animating, so the screen settles.
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}

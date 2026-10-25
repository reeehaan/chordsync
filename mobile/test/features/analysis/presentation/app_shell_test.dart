import 'package:chordsync/features/analysis/presentation/app_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget shell({
    required ValueNotifier<int> tab,
    ValueNotifier<double>? inset,
    bool reduceMotion = false,
  }) => MaterialApp(
    home: Builder(
      builder: (context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
        child: ValueListenableBuilder<int>(
          valueListenable: tab,
          builder: (context, index, _) => AppShell(
            selectedIndex: index,
            onSelected: (value) => tab.value = value,
            bannerInset: inset,
            pages: const [
              Align(
                alignment: Alignment.topLeft,
                child: SizedBox(
                  width: 200,
                  child: TextField(key: ValueKey('search')),
                ),
              ),
              Align(alignment: Alignment.topLeft, child: Text('add page')),
              Align(alignment: Alignment.topLeft, child: Text('tuner page')),
            ],
          ),
        ),
      ),
    ),
  );

  testWidgets('a page keeps what was typed while another tab is open', (
    tester,
  ) async {
    final tab = ValueNotifier(0);
    await tester.pumpWidget(shell(tab: tab));
    await tester.enterText(find.byKey(const ValueKey('search')), 'wonder');

    tab.value = 2;
    await tester.pumpAndSettle();
    expect(find.text('tuner page'), findsOneWidget);
    expect(find.byKey(const ValueKey('search')), findsNothing);

    tab.value = 0;
    await tester.pumpAndSettle();
    expect(find.text('wonder'), findsOneWidget);
    expect(find.text('tuner page'), findsNothing);
  });

  testWidgets('with Reduce Motion the old page goes at once', (tester) async {
    final tab = ValueNotifier(0);
    await tester.pumpWidget(shell(tab: tab, reduceMotion: true));

    tab.value = 1;
    await tester.pump();
    await tester.pump();

    expect(find.text('add page'), findsOneWidget);
    expect(find.byKey(const ValueKey('search')), findsNothing);
  });

  testWidgets('a page hidden by the fade takes no touches', (tester) async {
    final tab = ValueNotifier(0);
    await tester.pumpWidget(shell(tab: tab));

    tab.value = 1;
    await tester.pump(const Duration(milliseconds: 100)); // mid-fade
    final ignoring = tester
        .widgetList<IgnorePointer>(find.byType(IgnorePointer))
        .where((widget) => widget.ignoring)
        .length;
    expect(ignoring, greaterThanOrEqualTo(1));
    await tester.pumpAndSettle();
  });

  testWidgets('the pages make room for the progress banner', (tester) async {
    final tab = ValueNotifier(1);
    final inset = ValueNotifier(0.0);
    await tester.pumpWidget(shell(tab: tab, inset: inset));
    final before = tester.getTopLeft(find.text('add page')).dy;

    inset.value = 80;
    await tester.pumpAndSettle();
    expect(
      tester.getTopLeft(find.text('add page')).dy,
      closeTo(before + 80, 1),
    );

    inset.value = 0;
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(find.text('add page')).dy, closeTo(before, 1));
  });
}

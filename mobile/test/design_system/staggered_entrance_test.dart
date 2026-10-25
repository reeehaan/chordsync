import 'package:chordsync/design_system/staggered_entrance.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget host({required bool reduceMotion}) => MaterialApp(
    home: MediaQuery(
      data: MediaQueryData(disableAnimations: reduceMotion),
      child: const StaggeredEntrance(index: 3, child: Text('card')),
    ),
  );

  testWidgets('fades in, later items a little after earlier ones', (
    tester,
  ) async {
    await tester.pumpWidget(host(reduceMotion: false));
    expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 0);

    await tester.pumpAndSettle();
    expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 1);
  });

  testWidgets('with Reduce Motion the child just appears', (tester) async {
    await tester.pumpWidget(host(reduceMotion: true));
    expect(find.byType(Opacity), findsNothing);
    expect(find.text('card'), findsOneWidget);
  });

  testWidgets('an item that has entered once does not fade in again', (
    tester,
  ) async {
    Widget item(Key key) => MaterialApp(
      home: StaggeredEntrance(
        key: key,
        index: 0,
        identity: 'song-1',
        child: const Text('card'),
      ),
    );

    await tester.pumpWidget(item(const ValueKey('first')));
    expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 0);
    await tester.pumpAndSettle();

    // The item is scrolled away and built again.
    await tester.pumpWidget(const MaterialApp(home: SizedBox()));
    await tester.pumpWidget(item(const ValueKey('second')));
    expect(find.byType(Opacity), findsNothing);
    expect(find.text('card'), findsOneWidget);
  });
}

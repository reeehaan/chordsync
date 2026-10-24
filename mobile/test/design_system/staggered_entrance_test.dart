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
}

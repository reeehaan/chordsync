import 'package:chordsync/design_system/haptics.dart';
import 'package:chordsync/design_system/motion.dart';
import 'package:chordsync/design_system/pressable_scale.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('motion', () {
    testWidgets('keeps its durations normally', (tester) async {
      late Duration result;
      await tester.pumpWidget(
        Builder(
          builder: (context) {
            result = ChordSyncMotion.of(context, ChordSyncMotion.standard);
            return const SizedBox();
          },
        ),
      );
      expect(result, ChordSyncMotion.standard);
    });

    testWidgets('drops every duration when Reduce Motion is on', (
      tester,
    ) async {
      late Duration result;
      late bool reduced;
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Builder(
            builder: (context) {
              result = ChordSyncMotion.of(context, ChordSyncMotion.emphasized);
              reduced = ChordSyncMotion.reduced(context);
              return const SizedBox();
            },
          ),
        ),
      );
      expect(result, Duration.zero);
      expect(reduced, isTrue);
    });
  });

  group('haptics', () {
    final played = <String>[];

    setUp(() {
      played.clear();
      Haptics.enabled = true;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
            if (call.method == 'HapticFeedback.vibrate') {
              played.add(call.arguments as String);
            }
            return null;
          });
    });

    tearDown(() {
      Haptics.enabled = true;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null);
    });

    test('each kind plays its own system haptic', () async {
      Haptics.selection();
      Haptics.light();
      Haptics.success();
      await Future<void>.delayed(Duration.zero);

      expect(played, [
        'HapticFeedbackType.selectionClick',
        'HapticFeedbackType.lightImpact',
        'HapticFeedbackType.mediumImpact',
      ]);
    });

    test('nothing plays once haptics are switched off', () async {
      Haptics.enabled = false;
      Haptics.selection();
      Haptics.light();
      Haptics.success();
      await Future<void>.delayed(Duration.zero);

      expect(played, isEmpty);
    });

    test('a device that cannot vibrate is never an error', () async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, (call) async {
            throw PlatformException(code: 'unavailable');
          });

      Haptics.selection();
      await Future<void>.delayed(Duration.zero);
      // Reaching here without an unhandled error is the assertion.
    });
  });

  group('pressable scale', () {
    Widget app({bool reduceMotion = false, VoidCallback? onTap}) => MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(disableAnimations: reduceMotion),
        child: Scaffold(
          body: Center(
            child: PressableScale(
              child: GestureDetector(
                onTap: onTap,
                child: const ColoredBox(
                  key: ValueKey('target'),
                  color: Colors.orange,
                  child: SizedBox(width: 100, height: 100),
                ),
              ),
            ),
          ),
        ),
      ),
    );

    double scale(WidgetTester tester) =>
        tester.widget<AnimatedScale>(find.byType(AnimatedScale)).scale;

    testWidgets('shrinks under a finger and springs back', (tester) async {
      await tester.pumpWidget(app());
      expect(scale(tester), 1);

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(const ValueKey('target'))),
      );
      await tester.pump();
      expect(scale(tester), lessThan(1));

      await gesture.up();
      await tester.pump();
      expect(scale(tester), 1);
      await tester.pumpAndSettle();
    });

    testWidgets('a cancelled touch also springs back', (tester) async {
      await tester.pumpWidget(app());
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(const ValueKey('target'))),
      );
      await tester.pump();
      await gesture.cancel();
      await tester.pump();
      expect(scale(tester), 1);
    });

    testWidgets('sliding away to scroll lets the card go', (tester) async {
      await tester.pumpWidget(app());
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(const ValueKey('target'))),
      );
      await tester.pump();
      expect(scale(tester), lessThan(1));

      await gesture.moveBy(const Offset(0, -40));
      await tester.pump();
      expect(scale(tester), 1);
      await gesture.up();
      await tester.pumpAndSettle();
    });

    testWidgets('the child keeps its own tap', (tester) async {
      var taps = 0;
      await tester.pumpWidget(app(onTap: () => taps++));

      await tester.tap(find.byKey(const ValueKey('target')));
      await tester.pumpAndSettle();

      expect(taps, 1);
    });

    testWidgets('with Reduce Motion the press does not animate', (
      tester,
    ) async {
      await tester.pumpWidget(app(reduceMotion: true));
      final animated = tester.widget<AnimatedScale>(find.byType(AnimatedScale));
      expect(animated.duration, Duration.zero);
    });
  });
}

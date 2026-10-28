import 'package:chordsync/design_system/appearance_controller.dart';
import 'package:chordsync/design_system/chordsync_design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  tearDown(() => ChordSyncColors.dark = false);

  test('auto follows the phone, light and dark do not', () {
    expect(Appearance.system.resolvesDark(Brightness.dark), isTrue);
    expect(Appearance.system.resolvesDark(Brightness.light), isFalse);
    expect(Appearance.light.resolvesDark(Brightness.dark), isFalse);
    expect(Appearance.dark.resolvesDark(Brightness.light), isTrue);
  });

  test('the choice is remembered and loaded on the next launch', () async {
    final store = MemoryAppearanceStore();
    final first = AppearanceController(store: store);
    await first.select(Appearance.dark);

    final second = AppearanceController(store: store);
    expect(second.appearance, Appearance.system);
    await second.load();
    expect(second.appearance, Appearance.dark);
  });

  test('the dark theme swaps the page, text and accent colours', () {
    final light = ChordSyncTheme.light();
    final lightPage = light.scaffoldBackgroundColor;
    final dark = ChordSyncTheme.dark();

    expect(dark.brightness, Brightness.dark);
    expect(dark.scaffoldBackgroundColor, isNot(lightPage));
    expect(ChordSyncColors.dark, isTrue);
    // Text stays readable: lighter than the page it sits on.
    expect(
      ChordSyncColors.textPrimary.computeLuminance(),
      greaterThan(ChordSyncColors.background.computeLuminance() + 0.5),
    );
  });
}

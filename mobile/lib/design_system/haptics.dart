import 'dart:async';

import 'package:flutter/services.dart';

/// Short haptic taps that back up what is on screen.
///
/// Used sparingly and always with a visible change, never alone, and a person
/// can switch them off ([enabled]). A failure to vibrate is never an error.
abstract final class Haptics {
  /// Switched off by a setting; on by default.
  static bool enabled = true;

  /// A selection moved: a tab, a segment, a picker value.
  static void selection() => _play(HapticFeedback.selectionClick);

  /// A light confirmation: an action started.
  static void light() => _play(HapticFeedback.lightImpact);

  /// Something finished well: a song is ready.
  static void success() => _play(HapticFeedback.mediumImpact);

  static void _play(Future<void> Function() haptic) {
    if (!enabled) return;
    unawaited(haptic().catchError((Object _) {}));
  }
}

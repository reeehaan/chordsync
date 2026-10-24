import 'package:flutter/material.dart';

/// How things move in ChordSync, in one place.
///
/// Motion is short and purposeful (Apple's guidance: never decoration for its
/// own sake) and it is optional: with the system's Reduce Motion setting on,
/// every duration here becomes zero, so changes still happen but do not
/// animate. State is never communicated by motion alone.
abstract final class ChordSyncMotion {
  /// Feedback to a touch: a press, a toggle.
  static const quick = Duration(milliseconds: 140);

  /// A control or card changing state.
  static const standard = Duration(milliseconds: 300);

  /// Something arriving or a view changing place.
  static const emphasized = Duration(milliseconds: 420);

  /// Things that arrive: start fast, settle gently.
  static const Curve enter = Curves.easeOutCubic;

  /// Things that leave: start gently, finish fast.
  static const Curve exit = Curves.easeInCubic;

  /// A little overshoot on release, like an iOS spring.
  static const Curve spring = Curves.easeOutBack;

  /// A real spring, for physics-driven animation controllers.
  static const SpringDescription springDescription = SpringDescription(
    mass: 1,
    stiffness: 380,
    damping: 30,
  );

  /// True when the person asked the system to reduce motion.
  static bool reduced(BuildContext context) =>
      MediaQuery.disableAnimationsOf(context);

  /// [duration], or zero when motion is reduced.
  static Duration of(BuildContext context, Duration duration) =>
      reduced(context) ? Duration.zero : duration;
}

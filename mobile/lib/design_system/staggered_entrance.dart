import 'package:flutter/material.dart';

import 'motion.dart';

/// Fades and lifts its child into place once, a little after the items before
/// it. Only the first few items stagger, so a long list never feels slow.
/// With Reduce Motion on, the child simply appears.
class StaggeredEntrance extends StatelessWidget {
  const StaggeredEntrance({
    super.key,
    required this.index,
    required this.child,
  });

  final int index;
  final Widget child;

  static const _step = Duration(milliseconds: 60);
  static const _maxStaggered = 8;

  @override
  Widget build(BuildContext context) {
    if (ChordSyncMotion.reduced(context)) return child;
    final delay = _step * index.clamp(0, _maxStaggered);
    final total = delay + ChordSyncMotion.standard;
    final start = delay.inMilliseconds / total.inMilliseconds;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(start, 1, curve: ChordSyncMotion.enter),
      child: child,
      builder: (context, t, child) => Opacity(
        opacity: t,
        child: Transform.translate(
          offset: Offset(0, 14 * (1 - t)),
          child: child,
        ),
      ),
    );
  }
}

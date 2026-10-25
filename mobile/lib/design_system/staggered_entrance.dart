import 'package:flutter/material.dart';

import 'motion.dart';

/// Fades and lifts its child into place once, a little after the items before
/// it. Only the first few items stagger, so a long list never feels slow.
/// With Reduce Motion on, the child simply appears.
class StaggeredEntrance extends StatefulWidget {
  const StaggeredEntrance({
    super.key,
    required this.index,
    required this.child,
    this.identity,
  });

  final int index;
  final Widget child;

  /// Names what is entering. Each identity plays its entrance once per run of
  /// the app, so a list item scrolled away and back does not fade in again.
  final Object? identity;

  static final _played = <Object>{};

  static const _step = Duration(milliseconds: 60);
  static const _maxStaggered = 8;

  @override
  State<StaggeredEntrance> createState() => _StaggeredEntranceState();
}

class _StaggeredEntranceState extends State<StaggeredEntrance> {
  // Decided once, when the item first appears, so a rebuild mid-fade cannot
  // cut the animation short.
  late final bool _alreadyPlayed;

  @override
  void initState() {
    super.initState();
    final identity = widget.identity;
    _alreadyPlayed =
        identity != null && !StaggeredEntrance._played.add(identity);
  }

  @override
  Widget build(BuildContext context) {
    if (_alreadyPlayed || ChordSyncMotion.reduced(context)) return widget.child;
    final delay =
        StaggeredEntrance._step *
        widget.index.clamp(0, StaggeredEntrance._maxStaggered);
    final total = delay + ChordSyncMotion.standard;
    final start = delay.inMilliseconds / total.inMilliseconds;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(start, 1, curve: ChordSyncMotion.enter),
      child: widget.child,
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

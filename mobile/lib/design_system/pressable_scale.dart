import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';

import 'motion.dart';

/// Gives its child a springy press: it shrinks slightly while a finger is down
/// and settles back with a small overshoot. It only listens to the pointer, so
/// the child keeps its own tap handling.
class PressableScale extends StatefulWidget {
  const PressableScale({
    super.key,
    required this.child,
    this.pressedScale = 0.97,
  });

  final Widget child;

  /// The size while pressed, as a fraction of the normal size.
  final double pressedScale;

  @override
  State<PressableScale> createState() => _PressableScaleState();
}

class _PressableScaleState extends State<PressableScale> {
  bool _pressed = false;
  Offset? _downAt;

  void _set(bool pressed) {
    if (_pressed != pressed) setState(() => _pressed = pressed);
  }

  // A finger that slides away is scrolling, not pressing: let the card go.
  void _moved(PointerMoveEvent event) {
    final start = _downAt;
    if (start != null && (event.position - start).distance > kTouchSlop) {
      _set(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      onPointerDown: (event) {
        _downAt = event.position;
        _set(true);
      },
      onPointerMove: _moved,
      onPointerUp: (_) => _set(false),
      onPointerCancel: (_) => _set(false),
      child: AnimatedScale(
        scale: _pressed ? widget.pressedScale : 1,
        duration: ChordSyncMotion.of(
          context,
          _pressed ? const Duration(milliseconds: 90) : ChordSyncMotion.quick,
        ),
        curve: _pressed ? Curves.easeOut : ChordSyncMotion.spring,
        child: widget.child,
      ),
    );
  }
}

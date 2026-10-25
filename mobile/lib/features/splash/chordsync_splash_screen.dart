import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../design_system/chordsync_design_system.dart';
import 'splash_sound.dart';

/// The opening moment, light theme only for now: the icon alone, big. The C
/// shape appears, the three strings draw in, then a short tab of natural
/// harmonics (open C tuning, so C major) is picked: each note moves a string
/// as a real recorded guitar sounds it, at the phone's own volume. Then the
/// app goes on.
///
/// With Reduce Motion on, the finished icon shows briefly, in silence.
class ChordSyncSplashScreen extends StatefulWidget {
  const ChordSyncSplashScreen({
    super.key,
    this.onFinished,
    this.sound = const NoSplashSound(),
  });

  /// Called once, when the intro has played.
  final VoidCallback? onFinished;

  /// The strummed chord. Silent by default.
  final SplashSound sound;

  static const duration = Duration(milliseconds: 2700);
  static const reducedMotionDuration = Duration(milliseconds: 400);

  /// When the first note is picked, in milliseconds from the beginning.
  static const pickStartMs = 900.0;

  /// The time between notes (tool/generate_splash_chord.py uses the same).
  static const pickStepMs = 160.0;

  /// Which of the five drawn strings moves for each note of the tab, in order
  /// (0 is the top, thinnest string, 1st on a guitar; 4 is the bottom, 5th).
  /// The tab is picked 5th, 4th, 3rd, 2nd, 1st, then 2nd, 3rd, 4th string.
  static const pickStrings = [4, 3, 2, 1, 0, 1, 2, 3];

  /// Starting the sound a little early, so it is heard as the strings move:
  /// the player takes a moment to begin.
  static const soundLeadMs = 60.0;

  @override
  State<ChordSyncSplashScreen> createState() => _ChordSyncSplashScreenState();
}

class _ChordSyncSplashScreenState extends State<ChordSyncSplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: ChordSyncSplashScreen.duration,
  )..addListener(_maybeStartSound);

  // The sound this splash began with, whatever the parent rebuilds into.
  late final SplashSound _sound = widget.sound;
  bool _started = false;
  bool _soundStarted = false;

  double get _elapsedMs =>
      _controller.value * ChordSyncSplashScreen.duration.inMilliseconds;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      // No movement and no sound: the finished icon, then on.
      _soundStarted = true; // before the jump, which would start the sound
      _controller.value = 1;
      Future<void>.delayed(
        ChordSyncSplashScreen.reducedMotionDuration,
        _finish,
      );
    } else {
      _sound.load();
      _controller.forward().whenComplete(_finish);
    }
  }

  void _maybeStartSound() {
    if (_soundStarted) return;
    if (_elapsedMs >=
        ChordSyncSplashScreen.pickStartMs - ChordSyncSplashScreen.soundLeadMs) {
      _soundStarted = true;
      _sound.play();
    }
  }

  void _finish() {
    if (mounted) widget.onFinished?.call();
  }

  @override
  void dispose() {
    _controller.dispose();
    _sound.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final side = math.min(MediaQuery.sizeOf(context).width * 0.66, 300.0);
    return Scaffold(
      backgroundColor: ChordSyncColors.background,
      body: Center(
        child: Semantics(
          label: 'ChordSync',
          image: true,
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, _) => CustomPaint(
              size: Size.square(side),
              painter: ChordSyncMarkPainter(elapsedMs: _elapsedMs),
            ),
          ),
        ),
      ),
    );
  }
}

/// Draws the ChordSync mark (the same artwork as assets/icons/chordsync_icon.svg,
/// without its background square) as it builds up and is strummed.
class ChordSyncMarkPainter extends CustomPainter {
  ChordSyncMarkPainter({required this.elapsedMs});

  /// Milliseconds since the splash began.
  final double elapsedMs;

  // The artwork lives in a 512-unit square, centred (see the SVG).
  static const _units = 512.0;
  static const _shift = Offset(1.5, 14.5);

  // Each string: left end, control point and right end (the amber dot).
  // The same five strings as assets/icons/chordsync_icon.svg.
  static const _strings = [
    [Offset(234, 210), Offset(290, 213), Offset(352, 207), Offset(360, 207)],
    [
      Offset(228, 228.5),
      Offset(290, 231.5),
      Offset(352, 225.5),
      Offset(360, 225.5),
    ],
    [Offset(228, 247), Offset(290, 250), Offset(352, 244), Offset(360, 244)],
    [
      Offset(233, 265.5),
      Offset(290, 268.5),
      Offset(352, 262.5),
      Offset(360, 262.5),
    ],
    [Offset(244, 284), Offset(290, 287), Offset(352, 281), Offset(360, 281)],
  ];

  static const _stringWidth = 7.0;
  static const _dotRadius = 8.5;

  // Thin strings shiver faster than thick ones.
  static const _wiggleHz = [11.0, 10.0, 9.0, 8.0, 7.0];
  static const _wiggleAmplitude = 5.0; // units, per pick
  static const _wiggleLimit = 8.0; // units, however many picks pile up
  static const _wiggleDecaySeconds = 0.5;

  static Path _pick() => Path()
    ..moveTo(337, 96)
    ..cubicTo(281, 83, 216, 117, 164, 159)
    ..cubicTo(119, 196, 132, 251, 164, 303)
    ..cubicTo(194, 352, 237, 399, 269, 389)
    ..cubicTo(309, 377, 344, 326, 368, 294)
    ..cubicTo(377, 282, 367, 272, 355, 280)
    ..cubicTo(319, 302, 290, 323, 260, 306)
    ..cubicTo(223, 286, 204, 248, 218, 211)
    ..cubicTo(232, 174, 267, 158, 302, 171)
    ..cubicTo(327, 181, 344, 195, 361, 195)
    ..cubicTo(377, 195, 379, 180, 367, 159)
    ..cubicTo(358, 141, 350, 110, 337, 96)
    ..close();

  static double _ease(Curve curve, double t) => curve.transform(t.clamp(0, 1));

  /// A point on string [i], [u] of the way from its amber dot (0) to its free
  /// end (1), moved sideways by the strum.
  Offset _stringPoint(int i, double u) {
    final s = _strings[i];
    final free = s[0];
    final control = s[1];
    final fixed = s[2];
    // The curve runs from the free end through the control point to the end
    // by the dot, so measure along it from the dot.
    final v = 1 - u;
    final x =
        math.pow(1 - v, 2) * free.dx +
        2 * (1 - v) * v * control.dx +
        v * v * fixed.dx;
    final y =
        math.pow(1 - v, 2) * free.dy +
        2 * (1 - v) * v * control.dy +
        v * v * fixed.dy;
    return Offset(x.toDouble(), y.toDouble() + _wiggle(i, u));
  }

  /// Seconds since each pick of string [string] began, for the picks so far.
  Iterable<double> _pickAges(int string) sync* {
    final picks = ChordSyncSplashScreen.pickStrings;
    for (var n = 0; n < picks.length; n++) {
      if (picks[n] != string) continue;
      final seconds =
          (elapsedMs -
              (ChordSyncSplashScreen.pickStartMs +
                  n * ChordSyncSplashScreen.pickStepMs)) /
          1000;
      if (seconds > 0) yield seconds;
    }
  }

  /// Sideways movement of string [i] at position [u]: a standing wave that is
  /// still at both ends, swings most in the middle and dies away. Picks that
  /// follow each other add up, so a busy string shimmers.
  double _wiggle(int i, double u) {
    var total = 0.0;
    for (final seconds in _pickAges(i)) {
      total +=
          _wiggleAmplitude *
          math.exp(-seconds / _wiggleDecaySeconds) *
          math.sin(2 * math.pi * _wiggleHz[i] * seconds);
    }
    return total.clamp(-_wiggleLimit, _wiggleLimit) * math.sin(math.pi * u);
  }

  @override
  void paint(Canvas canvas, Size size) {
    final unit = size.width / _units;
    canvas.save();
    canvas.scale(unit);
    canvas.translate(_shift.dx, _shift.dy);

    // The C shape grows and fades in.
    final shapeT = (elapsedMs / 520).clamp(0.0, 1.0);
    final scale = 0.82 + 0.18 * _ease(Curves.easeOutBack, shapeT);
    final opacity = (elapsedMs / 300).clamp(0.0, 1.0);
    canvas.save();
    canvas.translate(_units / 2 - _shift.dx, _units / 2 - _shift.dy);
    canvas.scale(scale);
    canvas.translate(-(_units / 2 - _shift.dx), -(_units / 2 - _shift.dy));
    canvas.drawPath(
      _pick(),
      Paint()
        ..color = ChordSyncColors.brand.withValues(alpha: opacity)
        ..isAntiAlias = true,
    );
    canvas.restore();

    final stringPaint = Paint()
      ..color = ChordSyncColors.brandDark
      ..strokeWidth = _stringWidth
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke
      ..isAntiAlias = true;

    for (var i = 0; i < _strings.length; i++) {
      // A string draws itself outward from its dot.
      final start = 250.0 + i * 70;
      final drawn = _ease(Curves.easeOutCubic, (elapsedMs - start) / 300);
      if (drawn > 0) {
        final path = Path();
        const steps = 28;
        for (var step = 0; step <= steps; step++) {
          final u = drawn * step / steps;
          final p = _stringPoint(i, u);
          if (step == 0) {
            path.moveTo(p.dx, p.dy);
          } else {
            path.lineTo(p.dx, p.dy);
          }
        }
        canvas.drawPath(path, stringPaint);
      }

      // The amber dot pops in once its string is out, and pulses on the pluck.
      final popStart = start + 240;
      final pop = _ease(Curves.easeOutBack, (elapsedMs - popStart) / 220);
      if (pop > 0) {
        var pulse = 0.0;
        for (final seconds in _pickAges(i)) {
          pulse = math.max(pulse, 0.18 * math.exp(-seconds / 0.18));
        }
        final centre = _strings[i][3];
        final radius = _dotRadius * pop * (1 + pulse);
        canvas.drawCircle(
          centre,
          radius,
          Paint()..color = ChordSyncColors.honey,
        );
        canvas.drawCircle(
          centre,
          radius,
          Paint()
            ..color = ChordSyncColors.background
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.6,
        );
      }
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant ChordSyncMarkPainter oldDelegate) =>
      oldDelegate.elapsedMs != elapsedMs;
}

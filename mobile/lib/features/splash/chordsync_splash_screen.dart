import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../design_system/chordsync_design_system.dart';

/// The opening moment: the icon grows into place, amber flares open behind it
/// and the name and tagline fade in. Light theme only for now.
///
/// With Reduce Motion on, the finished frame shows briefly and the app goes on.
class ChordSyncSplashScreen extends StatefulWidget {
  const ChordSyncSplashScreen({super.key, this.onFinished});

  /// Called once, when the intro has played.
  final VoidCallback? onFinished;

  static const duration = Duration(milliseconds: 2200);
  static const reducedMotionDuration = Duration(milliseconds: 400);

  @override
  State<ChordSyncSplashScreen> createState() => _ChordSyncSplashScreenState();
}

class _ChordSyncSplashScreenState extends State<ChordSyncSplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: ChordSyncSplashScreen.duration,
  );

  late final Animation<double> _iconScale = Tween<double>(begin: 0.72, end: 1.0)
      .animate(
        CurvedAnimation(
          parent: _controller,
          curve: const Interval(0.0, 0.55, curve: Curves.easeOutBack),
        ),
      );
  late final Animation<double> _iconOpacity = CurvedAnimation(
    parent: _controller,
    curve: const Interval(0.0, 0.25, curve: Curves.easeIn),
  );
  late final Animation<double> _textOpacity = CurvedAnimation(
    parent: _controller,
    curve: const Interval(0.45, 0.8, curve: Curves.easeIn),
  );

  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      // No movement: show the finished splash, then go on.
      _controller.value = 1;
      Future<void>.delayed(
        ChordSyncSplashScreen.reducedMotionDuration,
        _finish,
      );
    } else {
      _controller.forward().whenComplete(_finish);
    }
  }

  void _finish() {
    if (mounted) widget.onFinished?.call();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      backgroundColor: ChordSyncColors.background,
      body: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => Stack(
          fit: StackFit.expand,
          children: [
            // Golden flares behind the icon.
            CustomPaint(
              painter: GoldenFlarePainter(progress: _controller.value),
            ),
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  FadeTransition(
                    opacity: _iconOpacity,
                    child: ScaleTransition(
                      scale: _iconScale,
                      child: SvgPicture.asset(
                        'assets/icons/chordsync_icon.svg',
                        width: 152,
                        height: 152,
                        semanticsLabel: 'ChordSync',
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  FadeTransition(
                    opacity: _textOpacity,
                    child: Column(
                      children: [
                        Text(
                          'ChordSync',
                          style: textTheme.displayMedium?.copyWith(
                            color: ChordSyncColors.textPrimary,
                            fontSize: 32,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -0.8,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Find your rhythm.',
                          style: textTheme.bodyMedium?.copyWith(
                            color: ChordSyncColors.textSecondary,
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Amber rays and a soft halo that open outward and fade behind the icon.
class GoldenFlarePainter extends CustomPainter {
  GoldenFlarePainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2 - 35);

    final t = Curves.easeOut.transform(
      ((progress - 0.12) / 0.58).clamp(0.0, 1.0),
    );
    final fade = (1.0 - t).clamp(0.0, 1.0);
    final radius = 100.0 + 100.0 * t;

    final flarePaint = Paint()
      ..color = ChordSyncColors.honey.withValues(alpha: 0.65 * fade)
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    for (var i = 0; i < 12; i++) {
      final angle = (2 * math.pi * i / 12) - math.pi / 2;
      final endRadius = radius + 8 + (i % 3) * 5;
      canvas.drawLine(
        Offset(
          center.dx + math.cos(angle) * radius,
          center.dy + math.sin(angle) * radius,
        ),
        Offset(
          center.dx + math.cos(angle) * endRadius,
          center.dy + math.sin(angle) * endRadius,
        ),
        flarePaint,
      );
    }

    final haloPaint = Paint()
      ..color = ChordSyncColors.honey.withValues(alpha: 0.10 * fade)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 28);
    canvas.drawCircle(center, 75 + 25 * t, haloPaint);
  }

  @override
  bool shouldRepaint(covariant GoldenFlarePainter oldDelegate) =>
      oldDelegate.progress != progress;
}

import 'package:flutter/material.dart';

/// One line of text that glides sideways to show all of it when it is too long
/// for the space, and sits still when it fits.
class MarqueeText extends StatefulWidget {
  const MarqueeText(this.text, {super.key, this.style, this.textKey});

  final String text;
  final TextStyle? style;

  /// Key of the inner [Text], so callers can find the visible title.
  final Key? textKey;

  /// How fast the text glides, and how long it rests at each end.
  static const pixelsPerSecond = 30.0;
  static const rest = Duration(milliseconds: 1500);

  @override
  State<MarqueeText> createState() => _MarqueeTextState();
}

class _MarqueeTextState extends State<MarqueeText>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);
  double _overflow = 0;
  Animation<double>? _offset;

  /// Sets up (or stops) the glide for the current overflow. Called from build,
  /// so the controller is only touched after the frame.
  void _configure(double overflow) {
    if ((overflow - _overflow).abs() < 0.5) return;
    _overflow = overflow;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _controller.stop();
      if (overflow <= 0) {
        setState(() => _offset = null);
        return;
      }
      final travelMs = (overflow / MarqueeText.pixelsPerSecond * 1000)
          .round()
          .clamp(1, 1 << 30);
      final restMs = MarqueeText.rest.inMilliseconds;
      _controller.duration = Duration(milliseconds: 2 * (restMs + travelMs));
      TweenSequenceItem<double> hold(double value) => TweenSequenceItem(
        tween: ConstantTween(value),
        weight: restMs.toDouble(),
      );
      TweenSequenceItem<double> move(double from, double to) =>
          TweenSequenceItem(
            tween: Tween(
              begin: from,
              end: to,
            ).chain(CurveTween(curve: Curves.easeInOut)),
            weight: travelMs.toDouble(),
          );
      setState(() {
        _offset = TweenSequence<double>([
          hold(0),
          move(0, -overflow),
          hold(-overflow),
          move(-overflow, 0),
        ]).animate(_controller);
      });
      _controller.repeat();
    });
  }

  @override
  void didUpdateWidget(covariant MarqueeText oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.text != widget.text || oldWidget.style != widget.style) {
      _overflow = -1; // measure again, even if it fits
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// The label at its full width, however narrow the space it is clipped to.
  Widget _wide(Widget label, double height) => SizedBox(
    height: height,
    child: OverflowBox(
      alignment: Alignment.centerLeft,
      minWidth: 0,
      maxWidth: double.infinity,
      child: label,
    ),
  );

  @override
  Widget build(BuildContext context) {
    final style = DefaultTextStyle.of(context).style.merge(widget.style);
    return LayoutBuilder(
      builder: (context, constraints) {
        final painter = TextPainter(
          text: TextSpan(text: widget.text, style: style),
          maxLines: 1,
          textDirection: Directionality.of(context),
          textScaler: MediaQuery.textScalerOf(context),
        )..layout();
        final overflow = constraints.maxWidth.isFinite
            ? (painter.width - constraints.maxWidth).clamp(0.0, double.infinity)
            : 0.0;
        final height = painter.height;
        painter.dispose();
        _configure(overflow);

        final label = Text(
          widget.text,
          key: widget.textKey,
          maxLines: 1,
          softWrap: false,
          style: widget.style,
        );
        final offset = _offset;
        if (overflow <= 0 || offset == null) {
          return overflow <= 0 ? label : ClipRect(child: _wide(label, height));
        }
        return ClipRect(
          child: AnimatedBuilder(
            animation: offset,
            builder: (context, child) => Transform.translate(
              offset: Offset(offset.value, 0),
              child: child,
            ),
            child: _wide(label, height),
          ),
        );
      },
    );
  }
}

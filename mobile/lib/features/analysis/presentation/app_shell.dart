import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/motion.dart';
import 'upload_theme.dart';

/// Themed scaffold with the bottom tab dock. It holds the library, add-song
/// and tuner pages together and keeps all three alive, so a search or a scroll
/// position survives a trip to another tab.
class AppShell extends StatelessWidget {
  const AppShell({
    super.key,
    required this.pages,
    required this.selectedIndex,
    required this.onSelected,
    this.bannerInset,
  });

  /// One page per dock item, in dock order.
  final List<Widget> pages;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  /// How far the progress banner hangs below the safe area; the pages move
  /// down by this much so the banner never covers their titles.
  final ValueListenable<double>? bannerInset;

  @override
  Widget build(BuildContext context) {
    final inset = bannerInset;
    final body = Stack(
      fit: StackFit.expand,
      alignment: Alignment.topCenter,
      children: [
        for (var i = 0; i < pages.length; i++)
          _TabPage(selected: i == selectedIndex, child: pages[i]),
      ],
    );
    return Theme(
      data: uploadTheme(context),
      child: Scaffold(
        // The dock floats over the page; the page learns its height through
        // MediaQuery padding, so lists can scroll under the glass.
        extendBody: true,
        body: SafeArea(
          bottom: false,
          child: inset == null
              ? body
              : ValueListenableBuilder<double>(
                  valueListenable: inset,
                  child: body,
                  builder: (context, value, child) => AnimatedPadding(
                    duration: ChordSyncMotion.of(
                      context,
                      ChordSyncMotion.standard,
                    ),
                    curve: ChordSyncMotion.enter,
                    padding: EdgeInsets.only(top: value),
                    child: child,
                  ),
                ),
        ),
        bottomNavigationBar: BottomDock(
          selectedIndex: selectedIndex,
          onSelected: onSelected,
        ),
      ),
    );
  }
}

/// One tab's page. It fades in when chosen and fades out when left, but is
/// never torn down: its state stays, and while hidden it takes no touches, no
/// screen-reader focus, no animation ticks and no scroll-to-top.
class _TabPage extends StatefulWidget {
  const _TabPage({required this.selected, required this.child});

  final bool selected;
  final Widget child;

  @override
  State<_TabPage> createState() => _TabPageState();
}

class _TabPageState extends State<_TabPage> {
  late bool _shown = widget.selected;

  @override
  void didUpdateWidget(_TabPage old) {
    super.didUpdateWidget(old);
    if (widget.selected) _shown = true;
  }

  @override
  Widget build(BuildContext context) {
    final inherited = PrimaryScrollController.maybeOf(context);
    final page = widget.child;
    // With Reduce Motion there is no fade to wait for: a page that is not
    // chosen is gone at once.
    final gone =
        !_shown || (!widget.selected && ChordSyncMotion.reduced(context));
    return Offstage(
      offstage: gone,
      child: IgnorePointer(
        ignoring: !widget.selected,
        child: ExcludeSemantics(
          excluding: !widget.selected,
          child: AnimatedOpacity(
            opacity: widget.selected ? 1 : 0,
            duration: ChordSyncMotion.of(context, ChordSyncMotion.standard),
            curve: widget.selected
                ? ChordSyncMotion.enter
                : ChordSyncMotion.exit,
            // With no fade (Reduce Motion) this fires while building, so the
            // state change waits for the end of the frame.
            onEnd: () => WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!widget.selected && mounted) setState(() => _shown = false);
            }),
            child: TickerMode(
              enabled: _shown,
              // Only the page on show answers the status-bar tap that scrolls
              // to the top; two pages must not share the route's controller.
              child: inherited != null && widget.selected
                  ? PrimaryScrollController(controller: inherited, child: page)
                  : PrimaryScrollController.none(child: page),
            ),
          ),
        ),
      ),
    );
  }
}

/// A frosted-glass tab dock. Navigation only: it never holds actions.
class BottomDock extends StatelessWidget {
  const BottomDock({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  static const _height = 64.0;

  void _select(int index) {
    if (index != selectedIndex) Haptics.selection();
    onSelected(index);
  }

  @override
  Widget build(BuildContext context) {
    const items = [
      ('assets/icons/source_providers/home.svg', 'Home'),
      ('assets/icons/source_providers/plus.svg', 'Add song'),
      ('assets/icons/source_providers/tuner.svg', 'Tuner'),
    ];
    // Increase Contrast turns the glass nearly opaque so icons stay legible.
    final highContrast = MediaQuery.highContrastOf(context);
    final radius = BorderRadius.circular(_height / 2);
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(24, 8, 24, 12),
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: radius,
          boxShadow: const [
            BoxShadow(
              color: UploadPalette.dockShadow,
              blurRadius: 24,
              offset: Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: radius,
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 22, sigmaY: 22),
            child: Container(
              height: _height,
              decoration: BoxDecoration(
                color: ChordSyncColors.background.withValues(
                  alpha: highContrast ? 0.97 : 0.72,
                ),
                borderRadius: radius,
                border: Border.all(
                  color: highContrast
                      ? ChordSyncColors.textSecondary
                      : Colors.white.withValues(alpha: 0.65),
                  width: highContrast ? 1 : 0.8,
                ),
              ),
              child: LayoutBuilder(
                builder: (context, box) {
                  final slot = box.maxWidth / items.length;
                  return Stack(
                    children: [
                      _SlidingCapsule(index: selectedIndex, slot: slot),
                      Row(
                        children: List.generate(items.length, (index) {
                          final selected = selectedIndex == index;
                          return Expanded(
                            child: Semantics(
                              selected: selected,
                              label: items[index].$2,
                              button: true,
                              child: InkResponse(
                                key: ValueKey('bottomNav$index'),
                                highlightShape: BoxShape.rectangle,
                                splashColor: Colors.transparent,
                                highlightColor: Colors.transparent,
                                hoverColor: Colors.transparent,
                                overlayColor: const WidgetStatePropertyAll(
                                  Colors.transparent,
                                ),
                                borderRadius: BorderRadius.circular(32),
                                onTap: () => _select(index),
                                child: SizedBox(
                                  height: _height,
                                  child: Center(
                                    child: TweenAnimationBuilder<Color?>(
                                      duration: ChordSyncMotion.of(
                                        context,
                                        ChordSyncMotion.quick,
                                      ),
                                      tween: ColorTween(
                                        end: selected
                                            ? ChordSyncColors.brand
                                            : ChordSyncColors.textSecondary,
                                      ),
                                      builder: (context, color, _) =>
                                          SvgPicture.asset(
                                            items[index].$1,
                                            width: index == 1 ? 32 : 27,
                                            height: index == 1 ? 32 : 27,
                                            colorFilter: ColorFilter.mode(
                                              color!,
                                              BlendMode.srcIn,
                                            ),
                                          ),
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          );
                        }),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The selection capsule. It glides on a spring, stretches a little in the
/// direction of travel and settles with a soft overshoot.
class _SlidingCapsule extends StatefulWidget {
  const _SlidingCapsule({required this.index, required this.slot});

  final int index;
  final double slot;

  @override
  State<_SlidingCapsule> createState() => _SlidingCapsuleState();
}

class _SlidingCapsuleState extends State<_SlidingCapsule>
    with SingleTickerProviderStateMixin {
  static const _spring = SpringDescription(
    mass: 1,
    stiffness: 260,
    damping: 24,
  );

  // Position in tab units (1.0 = one tab across); unbounded for overshoot.
  late final AnimationController _position = AnimationController.unbounded(
    vsync: this,
    value: widget.index.toDouble(),
  );

  @override
  void didUpdateWidget(_SlidingCapsule old) {
    super.didUpdateWidget(old);
    if (old.index == widget.index) return;
    if (ChordSyncMotion.reduced(context)) {
      _position.value = widget.index.toDouble();
      return;
    }
    _position.animateWith(
      SpringSimulation(
        _spring,
        _position.value,
        widget.index.toDouble(),
        _position.velocity,
      ),
    );
  }

  @override
  void dispose() {
    _position.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _position,
      builder: (context, _) {
        // Stretch with speed (tabs per second), up to 30% wider.
        final stretch = 1 + (_position.velocity.abs() * 0.12).clamp(0.0, 0.3);
        final width = widget.slot * stretch;
        final center = (_position.value + 0.5) * widget.slot;
        return Positioned(
          left: center - width / 2,
          width: width,
          top: 0,
          bottom: 0,
          child: Container(
            margin: const EdgeInsets.all(7),
            decoration: BoxDecoration(
              color: ChordSyncColors.surfaceAlt.withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(28),
            ),
          ),
        );
      },
    );
  }
}

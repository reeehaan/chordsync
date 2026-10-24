import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/motion.dart';
import 'upload_theme.dart';

/// Themed scaffold with the bottom tab dock, used by the library and tuner tabs.
class AppShell extends StatelessWidget {
  const AppShell({
    super.key,
    required this.child,
    required this.selectedIndex,
    required this.onSelected,
  });

  final Widget child;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: uploadTheme(context),
      child: Scaffold(
        // The dock floats over the page; the page learns its height through
        // MediaQuery padding, so lists can scroll under the glass.
        extendBody: true,
        body: SafeArea(bottom: false, child: child),
        bottomNavigationBar: BottomDock(
          selectedIndex: selectedIndex,
          onSelected: onSelected,
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
                      AnimatedPositioned(
                        duration: ChordSyncMotion.of(
                          context,
                          ChordSyncMotion.standard,
                        ),
                        curve: ChordSyncMotion.spring,
                        left: slot * selectedIndex,
                        top: 0,
                        bottom: 0,
                        width: slot,
                        child: Container(
                          margin: const EdgeInsets.all(7),
                          decoration: BoxDecoration(
                            color: ChordSyncColors.surfaceAlt.withValues(
                              alpha: 0.9,
                            ),
                            borderRadius: BorderRadius.circular(28),
                          ),
                        ),
                      ),
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

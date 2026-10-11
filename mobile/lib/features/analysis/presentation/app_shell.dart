import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

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
        body: SafeArea(child: child),
        bottomNavigationBar: BottomDock(
          selectedIndex: selectedIndex,
          onSelected: onSelected,
        ),
      ),
    );
  }
}

class BottomDock extends StatelessWidget {
  const BottomDock({
    super.key,
    required this.selectedIndex,
    required this.onSelected,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    const items = [
      ('assets/icons/source_providers/home.svg', 'Home'),
      ('assets/icons/source_providers/plus.svg', 'Add song'),
      ('assets/icons/source_providers/tuner.svg', 'Tuner'),
    ];
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(24, 8, 24, 12),
      child: Container(
        height: 68,
        decoration: BoxDecoration(
          color: UploadPalette.dock,
          borderRadius: BorderRadius.circular(34),
          border: Border.all(color: UploadPalette.border),
          boxShadow: const [
            BoxShadow(
              color: Color(0x292B1B12),
              blurRadius: 18,
              offset: Offset(0, 8),
            ),
          ],
        ),
        child: Row(
          children: List.generate(items.length, (index) {
            final selected = selectedIndex == index;
            return Expanded(
              child: Semantics(
                selected: selected,
                label: items[index].$2,
                button: true,
                child: InkWell(
                  key: ValueKey('bottomNav$index'),
                  borderRadius: BorderRadius.circular(32),
                  onTap: () => onSelected(index),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 220),
                    margin: const EdgeInsets.all(7),
                    decoration: BoxDecoration(
                      color: selected
                          ? UploadPalette.selected
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(28),
                    ),
                    child: Center(
                      child: SvgPicture.asset(
                        items[index].$1,
                        width: index == 1 ? 32 : 27,
                        height: index == 1 ? 32 : 27,
                        colorFilter: ColorFilter.mode(
                          selected
                              ? UploadPalette.coral
                              : UploadPalette.primaryText,
                          BlendMode.srcIn,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// Tells what covers the app's home page: a page pushed over it (the practice
/// screen, for one) and, separately, a dialog or sheet.
class PageRouteTracker extends NavigatorObserver {
  final _pages = ValueNotifier<int>(0);
  final _popups = ValueNotifier<int>(0);

  /// True while no page covers the home page. Dialogs and sheets do not count.
  late final ValueListenable<bool> atHome = _Derived(
    _pages,
    () => _pages.value <= 1,
  );

  /// True while nothing at all covers the home page: no page, dialog or sheet.
  late final ValueListenable<bool> uncovered = _Derived(
    Listenable.merge([_pages, _popups]),
    () => _pages.value <= 1 && _popups.value == 0,
  );

  ValueNotifier<int>? _counter(Route<dynamic> route) => switch (route) {
    PageRoute() => _pages,
    PopupRoute() => _popups,
    _ => null,
  };

  void _move(Route<dynamic> route, int by) {
    final counter = _counter(route);
    if (counter == null) return;
    // Navigator callbacks can arrive during a build; listeners update after.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      counter.value = (counter.value + by).clamp(0, 1 << 20);
    });
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _move(route, 1);

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _move(route, -1);

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      _move(route, -1);
}

class _Derived extends ValueListenable<bool> {
  _Derived(this._source, this._read);

  final Listenable _source;
  final bool Function() _read;

  @override
  bool get value => _read();

  @override
  void addListener(VoidCallback listener) => _source.addListener(listener);

  @override
  void removeListener(VoidCallback listener) =>
      _source.removeListener(listener);
}

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// Tells whether the app is showing its home page or a page pushed over it
/// (the practice screen, for one). Dialogs and sheets do not count.
class PageRouteTracker extends NavigatorObserver {
  final _depth = ValueNotifier<int>(0);

  /// True while no page covers the home page.
  late final ValueListenable<bool> atHome = _AtHome(_depth);

  static bool _isPage(Route<dynamic> route) => route is PageRoute;

  void _move(int by) {
    // Navigator callbacks can arrive during a build; listeners update after.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _depth.value = (_depth.value + by).clamp(0, 1 << 20);
    });
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_isPage(route)) _move(1);
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_isPage(route)) _move(-1);
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_isPage(route)) _move(-1);
  }
}

class _AtHome extends ValueListenable<bool> {
  _AtHome(this._depth);

  final ValueListenable<int> _depth;

  @override
  bool get value => _depth.value <= 1;

  @override
  void addListener(VoidCallback listener) => _depth.addListener(listener);

  @override
  void removeListener(VoidCallback listener) => _depth.removeListener(listener);
}

import 'package:wakelock_plus/wakelock_plus.dart';

/// Keeps the phone screen from dimming and locking while a song plays.
abstract interface class ScreenAwake {
  Future<void> setAwake(bool awake);
}

class WakelockScreenAwake implements ScreenAwake {
  const WakelockScreenAwake();

  @override
  Future<void> setAwake(bool awake) async {
    try {
      await WakelockPlus.toggle(enable: awake);
    } on Object {
      // Staying awake is a comfort, never a reason to interrupt practice.
    }
  }
}

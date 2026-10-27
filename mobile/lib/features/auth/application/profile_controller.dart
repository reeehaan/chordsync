import 'package:flutter/foundation.dart';

import '../data/profile_api.dart';
import '../data/profile_store.dart';
import '../data/user_profile.dart';
import 'auth_controller.dart';

enum ProfileStatus { idle, loading, ready, failed }

/// Keeps the signed-in person's profile: sends what they entered at sign-up to
/// their account, and loads it on any phone they log in on.
///
/// It follows the [AuthController]: it syncs when someone is signed in and wipes
/// the phone's copy when they log out.
class ProfileController extends ChangeNotifier {
  ProfileController({
    required this._api,
    required this._store,
    required this._auth,
  }) {
    _auth.addListener(_onAuthChanged);
    _onAuthChanged();
  }

  final ProfileApi _api;
  final ProfileStore _store;
  final AuthController _auth;

  UserProfile? _profile;
  ProfileStatus _status = ProfileStatus.idle;
  bool _syncing = false;

  /// The saved profile, or null when there is none (or it has not loaded).
  UserProfile? get profile => _profile;
  ProfileStatus get status => _status;

  void _onAuthChanged() {
    if (_auth.isSignedIn) {
      if (_status == ProfileStatus.idle) sync();
    } else if (_auth.status == AuthStatus.signedOut) {
      _reset();
    }
  }

  Future<void> _reset() async {
    _profile = null;
    _status = ProfileStatus.idle;
    notifyListeners();
    await _store.clear();
  }

  /// Loads the profile from the account. If the account has none yet and this
  /// phone holds the sign-up answers of the same email, they are sent now.
  Future<void> sync() async {
    final email = _auth.email;
    if (email == null || _syncing) return;
    _syncing = true;
    _status = ProfileStatus.loading;
    notifyListeners();
    try {
      var local = await _store.read();
      if (local != null && local.email != email) {
        await _store.clear(); // someone else's unfinished sign-up
        local = null;
      }
      try {
        var profile = await _api.fetch();
        if (profile == null && local != null) {
          profile = await _api.save(local.profile);
        }
        if (profile != null) await _store.write(profile, email: email);
        _profile = profile;
        _status = ProfileStatus.ready;
      } on ProfileApiException {
        // Offline or the server is busy: show what the phone has, try again later.
        _profile = local?.profile;
        _status = ProfileStatus.failed;
      }
    } finally {
      _syncing = false;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _auth.removeListener(_onAuthChanged);
    super.dispose();
  }
}

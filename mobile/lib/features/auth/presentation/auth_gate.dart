import 'package:flutter/material.dart';

import '../application/auth_controller.dart';
import '../data/profile_store.dart';
import 'create_account_flow.dart';
import 'log_in_screen.dart';
import 'welcome_screen.dart';

/// Shows the app to people who are signed in, and the welcome, log in and
/// create-account screens to everyone else.
class AuthGate extends StatelessWidget {
  const AuthGate({
    super.key,
    required this.auth,
    required this.profiles,
    required this.signedIn,
    this.today,
  });

  final AuthController auth;
  final ProfileStore profiles;

  /// What a signed-in person sees.
  final Widget signedIn;

  /// Today's date for the age check. Tests set it.
  final DateTime Function()? today;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: auth,
      builder: (context, _) => switch (auth.status) {
        // While the phone's storage is read: the same dark as the first screen,
        // so nothing flashes.
        AuthStatus.loading => const ColoredBox(color: Color(0xFF2B1A12)),
        AuthStatus.signedOut => _SignedOutNavigator(
          auth: auth,
          profiles: profiles,
          today: today,
        ),
        AuthStatus.signedIn => signedIn,
      },
    );
  }
}

class _SignedOutNavigator extends StatelessWidget {
  const _SignedOutNavigator({
    required this.auth,
    required this.profiles,
    required this.today,
  });

  final AuthController auth;
  final ProfileStore profiles;
  final DateTime Function()? today;

  @override
  Widget build(BuildContext context) {
    return Navigator(
      onGenerateRoute: (settings) => _fade(
        (context) => WelcomeScreen(
          onLogIn: () => Navigator.of(context).push(_fade(_logIn)),
          onCreateAccount: () => Navigator.of(context).push(_fade(_create)),
        ),
      ),
    );
  }

  Widget _logIn(BuildContext context) => LogInScreen(
    auth: auth,
    onCreateAccount: () {
      auth.cancel();
      Navigator.of(context).pushReplacement(_fade(_create));
    },
  );

  Widget _create(BuildContext context) => CreateAccountFlow(
    auth: auth,
    profiles: profiles,
    today: today,
    onLogIn: () {
      auth.cancel();
      Navigator.of(context).pushReplacement(_fade(_logIn));
    },
  );

  static Route<void> _fade(WidgetBuilder builder) => PageRouteBuilder<void>(
    pageBuilder: (context, _, _) => builder(context),
    transitionDuration: const Duration(milliseconds: 280),
    reverseTransitionDuration: const Duration(milliseconds: 220),
    transitionsBuilder: (context, animation, _, child) => FadeTransition(
      opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
      child: child,
    ),
  );
}

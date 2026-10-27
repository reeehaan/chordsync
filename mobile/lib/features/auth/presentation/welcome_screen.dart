import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import 'auth_style.dart';

const welcomeImage = 'assets/auth/welcome.jpg';

/// The first screen a signed-out person sees: log in, or create an account.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({
    super.key,
    required this.onLogIn,
    required this.onCreateAccount,
  });

  final VoidCallback onLogIn;
  final VoidCallback onCreateAccount;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF2B1A12),
      body: AuthBackdrop(
        image: welcomeImage,
        shade: 0.5,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              ChordSyncSpace.lg,
              ChordSyncSpace.xl,
              ChordSyncSpace.lg,
              ChordSyncSpace.lg,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(
                  header: true,
                  child: const Text('ChordSync', style: AuthText.wordmark),
                ),
                const SizedBox(height: ChordSyncSpace.sm),
                const Text(
                  'Your songs. Your practice.',
                  style: AuthText.tagline,
                ),
                const Spacer(),
                AuthPrimaryButton(label: 'Log in', onPressed: onLogIn),
                const SizedBox(height: ChordSyncSpace.md),
                AuthSecondaryButton(
                  label: 'Create account',
                  onPressed: onCreateAccount,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

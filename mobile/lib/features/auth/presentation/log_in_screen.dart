import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../application/auth_controller.dart';
import 'auth_style.dart';
import 'code_entry.dart';
import 'welcome_screen.dart';

/// Log in with an email and a code. No password.
class LogInScreen extends StatefulWidget {
  const LogInScreen({
    super.key,
    required this.auth,
    required this.onCreateAccount,
    this.initialEmail = '',
  });

  final AuthController auth;
  final VoidCallback onCreateAccount;
  final String initialEmail;

  @override
  State<LogInScreen> createState() => _LogInScreenState();
}

class _LogInScreenState extends State<LogInScreen> {
  late final _email = TextEditingController(text: widget.initialEmail);

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    FocusScope.of(context).unfocus();
    await widget.auth.beginLogIn(_email.text);
  }

  void _back() {
    if (widget.auth.waitingForCode) {
      widget.auth.cancel();
    } else {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = widget.auth;
    return ListenableBuilder(
      listenable: auth,
      builder: (context, _) {
        final waiting = auth.waitingForCode;
        return PopScope(
          canPop: !waiting,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) auth.cancel();
          },
          child: Scaffold(
            backgroundColor: const Color(0xFF2B1A12),
            body: AuthBackdrop(
              image: welcomeImage,
              child: SafeArea(
                child: CustomScrollView(
                  slivers: [
                    SliverFillRemaining(
                      hasScrollBody: false,
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(
                          ChordSyncSpace.lg,
                          ChordSyncSpace.sm,
                          ChordSyncSpace.lg,
                          ChordSyncSpace.lg,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            AuthBackButton(onPressed: _back),
                            const SizedBox(height: ChordSyncSpace.lg),
                            Semantics(
                              header: true,
                              child: Text(
                                waiting ? 'Check your email' : 'Welcome back',
                                style: AuthText.title,
                              ),
                            ),
                            if (!waiting) ...[
                              const SizedBox(height: ChordSyncSpace.sm),
                              const Text(
                                "Enter your email and we'll send you a code. No password needed.",
                                style: AuthText.lead,
                              ),
                            ],
                            const Spacer(),
                            GlassPanel(
                              child: waiting
                                  ? CodeEntry(
                                      auth: auth,
                                      onChangeEmail: auth.cancel,
                                      hint: Padding(
                                        padding: const EdgeInsets.only(
                                          top: ChordSyncSpace.xs,
                                        ),
                                        child: Text(
                                          'No code? That email may not have an account yet.',
                                          style: AuthText.lead.copyWith(
                                            fontSize: 14,
                                            shadows: const [],
                                          ),
                                        ),
                                      ),
                                    )
                                  : _EmailStep(
                                      auth: auth,
                                      controller: _email,
                                      onSend: _send,
                                      onCreateAccount: widget.onCreateAccount,
                                    ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _EmailStep extends StatelessWidget {
  const _EmailStep({
    required this.auth,
    required this.controller,
    required this.onSend,
    required this.onCreateAccount,
  });

  final AuthController auth;
  final TextEditingController controller;
  final VoidCallback onSend;
  final VoidCallback onCreateAccount;

  @override
  Widget build(BuildContext context) {
    final failure = auth.failure;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AuthField(
          label: 'Email',
          controller: controller,
          hint: 'you@example.com',
          keyboardType: TextInputType.emailAddress,
          textInputAction: TextInputAction.send,
          autofillHints: const [AutofillHints.email],
          autocorrect: false,
          onSubmitted: (_) => onSend(),
        ),
        AuthErrorText(failure == null ? null : authFailureMessage(failure)),
        const SizedBox(height: ChordSyncSpace.md),
        AuthPrimaryButton(
          label: 'Send me a code',
          busy: auth.busy,
          onPressed: onSend,
        ),
        const SizedBox(height: ChordSyncSpace.xs),
        Center(
          child: AuthTextButton(
            label: 'New here? Create an account',
            onPressed: auth.busy ? null : onCreateAccount,
          ),
        ),
      ],
    );
  }
}

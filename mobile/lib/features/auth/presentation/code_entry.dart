import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../application/auth_controller.dart';
import 'auth_style.dart';

/// The step where the person types the six-digit code from their email. Shared
/// by log in and create account.
class CodeEntry extends StatefulWidget {
  const CodeEntry({
    super.key,
    required this.auth,
    required this.onChangeEmail,
    this.hint,
    this.cooldown = const Duration(seconds: 30),
  });

  final AuthController auth;
  final VoidCallback onChangeEmail;

  /// A line under the instructions, for example how to create an account.
  final Widget? hint;

  /// How long the person waits before asking for another code.
  final Duration cooldown;

  @override
  State<CodeEntry> createState() => _CodeEntryState();
}

class _CodeEntryState extends State<CodeEntry> {
  final _code = TextEditingController();
  Timer? _timer;
  int _secondsLeft = 0;

  @override
  void initState() {
    super.initState();
    _startCooldown();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _code.dispose();
    super.dispose();
  }

  void _startCooldown() {
    _timer?.cancel();
    _secondsLeft = widget.cooldown.inSeconds;
    if (_secondsLeft == 0) return;
    _timer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;
      setState(() => _secondsLeft -= 1);
      if (_secondsLeft <= 0) timer.cancel();
    });
  }

  Future<void> _verify() async {
    final signedIn = await widget.auth.submitCode(_code.text);
    if (!mounted) return;
    if (!signedIn && widget.auth.waitingForCode) {
      // A second code was sent (or the code was wrong): start fresh.
      if (widget.auth.failure == null) _code.clear();
      _startCooldown();
    }
  }

  Future<void> _resend() async {
    final sent = await widget.auth.resendCode();
    if (!mounted || !sent) return;
    _code.clear();
    _startCooldown();
  }

  @override
  Widget build(BuildContext context) {
    final auth = widget.auth;
    final failure = auth.failure;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text.rich(
          TextSpan(
            style: AuthText.lead,
            children: [
              const TextSpan(text: 'We sent a code to '),
              TextSpan(
                text: auth.pendingEmail ?? '',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              const TextSpan(text: '. It can take a minute to arrive.'),
            ],
          ),
        ),
        const SizedBox(height: ChordSyncSpace.md),
        AuthField(
          label: 'Your code',
          controller: _code,
          hint: '••••••••',
          autofocus: true,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.done,
          autofillHints: const [AutofillHints.oneTimeCode],
          maxLength: codeLength,
          inputFormatters: codeInputFormatters,
          textAlign: TextAlign.center,
          letterSpacing: 8,
          autocorrect: false,
          onChanged: (value) {
            // Sign in as soon as the last digit arrives (or is autofilled).
            if (value.length == codeLength && !auth.busy) unawaited(_verify());
          },
          onSubmitted: (_) => _verify(),
        ),
        AuthErrorText(failure == null ? null : authFailureMessage(failure)),
        const SizedBox(height: ChordSyncSpace.md),
        AuthPrimaryButton(label: 'Verify', busy: auth.busy, onPressed: _verify),
        const SizedBox(height: ChordSyncSpace.sm),
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            AuthTextButton(
              label: _secondsLeft > 0
                  ? 'Send a new code in ${_secondsLeft}s'
                  : 'Send a new code',
              onPressed: _secondsLeft > 0 || auth.busy ? null : _resend,
            ),
            AuthTextButton(
              label: 'Use a different email',
              onPressed: auth.busy ? null : widget.onChangeEmail,
            ),
          ],
        ),
        if (widget.hint != null) widget.hint!,
      ],
    );
  }
}

/// The length of the code Cognito emails.
const codeLength = 8;

/// Digits only, no more than the code length: for any field that takes the code.
final codeInputFormatters = <TextInputFormatter>[
  FilteringTextInputFormatter.digitsOnly,
  LengthLimitingTextInputFormatter(codeLength),
];

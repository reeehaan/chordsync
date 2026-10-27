import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/pressable_scale.dart';
import '../data/cognito_api.dart';

/// The sign-in screens sit on warm illustrations, with dark glass panels for
/// the controls. These colours belong to those screens only.
abstract final class AuthColors {
  static const cream = Color(0xFFFBEBD3);
  static const creamMuted = Color(0xCCFBEBD3);
  static const peach = Color(0xFFFFD9A8);
  static const onPeach = Color(0xFF2B1A12);
  static const panel = Color(0xCC1F140E);
  static const field = Color(0xFF2B1D15);
  static const edge = Color(0x40FFC888);
  static const amber = Color(0xFFD88732);
  static const error = Color(0xFFFFB4A2);
}

abstract final class AuthText {
  static const _body = ChordSyncTypography.bodyFamily;
  static const _display = ChordSyncTypography.displayFamily;

  static const wordmark = TextStyle(
    fontFamily: _display,
    fontSize: 54,
    height: 1.0,
    fontWeight: FontWeight.w600,
    color: Colors.white,
    shadows: [Shadow(blurRadius: 18, color: Color(0x99000000))],
  );
  static const tagline = TextStyle(
    fontFamily: _display,
    fontSize: 20,
    fontStyle: FontStyle.italic,
    color: AuthColors.cream,
    shadows: [Shadow(blurRadius: 12, color: Color(0xB3000000))],
  );
  static const title = TextStyle(
    fontFamily: _display,
    fontSize: 32,
    height: 1.12,
    fontWeight: FontWeight.w600,
    color: Colors.white,
    shadows: [Shadow(blurRadius: 14, color: Color(0xB3000000))],
  );
  static const lead = TextStyle(
    fontFamily: _body,
    fontSize: 16,
    height: 1.35,
    color: AuthColors.cream,
    shadows: [Shadow(blurRadius: 10, color: Color(0xB3000000))],
  );
  static const label = TextStyle(
    fontFamily: _body,
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: AuthColors.cream,
  );
  static const input = TextStyle(
    fontFamily: _body,
    fontSize: 17,
    color: AuthColors.cream,
  );
  static const hint = TextStyle(
    fontFamily: _body,
    fontSize: 17,
    color: Color(0x99FBEBD3),
  );
  static const button = TextStyle(
    fontFamily: _body,
    fontSize: 17,
    fontWeight: FontWeight.w700,
    color: AuthColors.onPeach,
  );
  static const error = TextStyle(
    fontFamily: _body,
    fontSize: 14,
    height: 1.3,
    color: AuthColors.error,
  );
}

/// Plain words for each thing that can go wrong while signing in.
String authFailureMessage(AuthFailure failure) => switch (failure) {
  AuthFailure.wrongCode =>
    "That code isn't right. Check the email and try again.",
  AuthFailure.expiredCode =>
    'That code has expired. Send a new code and try again.',
  AuthFailure.accountExists =>
    'That email already has an account. Log in instead.',
  AuthFailure.noAccount => "We couldn't find an account for that email.",
  AuthFailure.tooManyAttempts =>
    'Too many tries. Wait a few minutes and try again.',
  AuthFailure.invalidEmail => 'Enter a valid email address.',
  AuthFailure.sessionEnded => 'Your session ended. Please log in again.',
  AuthFailure.network =>
    "Can't reach ChordSync. Check your connection and try again.",
  AuthFailure.unknown => 'Something went wrong. Please try again.',
};

/// A full-screen illustration with a shade so the text on it stays readable.
class AuthBackdrop extends StatelessWidget {
  const AuthBackdrop({
    super.key,
    required this.image,
    required this.child,
    this.alignment = Alignment.topCenter,
    this.shade = 0.62,
  });

  final String image;
  final Widget child;
  final Alignment alignment;

  /// How dark the bottom of the picture gets, 0 to 1.
  final double shade;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        const ColoredBox(color: Color(0xFF2B1A12)),
        // The picture is decoration; screen readers skip it.
        ExcludeSemantics(
          child: Image.asset(image, fit: BoxFit.cover, alignment: alignment),
        ),
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                const Color(0x33000000),
                const Color(0x00000000),
                Color.fromRGBO(18, 10, 6, shade),
                Color.fromRGBO(18, 10, 6, (shade + 0.28).clamp(0, 1)),
              ],
              stops: const [0, 0.32, 0.62, 1],
            ),
          ),
        ),
        child,
      ],
    );
  }
}

/// A dark, slightly see-through panel for the controls.
class GlassPanel extends StatelessWidget {
  const GlassPanel({super.key, required this.child, this.padding});

  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AuthColors.panel,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: AuthColors.edge),
      ),
      child: Padding(
        padding: padding ?? const EdgeInsets.all(ChordSyncSpace.md),
        child: child,
      ),
    );
  }
}

/// The main call to action: a wide peach button with an arrow.
class AuthPrimaryButton extends StatelessWidget {
  const AuthPrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.busy = false,
    this.showArrow = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool busy;
  final bool showArrow;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !busy;
    return Semantics(
      button: true,
      enabled: enabled,
      label: busy ? '$label, please wait' : label,
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: enabled
                ? () {
                    Haptics.light();
                    onPressed!();
                  }
                : null,
            child: AnimatedOpacity(
              duration: const Duration(milliseconds: 140),
              opacity: onPressed == null ? 0.5 : 1,
              child: Container(
                constraints: const BoxConstraints(minHeight: 56),
                decoration: BoxDecoration(
                  color: AuthColors.peach,
                  borderRadius: BorderRadius.circular(30),
                ),
                alignment: Alignment.center,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: busy
                    ? const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(
                          strokeWidth: 2.5,
                          color: AuthColors.onPeach,
                        ),
                      )
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(
                              label,
                              style: AuthText.button,
                              textAlign: TextAlign.center,
                            ),
                          ),
                          if (showArrow) ...[
                            const SizedBox(width: 10),
                            const Icon(
                              Icons.arrow_forward,
                              size: 20,
                              color: AuthColors.onPeach,
                            ),
                          ],
                        ],
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The quieter button: an outline on the picture.
class AuthSecondaryButton extends StatelessWidget {
  const AuthSecondaryButton({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      enabled: onPressed != null,
      label: label,
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onPressed == null
                ? null
                : () {
                    Haptics.selection();
                    onPressed!();
                  },
            child: Container(
              constraints: const BoxConstraints(minHeight: 56),
              decoration: BoxDecoration(
                color: const Color(0x66000000),
                borderRadius: BorderRadius.circular(30),
                border: Border.all(color: const Color(0xB3FFC888), width: 1.4),
              ),
              alignment: Alignment.center,
              child: Text(
                label,
                style: AuthText.button.copyWith(color: AuthColors.cream),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// A text link on the dark panels, at least 48 high to tap.
class AuthTextButton extends StatelessWidget {
  const AuthTextButton({
    super.key,
    required this.label,
    required this.onPressed,
  });

  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: onPressed,
      style: TextButton.styleFrom(
        minimumSize: const Size(48, 48),
        foregroundColor: AuthColors.peach,
        disabledForegroundColor: AuthColors.creamMuted,
        textStyle: AuthText.label.copyWith(
          decoration: TextDecoration.underline,
          decorationColor: AuthColors.peach,
        ),
      ),
      child: Text(label),
    );
  }
}

/// A labelled dark text field.
class AuthField extends StatelessWidget {
  const AuthField({
    super.key,
    required this.label,
    required this.controller,
    this.hint,
    this.keyboardType,
    this.textInputAction,
    this.autofillHints,
    this.onSubmitted,
    this.onChanged,
    this.maxLength,
    this.textAlign = TextAlign.start,
    this.letterSpacing,
    this.autofocus = false,
    this.readOnly = false,
    this.onTap,
    this.suffix,
    this.textCapitalization = TextCapitalization.none,
    this.autocorrect = true,
    this.inputFormatters,
  });

  final String label;
  final TextEditingController controller;
  final String? hint;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;
  final Iterable<String>? autofillHints;
  final ValueChanged<String>? onSubmitted;
  final ValueChanged<String>? onChanged;
  final int? maxLength;
  final TextAlign textAlign;
  final double? letterSpacing;
  final bool autofocus;
  final bool readOnly;
  final VoidCallback? onTap;
  final Widget? suffix;
  final TextCapitalization textCapitalization;
  final bool autocorrect;
  final List<TextInputFormatter>? inputFormatters;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 8),
          child: Text(label, style: AuthText.label),
        ),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          textInputAction: textInputAction,
          autofillHints: autofillHints,
          onSubmitted: onSubmitted,
          onChanged: onChanged,
          maxLength: maxLength,
          inputFormatters: inputFormatters,
          autofocus: autofocus,
          readOnly: readOnly,
          onTap: onTap,
          textAlign: textAlign,
          textCapitalization: textCapitalization,
          autocorrect: autocorrect,
          enableSuggestions: autocorrect,
          cursorColor: AuthColors.peach,
          style: AuthText.input.copyWith(letterSpacing: letterSpacing),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: AuthText.hint,
            counterText: '',
            suffixIcon: suffix,
            filled: true,
            fillColor: AuthColors.field,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 16,
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: AuthColors.edge),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: AuthColors.edge),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: AuthColors.peach, width: 1.6),
            ),
          ),
        ),
      ],
    );
  }
}

/// The error line under a field. Announced to screen readers when it appears.
class AuthErrorText extends StatelessWidget {
  const AuthErrorText(this.message, {super.key});

  final String? message;

  @override
  Widget build(BuildContext context) {
    if (message == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10, left: 4),
      child: Semantics(
        liveRegion: true,
        child: Text(message!, style: AuthText.error),
      ),
    );
  }
}

/// The back arrow on the pictures, large enough to tap.
class AuthBackButton extends StatelessWidget {
  const AuthBackButton({super.key, required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: IconButton(
        onPressed: onPressed,
        tooltip: 'Back',
        iconSize: 26,
        constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
        style: IconButton.styleFrom(
          backgroundColor: const Color(0x66000000),
          foregroundColor: AuthColors.cream,
        ),
        icon: const Icon(Icons.arrow_back),
      ),
    );
  }
}

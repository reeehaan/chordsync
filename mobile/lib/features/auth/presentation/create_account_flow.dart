import 'package:flutter/cupertino.dart'
    show
        CupertinoDatePicker,
        CupertinoDatePickerMode,
        CupertinoTextThemeData,
        CupertinoTheme,
        CupertinoThemeData,
        DatePickerDateOrder;
import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/motion.dart';
import '../../../design_system/pressable_scale.dart';
import '../application/auth_controller.dart';
import '../data/profile_store.dart';
import '../data/user_profile.dart';
import 'auth_style.dart';
import 'code_entry.dart';

const _aboutYouImage = 'assets/auth/about_you.jpg';
const _musicTasteImage = 'assets/auth/music_taste.jpg';
const _experienceImage = 'assets/auth/experience.jpg';
const _welcomeImage = 'assets/auth/welcome.jpg';
const _stepCount = 4;

/// Create an account in four short steps: who you are, what you like to hear,
/// how much you play, and then your email with the code that proves it.
class CreateAccountFlow extends StatefulWidget {
  const CreateAccountFlow({
    super.key,
    required this.auth,
    required this.profiles,
    required this.onLogIn,
    this.today,
  });

  final AuthController auth;
  final ProfileStore profiles;
  final VoidCallback onLogIn;

  /// Today's date, for the age check. Tests set it.
  final DateTime Function()? today;

  @override
  State<CreateAccountFlow> createState() => _CreateAccountFlowState();
}

class _CreateAccountFlowState extends State<CreateAccountFlow> {
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _birthText = TextEditingController();
  int _step = 0;
  DateTime? _birthDate;
  final _genres = <String>{};
  GuitarExperience? _experience;
  String? _problem;

  DateTime get _today => (widget.today ?? DateTime.now)();

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _birthText.dispose();
    super.dispose();
  }

  void _go(int step) {
    FocusScope.of(context).unfocus();
    setState(() {
      _step = step;
      _problem = null;
    });
  }

  void _back() {
    if (widget.auth.waitingForCode) {
      widget.auth.cancel();
    } else if (_step == 0) {
      Navigator.of(context).maybePop();
    } else {
      _go(_step - 1);
    }
  }

  void _nextFromAbout() {
    final name = _name.text.trim();
    if (name.isEmpty) {
      setState(() => _problem = 'Tell us your name.');
    } else if (_birthDate == null) {
      setState(() => _problem = 'Choose your date of birth.');
    } else if (UserProfile.ageOn(_birthDate!, _today) <
        UserProfile.minimumAge) {
      setState(
        () => _problem =
            'You need to be ${UserProfile.minimumAge} or older to use ChordSync.',
      );
    } else {
      _go(1);
    }
  }

  Future<void> _pickBirthDate() async {
    FocusScope.of(context).unfocus();
    final latest = UserProfile.youngestBirthDate(_today);
    final picked = await showModalBottomSheet<DateTime>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => _BirthdaySheet(
        initial: _birthDate ?? DateTime(latest.year - 5, 6, 15),
        latest: latest,
      ),
    );
    if (picked != null && mounted) {
      setState(() {
        _birthDate = picked;
        _birthText.text = _formatDate(picked);
        _problem = null;
      });
    }
  }

  Future<void> _sendCode() async {
    FocusScope.of(context).unfocus();
    final email = AuthController.normalizeEmail(_email.text);
    if (email != null) {
      final profile = UserProfile(
        name: _name.text.trim(),
        birthYear: _birthDate!.year,
        genres: _genres.toList(),
        experience: _experience ?? GuitarExperience.beginner,
      );
      // Kept on this phone first, under this email, so signing in can never
      // lose what was typed. It is sent to the account once signed in.
      await widget.profiles.write(profile, email: email);
    }
    await widget.auth.beginSignUp(_email.text);
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.auth,
      builder: (context, _) {
        final waiting = widget.auth.waitingForCode;
        return PopScope(
          canPop: _step == 0 && !waiting,
          onPopInvokedWithResult: (didPop, _) {
            if (!didPop) _back();
          },
          child: Scaffold(
            backgroundColor: const Color(0xFF2B1A12),
            body: AnimatedSwitcher(
              duration: ChordSyncMotion.of(context, ChordSyncMotion.standard),
              child: KeyedSubtree(
                key: ValueKey('$_step-$waiting'),
                child: _buildStep(waiting),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildStep(bool waiting) {
    switch (_step) {
      case 0:
        return _StepPage(
          image: _aboutYouImage,
          step: 1,
          onBack: _back,
          title: "Let's get to know you",
          lead: 'Start with your name and birthday.',
          action: AuthPrimaryButton(label: 'Next', onPressed: _nextFromAbout),
          problem: _problem,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AuthField(
                label: 'Full name',
                controller: _name,
                hint: 'Enter your name',
                textInputAction: TextInputAction.next,
                textCapitalization: TextCapitalization.words,
                autofillHints: const [AutofillHints.name],
                onChanged: (_) {
                  if (_problem != null) setState(() => _problem = null);
                },
              ),
              const SizedBox(height: ChordSyncSpace.md),
              AuthField(
                label: 'Date of birth',
                controller: _birthText,
                hint: 'DD / MM / YYYY',
                readOnly: true,
                onTap: _pickBirthDate,
                suffix: const Icon(
                  Icons.calendar_today_outlined,
                  color: AuthColors.cream,
                  size: 20,
                ),
              ),
            ],
          ),
        );
      case 1:
        return _StepPage(
          image: _musicTasteImage,
          step: 2,
          onBack: _back,
          title: 'What kind of music do you enjoy?',
          lead: 'Choose your favourite genres. You can pick more than one.',
          action: AuthPrimaryButton(
            label: 'Next',
            onPressed: _genres.isEmpty
                ? null
                : () {
                    _go(2);
                  },
          ),
          secondary: AuthTextButton(
            label: 'Skip for now',
            onPressed: () => _go(2),
          ),
          child: _GenreBox(
            selected: _genres,
            onToggle: (genre) => setState(() {
              Haptics.selection();
              if (!_genres.remove(genre)) _genres.add(genre);
            }),
          ),
        );
      case 2:
        return _StepPage(
          image: _experienceImage,
          step: 3,
          onBack: _back,
          title: 'Your guitar experience',
          lead: 'This helps us suggest songs at the right level.',
          action: AuthPrimaryButton(
            label: 'Next',
            onPressed: _experience == null ? null : () => _go(3),
          ),
          child: Column(
            children: [
              for (final level in GuitarExperience.values)
                _ExperienceOption(
                  level: level,
                  selected: _experience == level,
                  onTap: () => setState(() {
                    Haptics.selection();
                    _experience = level;
                  }),
                ),
            ],
          ),
        );
      default:
        return _StepPage(
          image: _welcomeImage,
          step: 4,
          onBack: _back,
          title: waiting ? 'Check your email' : 'Last step: your email',
          lead: waiting
              ? null
              : "We'll send you a code to confirm it's you. No password needed.",
          action: waiting
              ? null
              : AuthPrimaryButton(
                  label: 'Send me a code',
                  busy: widget.auth.busy,
                  onPressed: _sendCode,
                ),
          secondary: waiting
              ? null
              : AuthTextButton(
                  label: 'Already have an account? Log in',
                  onPressed: widget.auth.busy ? null : widget.onLogIn,
                ),
          child: waiting
              ? CodeEntry(auth: widget.auth, onChangeEmail: widget.auth.cancel)
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    AuthField(
                      label: 'Email',
                      controller: _email,
                      hint: 'you@example.com',
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.send,
                      autofillHints: const [AutofillHints.email],
                      autocorrect: false,
                      onSubmitted: (_) => _sendCode(),
                    ),
                    AuthErrorText(
                      widget.auth.failure == null
                          ? null
                          : authFailureMessage(widget.auth.failure!),
                    ),
                  ],
                ),
        );
    }
  }

  static String _formatDate(DateTime date) =>
      '${date.day.toString().padLeft(2, '0')} / '
      '${date.month.toString().padLeft(2, '0')} / '
      '${date.year.toString().padLeft(4, '0')}';
}

/// One screen of the flow: a picture, the step count, a title, the controls on
/// a glass panel, and the button.
class _StepPage extends StatelessWidget {
  const _StepPage({
    required this.image,
    required this.step,
    required this.onBack,
    required this.title,
    required this.child,
    this.lead,
    this.action,
    this.secondary,
    this.problem,
  });

  final String image;
  final int step;
  final VoidCallback onBack;
  final String title;
  final String? lead;
  final Widget child;
  final Widget? action;
  final Widget? secondary;
  final String? problem;

  @override
  Widget build(BuildContext context) {
    return AuthBackdrop(
      image: image,
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
                    AuthBackButton(onPressed: onBack),
                    const SizedBox(height: ChordSyncSpace.sm),
                    _Progress(step: step),
                    const SizedBox(height: ChordSyncSpace.lg),
                    Semantics(
                      header: true,
                      child: Text(title, style: AuthText.title),
                    ),
                    if (lead != null) ...[
                      const SizedBox(height: ChordSyncSpace.sm),
                      Text(lead!, style: AuthText.lead),
                    ],
                    const Spacer(),
                    GlassPanel(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          child,
                          AuthErrorText(problem),
                          if (action != null) ...[
                            const SizedBox(height: ChordSyncSpace.md),
                            action!,
                          ],
                          if (secondary != null) Center(child: secondary!),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "2 / 4" and a line that fills as the person moves on.
class _Progress extends StatelessWidget {
  const _Progress({required this.step});

  final int step;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Step $step of $_stepCount',
      child: ExcludeSemantics(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '$step / $_stepCount',
              style: AuthText.label.copyWith(
                shadows: const [
                  Shadow(blurRadius: 8, color: Color(0xB3000000)),
                ],
              ),
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: TweenAnimationBuilder<double>(
                tween: Tween(end: step / _stepCount),
                duration: ChordSyncMotion.of(
                  context,
                  ChordSyncMotion.emphasized,
                ),
                curve: Curves.easeOutCubic,
                builder: (context, value, _) => LinearProgressIndicator(
                  value: value,
                  minHeight: 4,
                  backgroundColor: const Color(0x4DFFFFFF),
                  color: AuthColors.peach,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _GenreChip extends StatelessWidget {
  const _GenreChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onTap,
            child: AnimatedContainer(
              duration: ChordSyncMotion.of(context, ChordSyncMotion.quick),
              constraints: const BoxConstraints(minHeight: 44, minWidth: 64),
              padding: const EdgeInsets.symmetric(horizontal: 16),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected ? AuthColors.peach : AuthColors.field,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(
                  color: selected ? AuthColors.peach : AuthColors.edge,
                ),
              ),
              child: Text(
                label,
                style: AuthText.label.copyWith(
                  fontSize: 15,
                  color: selected ? AuthColors.onPeach : AuthColors.cream,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ExperienceOption extends StatelessWidget {
  const _ExperienceOption({
    required this.level,
    required this.selected,
    required this.onTap,
  });

  final GuitarExperience level;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      inMutuallyExclusiveGroup: true,
      checked: selected,
      label: '${level.title}. ${level.subtitle}',
      child: ExcludeSemantics(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: AnimatedContainer(
              duration: ChordSyncMotion.of(context, ChordSyncMotion.quick),
              constraints: const BoxConstraints(minHeight: 60),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: selected ? const Color(0x33FFD9A8) : AuthColors.field,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: selected ? AuthColors.peach : AuthColors.edge,
                  width: selected ? 1.6 : 1,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    selected
                        ? Icons.radio_button_checked
                        : Icons.radio_button_unchecked,
                    color: selected ? AuthColors.peach : AuthColors.creamMuted,
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          level.title,
                          style: AuthText.label.copyWith(fontSize: 16),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          level.subtitle,
                          style: AuthText.label.copyWith(
                            fontSize: 13,
                            fontWeight: FontWeight.w400,
                            color: AuthColors.creamMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The genres in a small, fixed-height box. It scrolls inside, so a long list
/// never pushes the button off the screen.
class _GenreBox extends StatefulWidget {
  const _GenreBox({required this.selected, required this.onToggle});

  final Set<String> selected;
  final ValueChanged<String> onToggle;

  @override
  State<_GenreBox> createState() => _GenreBoxState();
}

class _GenreBoxState extends State<_GenreBox> {
  static const _height = 184.0;
  final _scroll = ScrollController();

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: _height,
      child: ShaderMask(
        // A soft fade at the bottom hints that there is more to scroll to.
        shaderCallback: (bounds) => const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Colors.white, Colors.white, Color(0x00FFFFFF)],
          stops: [0, 0.82, 1],
        ).createShader(bounds),
        blendMode: BlendMode.dstIn,
        child: Scrollbar(
          controller: _scroll,
          thumbVisibility: true,
          child: SingleChildScrollView(
            controller: _scroll,
            padding: const EdgeInsets.only(bottom: 24, right: 8),
            child: Wrap(
              spacing: ChordSyncSpace.sm,
              runSpacing: ChordSyncSpace.sm,
              children: [
                for (final genre in musicGenres)
                  _GenreChip(
                    label: genre,
                    selected: widget.selected.contains(genre),
                    onTap: () => widget.onToggle(genre),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// A spinning date wheel in a dark sheet: scroll the day, month and year.
class _BirthdaySheet extends StatefulWidget {
  const _BirthdaySheet({required this.initial, required this.latest});

  final DateTime initial;
  final DateTime latest;

  @override
  State<_BirthdaySheet> createState() => _BirthdaySheetState();
}

class _BirthdaySheetState extends State<_BirthdaySheet> {
  late DateTime _chosen = widget.initial.isAfter(widget.latest)
      ? widget.latest
      : widget.initial;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: Color(0xFF1F140E),
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            ChordSyncSpace.lg,
            ChordSyncSpace.md,
            ChordSyncSpace.lg,
            ChordSyncSpace.md,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Semantics(
                header: true,
                child: const Text('Date of birth', style: AuthText.label),
              ),
              SizedBox(
                height: 216,
                child: CupertinoTheme(
                  data: const CupertinoThemeData(
                    brightness: Brightness.dark,
                    textTheme: CupertinoTextThemeData(
                      dateTimePickerTextStyle: TextStyle(
                        fontFamily: 'DM Sans',
                        fontSize: 22,
                        color: AuthColors.cream,
                      ),
                    ),
                  ),
                  child: CupertinoDatePicker(
                    mode: CupertinoDatePickerMode.date,
                    dateOrder: DatePickerDateOrder.dmy,
                    initialDateTime: _chosen,
                    minimumDate: DateTime(1900),
                    maximumDate: widget.latest,
                    onDateTimeChanged: (date) => _chosen = date,
                  ),
                ),
              ),
              const SizedBox(height: ChordSyncSpace.sm),
              AuthPrimaryButton(
                label: 'Done',
                showArrow: false,
                onPressed: () => Navigator.of(context).pop(_chosen),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

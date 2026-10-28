import 'package:flutter/material.dart';

import '../../../design_system/appearance_controller.dart';
import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../application/auth_controller.dart';
import '../application/profile_controller.dart';
import '../data/profile_api.dart';
import '../data/user_profile.dart';

/// A round button in the Library header that opens the account sheet: who is
/// signed in, and how to log out.
class AccountButton extends StatelessWidget {
  const AccountButton({
    super.key,
    required this.auth,
    this.profile,
    this.appearance,
  });

  final AuthController auth;

  /// The person's profile, shown in the sheet when there is one.
  final ProfileController? profile;

  /// The light/dark choice, offered in the sheet when given.
  final AppearanceController? appearance;

  @override
  Widget build(BuildContext context) {
    return IconButton.filledTonal(
      tooltip: 'Account',
      constraints: const BoxConstraints(minWidth: 48, minHeight: 48),
      icon: const Icon(Icons.person_outline),
      onPressed: () {
        Haptics.selection();
        showModalBottomSheet<void>(
          context: context,
          showDragHandle: true,
          builder: (context) => _AccountSheet(
            auth: auth,
            profile: profile,
            appearance: appearance,
          ),
        );
      },
    );
  }
}

class _AccountSheet extends StatelessWidget {
  const _AccountSheet({required this.auth, this.profile, this.appearance});

  final AuthController auth;
  final ProfileController? profile;
  final AppearanceController? appearance;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final controller = profile;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          ChordSyncSpace.lg,
          0,
          ChordSyncSpace.lg,
          ChordSyncSpace.lg,
        ),
        child: ListenableBuilder(
          listenable: controller ?? auth,
          builder: (context, _) {
            final details = controller?.profile;
            return SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (details != null) ...[
                    Text(
                      details.name,
                      style: textTheme.headlineSmall,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 2),
                  ],
                  Text(
                    auth.email ?? '',
                    style: details == null
                        ? textTheme.titleLarge
                        : textTheme.bodyLarge,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (details != null) ...[
                    const SizedBox(height: ChordSyncSpace.md),
                    _Detail(
                      label: 'Guitar level',
                      value: details.experience.title,
                    ),
                    if (details.genres.isNotEmpty)
                      _Detail(
                        label: 'You enjoy',
                        value: details.genres.join(', '),
                      ),
                  ],
                  if (controller != null &&
                      controller.status == ProfileStatus.failed) ...[
                    const SizedBox(height: ChordSyncSpace.md),
                    Text(
                      "Couldn't load your profile just now.",
                      style: textTheme.bodyMedium,
                    ),
                    TextButton(
                      onPressed: controller.sync,
                      child: const Text('Try again'),
                    ),
                  ],
                  if (controller != null &&
                      controller.status != ProfileStatus.loading) ...[
                    const SizedBox(height: ChordSyncSpace.sm),
                    TextButton.icon(
                      icon: const Icon(Icons.edit_outlined),
                      label: Text(
                        details == null ? 'Add your details' : 'Edit profile',
                      ),
                      onPressed: () {
                        Navigator.of(context).pop();
                        showModalBottomSheet<void>(
                          context: context,
                          isScrollControlled: true,
                          showDragHandle: true,
                          builder: (_) =>
                              _EditProfileSheet(controller: controller),
                        );
                      },
                    ),
                  ],
                  if (appearance case final appearance?) ...[
                    const SizedBox(height: ChordSyncSpace.md),
                    Text('Appearance', style: textTheme.labelLarge),
                    const SizedBox(height: ChordSyncSpace.sm),
                    ListenableBuilder(
                      listenable: appearance,
                      builder: (context, _) => SizedBox(
                        width: double.infinity,
                        child: SegmentedButton<Appearance>(
                          showSelectedIcon: false,
                          segments: [
                            for (final choice in Appearance.values)
                              ButtonSegment(
                                value: choice,
                                label: Text(choice.label),
                              ),
                          ],
                          selected: {appearance.appearance},
                          onSelectionChanged: (picked) =>
                              appearance.select(picked.first),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: ChordSyncSpace.lg),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.logout),
                      label: const Text('Log out'),
                      onPressed: () {
                        Navigator.of(context).pop();
                        auth.signOut();
                      },
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _Detail extends StatelessWidget {
  const _Detail({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: ChordSyncSpace.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: textTheme.labelLarge),
          Text(value, style: textTheme.bodyLarge),
        ],
      ),
    );
  }
}

class _EditProfileSheet extends StatefulWidget {
  const _EditProfileSheet({required this.controller});

  final ProfileController controller;

  @override
  State<_EditProfileSheet> createState() => _EditProfileSheetState();
}

class _EditProfileSheetState extends State<_EditProfileSheet> {
  late final TextEditingController _name;
  late int? _birthYear;
  late GuitarExperience _experience;
  late final Set<String> _genres;
  String? _problem;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final current = widget.controller.profile;
    _name = TextEditingController(text: current?.name ?? '');
    _birthYear = current?.birthYear;
    _experience = current?.experience ?? GuitarExperience.beginner;
    _genres = {...?current?.genres};
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final latest = DateTime.now().year - UserProfile.minimumAge;
    if (name.isEmpty) {
      setState(() => _problem = 'Tell us your name.');
      return;
    }
    if (_birthYear == null || _birthYear! > latest) {
      setState(() => _problem = 'Choose the year you were born.');
      return;
    }
    setState(() {
      _saving = true;
      _problem = null;
    });
    try {
      await widget.controller.save(
        UserProfile(
          name: name,
          birthYear: _birthYear!,
          genres: [
            for (final genre in musicGenres)
              if (_genres.contains(genre)) genre,
          ],
          experience: _experience,
        ),
      );
      if (mounted) Navigator.of(context).pop();
    } on ProfileApiException {
      if (mounted) {
        setState(() {
          _saving = false;
          _problem =
              "Couldn't save just now. Check your connection and try again.";
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final newest = DateTime.now().year - UserProfile.minimumAge;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          ChordSyncSpace.lg,
          0,
          ChordSyncSpace.lg,
          ChordSyncSpace.lg + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Your details', style: textTheme.headlineSmall),
              const SizedBox(height: ChordSyncSpace.md),
              TextField(
                controller: _name,
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Full name'),
              ),
              const SizedBox(height: ChordSyncSpace.md),
              DropdownButtonFormField<int>(
                initialValue: _birthYear,
                decoration: const InputDecoration(
                  labelText: 'Year you were born',
                ),
                items: [
                  for (var year = newest; year >= 1900; year--)
                    DropdownMenuItem(value: year, child: Text('$year')),
                ],
                onChanged: (year) => setState(() => _birthYear = year),
              ),
              const SizedBox(height: ChordSyncSpace.md),
              Text('Guitar level', style: textTheme.labelLarge),
              const SizedBox(height: ChordSyncSpace.sm),
              Wrap(
                spacing: ChordSyncSpace.sm,
                children: [
                  for (final level in GuitarExperience.values)
                    ChoiceChip(
                      label: Text(level.title),
                      selected: _experience == level,
                      onSelected: (_) => setState(() => _experience = level),
                    ),
                ],
              ),
              const SizedBox(height: ChordSyncSpace.md),
              Text('You enjoy', style: textTheme.labelLarge),
              const SizedBox(height: ChordSyncSpace.sm),
              Wrap(
                spacing: ChordSyncSpace.sm,
                children: [
                  for (final genre in musicGenres)
                    FilterChip(
                      label: Text(genre),
                      selected: _genres.contains(genre),
                      onSelected: (on) => setState(
                        () => on ? _genres.add(genre) : _genres.remove(genre),
                      ),
                    ),
                ],
              ),
              if (_problem != null) ...[
                const SizedBox(height: ChordSyncSpace.md),
                Text(
                  _problem!,
                  style: textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
                ),
              ],
              const SizedBox(height: ChordSyncSpace.lg),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _saving ? null : _save,
                  child: Text(_saving ? 'Saving…' : 'Save'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

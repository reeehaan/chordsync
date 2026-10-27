import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../application/auth_controller.dart';
import '../application/profile_controller.dart';

/// A round button in the Library header that opens the account sheet: who is
/// signed in, and how to log out.
class AccountButton extends StatelessWidget {
  const AccountButton({super.key, required this.auth, this.profile});

  final AuthController auth;

  /// The person's profile, shown in the sheet when there is one.
  final ProfileController? profile;

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
          builder: (context) => _AccountSheet(auth: auth, profile: profile),
        );
      },
    );
  }
}

class _AccountSheet extends StatelessWidget {
  const _AccountSheet({required this.auth, this.profile});

  final AuthController auth;
  final ProfileController? profile;

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
            return Column(
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

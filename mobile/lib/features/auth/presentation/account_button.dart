import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../application/auth_controller.dart';

/// A round button in the Library header that opens the account sheet: who is
/// signed in, and how to log out.
class AccountButton extends StatelessWidget {
  const AccountButton({super.key, required this.auth});

  final AuthController auth;

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
          builder: (context) => _AccountSheet(auth: auth),
        );
      },
    );
  }
}

class _AccountSheet extends StatelessWidget {
  const _AccountSheet({required this.auth});

  final AuthController auth;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          ChordSyncSpace.lg,
          0,
          ChordSyncSpace.lg,
          ChordSyncSpace.lg,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Signed in as', style: textTheme.labelLarge),
            const SizedBox(height: 4),
            Text(
              auth.email ?? '',
              style: textTheme.titleLarge,
              overflow: TextOverflow.ellipsis,
            ),
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
      ),
    );
  }
}

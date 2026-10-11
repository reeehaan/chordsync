import 'package:flutter/material.dart';

import '../application/analyzed_practice_session.dart';
import 'upload_theme.dart';

/// The "Your songs" tab listing previously analyzed practice sessions.
class LibraryHome extends StatelessWidget {
  const LibraryHome({
    super.key,
    required this.sessions,
    required this.onOpen,
    required this.onAddSong,
  });

  final List<AnalyzedPracticeSession> sessions;
  final ValueChanged<AnalyzedPracticeSession> onOpen;
  final VoidCallback onAddSong;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 28, 20, 32),
      children: [
        Text('Your songs', style: Theme.of(context).textTheme.displayMedium),
        const SizedBox(height: 8),
        Text(
          'Pick up where you left off.',
          style: Theme.of(
            context,
          ).textTheme.bodyLarge?.copyWith(color: UploadPalette.secondaryText),
        ),
        const SizedBox(height: 28),
        if (sessions.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  const Icon(Icons.library_music_outlined, size: 42),
                  const SizedBox(height: 12),
                  Text(
                    'No analyzed songs yet',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Add an audio file to create your first practice sheet.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: onAddSong,
                    icon: const Icon(Icons.add),
                    label: const Text('Add a song'),
                  ),
                ],
              ),
            ),
          )
        else ...[
          Row(
            children: [
              Expanded(
                child: Text(
                  'Previously analyzed',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              Text(
                '${sessions.length} saved',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: UploadPalette.secondaryText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (final session in sessions)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _SavedPracticeCard(
                session: session,
                onOpen: () => onOpen(session),
              ),
            ),
        ],
      ],
    );
  }
}

class _SavedPracticeCard extends StatelessWidget {
  const _SavedPracticeCard({required this.session, required this.onOpen});

  final AnalyzedPracticeSession session;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 230,
      child: Card(
        child: InkWell(
          key: ValueKey('savedPractice-${session.job.jobId}'),
          borderRadius: BorderRadius.circular(16),
          onTap: onOpen,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
            child: Row(
              children: [
                const CircleAvatar(child: Icon(Icons.music_note)),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        session.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${session.timeline.bpm.toStringAsFixed(0)} BPM · Practice',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: UploadPalette.secondaryText,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/pressable_scale.dart';
import '../../../design_system/staggered_entrance.dart';
import '../../practice_timeline/data/song_identity.dart';
import '../application/analyzed_practice_session.dart';
import '../application/cloud_library_controller.dart';
import '../data/cloud_library_api.dart';
import '../data/embedded_cover_art.dart';
import '../../auth/application/profile_controller.dart';
import 'cover_tile.dart';
import 'discover_section.dart';
import 'upload_theme.dart';

/// The "Your songs" tab listing previously analyzed practice sessions.
class LibraryHome extends StatefulWidget {
  const LibraryHome({
    super.key,
    required this.sessions,
    required this.onOpen,
    required this.onAddSong,
    this.cloud,
    this.accountButton,
    this.profile,
  });

  final List<AnalyzedPracticeSession> sessions;
  final ValueChanged<AnalyzedPracticeSession> onOpen;
  final VoidCallback onAddSong;

  /// The shared library in the cloud. Null when the app has no cloud to ask
  /// (local development), and the section is then left out.
  final CloudLibraryController? cloud;

  /// Shown beside the title when the app has accounts; null otherwise.
  final Widget? accountButton;

  /// The signed-in person's profile, for ordering the genre shelves by their taste.
  final ProfileController? profile;

  @override
  State<LibraryHome> createState() => _LibraryHomeState();
}

class _LibraryHomeState extends State<LibraryHome> {
  final TextEditingController _search = TextEditingController();
  String _query = '';
  bool _showAllSaved = false;

  /// How many of the person's own songs show before "Show all".
  static const _recentCount = 5;

  @override
  void initState() {
    super.initState();
    final cloud = widget.cloud;
    if (cloud != null && cloud.status == CloudLibraryStatus.idle) {
      cloud.refresh();
    }
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  /// Songs whose title or artist contains every word typed, in any order.
  List<AnalyzedPracticeSession> get _matches {
    final words = _query
        .toLowerCase()
        .split(RegExp(r'\s+'))
        .where((word) => word.isNotEmpty)
        .toList();
    if (words.isEmpty) return widget.sessions;
    return [
      for (final session in widget.sessions)
        if (_containsAll(_haystack(session), words)) session,
    ];
  }

  List<String> get _words => _query
      .toLowerCase()
      .split(RegExp(r'\s+'))
      .where((word) => word.isNotEmpty)
      .toList();

  /// The genres the person picked at sign-up, in the order they chose them.
  List<String> get _favourites => widget.profile?.profile?.genres ?? const [];

  /// Changes in the cloud list or in the person's profile redraw the shelves.
  Listenable _tasteAnd(CloudLibraryController cloud) => widget.profile == null
      ? cloud
      : Listenable.merge([cloud, widget.profile!]);

  /// Cloud songs not already on this phone that match the search.
  List<CloudSong> _cloudMatches(CloudLibraryController cloud) {
    final onPhone = {for (final s in widget.sessions) s.job.jobId};
    final words = _words;
    return [
      for (final song in cloud.songs)
        if (!onPhone.contains(song.jobId) &&
            !cloud.isSaved(song.jobId) &&
            _containsAll(_cloudHaystack(song), words))
          song,
    ];
  }

  static String _cloudHaystack(CloudSong song) {
    final identity = SongIdentity.fromFileName(song.title);
    return '${identity.title} ${identity.artist ?? ''} ${song.title} '
            '${song.artist ?? ''} ${song.genres.join(' ')}'
        .toLowerCase();
  }

  void _dismissKeyboard() => FocusManager.instance.primaryFocus?.unfocus();

  static bool _containsAll(String text, List<String> words) =>
      words.every(text.contains);

  static String _haystack(AnalyzedPracticeSession session) {
    final identity = SongIdentity.fromFileName(session.title);
    return '${identity.title} ${identity.artist ?? ''} ${session.title}'
        .toLowerCase();
  }

  @override
  Widget build(BuildContext context) {
    final sessions = widget.sessions;
    final matches = _matches;
    final searching = _query.trim().isNotEmpty;
    // Tapping anywhere that is not a control, or scrolling the list, puts the
    // keyboard away; so does the search key.
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onTap: _dismissKeyboard,
      child: ListView(
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        padding: EdgeInsets.fromLTRB(
          20,
          28,
          20,
          // The glass dock floats over the page; leave room to scroll clear.
          32 + MediaQuery.paddingOf(context).bottom,
        ),
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  'Your songs',
                  style: Theme.of(context).textTheme.displayMedium,
                ),
              ),
              if (widget.accountButton != null) widget.accountButton!,
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Pick up where you left off.',
            style: Theme.of(
              context,
            ).textTheme.bodyLarge?.copyWith(color: UploadPalette.secondaryText),
          ),
          const SizedBox(height: 20),
          if (widget.cloud case final cloud? when !searching)
            ListenableBuilder(
              listenable: _tasteAnd(cloud),
              builder: (context, _) => Padding(
                padding: const EdgeInsets.only(bottom: 20),
                child: DiscoverHero(
                  songs: _cloudMatches(cloud),
                  cloud: cloud,
                  favourites: _favourites,
                ),
              ),
            ),
          if (sessions.isNotEmpty) ...[
            TextField(
              key: const ValueKey('songSearchField'),
              controller: _search,
              onChanged: (value) => setState(() => _query = value),
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _dismissKeyboard(),
              decoration: InputDecoration(
                hintText: 'Search songs or artists',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: searching
                    ? IconButton(
                        key: const ValueKey('clearSongSearch'),
                        tooltip: 'Clear search',
                        icon: const Icon(Icons.close),
                        onPressed: () {
                          _search.clear();
                          setState(() => _query = '');
                        },
                      )
                    : null,
              ),
            ),
            const SizedBox(height: 20),
          ] else
            const SizedBox(height: 8),
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
                      onPressed: widget.onAddSong,
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
                  searching
                      ? '${matches.length} of ${sessions.length}'
                      : '${sessions.length} saved',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: UploadPalette.secondaryText,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            if (matches.isEmpty)
              Padding(
                key: const ValueKey('noSongMatches'),
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Text(
                  'No songs match "${_query.trim()}".',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: UploadPalette.secondaryText,
                  ),
                ),
              ),
            for (final (index, session)
                in (searching || _showAllSaved
                        ? matches
                        : matches.take(_recentCount))
                    .indexed)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: StaggeredEntrance(
                  key: ValueKey('entrance-${session.job.jobId}'),
                  identity: session.job.jobId,
                  index: index,
                  child: PressableScale(
                    child: _SavedPracticeCard(
                      key: ValueKey('card-${session.job.jobId}'),
                      session: session,
                      onOpen: () => widget.onOpen(session),
                    ),
                  ),
                ),
              ),
            if (!searching && matches.length > _recentCount)
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: const ValueKey('toggleAllSaved'),
                  onPressed: () =>
                      setState(() => _showAllSaved = !_showAllSaved),
                  child: Text(
                    _showAllSaved
                        ? 'Show fewer'
                        : 'Show all ${matches.length} songs',
                  ),
                ),
              ),
          ],
          if (widget.cloud case final cloud?)
            ListenableBuilder(
              listenable: _tasteAnd(cloud),
              builder: (context, _) => searching
                  ? _CloudSection(
                      cloud: cloud,
                      songs: _cloudMatches(cloud),
                      searching: searching,
                    )
                  : DiscoverSection(
                      cloud: cloud,
                      songs: _cloudMatches(cloud),
                      favourites: _favourites,
                      showHero: false,
                    ),
            ),
        ],
      ),
    );
  }
}

/// Song names are set a little heavier, and their details a little darker,
/// than the default text so cards read clearly on the parchment page.
const _cardSecondary = Color(0xFF55473C);

TextStyle? _cardTitle(TextTheme textTheme) => textTheme.titleMedium?.copyWith(
  fontWeight: FontWeight.w700,
  color: ChordSyncColors.textPrimary,
);

class _SavedPracticeCard extends StatefulWidget {
  const _SavedPracticeCard({
    super.key,
    required this.session,
    required this.onOpen,
  });

  final AnalyzedPracticeSession session;
  final VoidCallback onOpen;

  @override
  State<_SavedPracticeCard> createState() => _SavedPracticeCardState();
}

class _SavedPracticeCardState extends State<_SavedPracticeCard> {
  /// Covers already read this run, so scrolling back does not read the file
  /// again.
  static final Map<String, Future<Uint8List?>> _covers = {};

  late final Future<Uint8List?> _cover = _covers.putIfAbsent(
    widget.session.audioFile.path,
    () => EmbeddedCoverArt.read(widget.session.audioFile),
  );

  @override
  Widget build(BuildContext context) {
    final session = widget.session;
    final identity = SongIdentity.fromFileName(session.title);
    final textTheme = Theme.of(context).textTheme;
    final chords = _firstChords(session, 4);
    return Card(
      child: InkWell(
        key: ValueKey('savedPractice-${session.job.jobId}'),
        borderRadius: BorderRadius.circular(16),
        onTap: widget.onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          child: Row(
            children: [
              CoverTile(future: _cover, seed: identity.title),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      identity.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: _cardTitle(textTheme),
                    ),
                    if (identity.artist != null)
                      Text(
                        identity.artist!,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodyMedium?.copyWith(
                          color: _cardSecondary,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    const SizedBox(height: 4),
                    Text(
                      '${_duration(session.timeline.endTime)} · '
                      '${session.timeline.bpm.toStringAsFixed(0)} BPM',
                      style: textTheme.bodySmall?.copyWith(
                        color: _cardSecondary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    if (chords.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          for (final chord in chords) _ChordChip(chord),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 6),
              const DecoratedBox(
                decoration: BoxDecoration(
                  color: ChordSyncColors.surfaceAlt,
                  shape: BoxShape.circle,
                ),
                child: Padding(
                  padding: EdgeInsets.all(6),
                  child: Icon(
                    Icons.chevron_right_rounded,
                    size: 22,
                    color: ChordSyncColors.brand,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The first [limit] different chords in the order they are played.
  static List<String> _firstChords(AnalyzedPracticeSession session, int limit) {
    final seen = <String>[];
    for (final bar in session.timeline.bars) {
      for (final beat in bar.beats) {
        if (beat.chord != 'N' && !seen.contains(beat.chord)) {
          seen.add(beat.chord);
          if (seen.length == limit) return seen;
        }
      }
    }
    return seen;
  }

  static String _duration(double seconds) {
    final total = seconds.round();
    final secs = (total % 60).toString().padLeft(2, '0');
    return '${total ~/ 60}:$secs';
  }
}

class _ChordChip extends StatelessWidget {
  const _ChordChip(this.chord);

  final String chord;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: ChordSyncColors.surfaceAlt,
        border: Border.all(
          color: ChordSyncColors.brand.withValues(alpha: 0.45),
        ),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        child: Text(
          chord,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
            color: ChordSyncColors.brandDark,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

/// The songs in the shared library that are not on this phone yet.
class _CloudSection extends StatelessWidget {
  const _CloudSection({
    required this.cloud,
    required this.songs,
    required this.searching,
  });

  final CloudLibraryController cloud;
  final List<CloudSong> songs;
  final bool searching;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final muted = textTheme.bodyMedium?.copyWith(
      color: UploadPalette.secondaryText,
    );
    final loading = cloud.status == CloudLibraryStatus.loading;
    final failed = cloud.status == CloudLibraryStatus.failed;
    return Padding(
      key: const ValueKey('cloudSection'),
      padding: const EdgeInsets.only(top: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('From the cloud', style: textTheme.titleLarge),
              ),
              if (loading)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                IconButton(
                  key: const ValueKey('refreshCloudSongs'),
                  tooltip: 'Refresh cloud songs',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.refresh),
                  onPressed: cloud.refresh,
                ),
            ],
          ),
          const SizedBox(height: 6),
          if (failed)
            Padding(
              key: const ValueKey('cloudFailed'),
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'Could not reach the cloud library. Check your connection '
                'and try again.',
                style: muted,
              ),
            )
          else if (!loading && songs.isEmpty)
            Padding(
              key: const ValueKey('cloudEmpty'),
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(
                searching
                    ? 'No cloud songs match your search.'
                    : 'Every song in the cloud is already on this phone.',
                style: muted,
              ),
            ),
          for (final song in songs)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _CloudSongCard(song: song, cloud: cloud),
            ),
        ],
      ),
    );
  }
}

class _CloudSongCard extends StatelessWidget {
  const _CloudSongCard({required this.song, required this.cloud});

  final CloudSong song;
  final CloudLibraryController cloud;

  @override
  Widget build(BuildContext context) {
    final identity = SongIdentity.fromFileName(song.title);
    // The server's artist, once the song has been tagged, beats the one guessed
    // from the file name.
    final artist = song.artist ?? identity.artist;
    final textTheme = Theme.of(context).textTheme;
    final progress = cloud.progressOf(song.jobId);
    final error = cloud.errorOf(song.jobId);
    final seconds = song.durationSeconds;
    return Card(
      key: ValueKey('cloudSong-${song.jobId}'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            CoverTile(future: Future.value(null), seed: identity.title),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    identity.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _cardTitle(textTheme),
                  ),
                  if (artist != null)
                    Text(
                      artist,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodyMedium?.copyWith(
                        color: _cardSecondary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  if (song.genres.isNotEmpty)
                    Text(
                      song.genres.join(' · '),
                      key: ValueKey('cloudGenres-${song.jobId}'),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodySmall?.copyWith(
                        color: ChordSyncColors.brand,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  if (seconds != null)
                    Text(
                      _SavedPracticeCardState._duration(seconds),
                      style: textTheme.bodySmall?.copyWith(
                        color: UploadPalette.secondaryText,
                      ),
                    ),
                  if (error != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        error,
                        key: ValueKey('cloudError-${song.jobId}'),
                        style: textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            if (progress != null)
              SizedBox(
                key: ValueKey('cloudProgress-${song.jobId}'),
                width: 28,
                height: 28,
                child: CircularProgressIndicator(
                  value: progress > 0 ? progress : null,
                  strokeWidth: 3,
                ),
              )
            else
              FilledButton.tonal(
                key: ValueKey('downloadCloudSong-${song.jobId}'),
                onPressed: () => cloud.download(song),
                child: Text(error == null ? 'Download' : 'Retry'),
              ),
          ],
        ),
      ),
    );
  }
}

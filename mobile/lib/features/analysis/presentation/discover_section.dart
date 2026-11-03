import 'package:flutter/material.dart';

import '../../../design_system/chordsync_design_system.dart';
import '../../../design_system/haptics.dart';
import '../../../design_system/pressable_scale.dart';
import '../application/cloud_library_controller.dart';
import '../application/genre_shelves.dart';
import '../data/cloud_library_api.dart';
import '../../practice_timeline/data/song_identity.dart';
import 'song_cover.dart';
import 'genre_style.dart';
import 'upload_theme.dart';

const _heroImage = 'assets/auth/welcome.jpg';

/// The shared library as a place to browse: a banner, a row of songs for each
/// genre (the person's favourites first), and a grid of all the genres.
class DiscoverSection extends StatelessWidget {
  const DiscoverSection({
    super.key,
    required this.cloud,
    required this.songs,
    this.favourites = const [],
    this.showHero = true,
  });

  final CloudLibraryController cloud;

  /// The songs not yet on this phone.
  final List<CloudSong> songs;
  final List<String> favourites;

  /// Whether the banner is part of the section (the Library screen shows it
  /// higher up, above the person's own songs).
  final bool showHero;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final muted = textTheme.bodyMedium?.copyWith(
      color: UploadPalette.secondaryText,
    );
    final loading = cloud.status == CloudLibraryStatus.loading;
    final failed = cloud.status == CloudLibraryStatus.failed;
    final layout = buildDiscoverLayout(songs, favourites: favourites);
    return Padding(
      key: const ValueKey('cloudSection'),
      padding: const EdgeInsets.only(top: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text('Discover', style: textTheme.titleLarge)),
              if (loading)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                IconButton(
                  key: const ValueKey('refreshCloudSongs'),
                  tooltip: 'Refresh songs',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.refresh),
                  onPressed: () => cloud.refresh(force: true),
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
          else if (!loading && layout.isEmpty)
            Padding(
              key: const ValueKey('cloudEmpty'),
              padding: const EdgeInsets.symmetric(vertical: 12),
              child: Text(
                'Every song in the cloud is already on this phone.',
                style: muted,
              ),
            ),
          if (!layout.isEmpty) ...[
            if (showHero) ...[
              DiscoverHero(songs: songs, cloud: cloud, favourites: favourites),
              const SizedBox(height: 8),
            ],
            for (final shelf in layout.shelves)
              _Shelf(
                key: ValueKey('shelf-${shelf.genre}'),
                title: shelf.genre,
                songs: shelf.songs,
                cloud: cloud,
                onSeeAll: () => _openGenre(context, shelf.genre),
              ),
            if (layout.untagged.isNotEmpty)
              _Shelf(
                key: const ValueKey('shelf-more'),
                title: 'More songs',
                songs: layout.untagged,
                cloud: cloud,
              ),
            if (layout.shelves.isNotEmpty) ...[
              const SizedBox(height: 20),
              Text('Browse all genres', style: textTheme.titleLarge),
              const SizedBox(height: 12),
              _GenreGrid(
                shelves: layout.shelves,
                onOpen: (genre) => _openGenre(context, genre),
              ),
            ],
          ],
        ],
      ),
    );
  }

  void _openGenre(BuildContext context, String genre) {
    Haptics.selection();
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => GenrePage(genre: genre, cloud: cloud),
      ),
    );
  }
}

/// The banner at the top of the Library: "Picked for you", and why. Tapping it
/// opens the person's top genre.
class DiscoverHero extends StatelessWidget {
  const DiscoverHero({
    super.key,
    required this.songs,
    required this.cloud,
    this.favourites = const [],
  });

  final List<CloudSong> songs;
  final CloudLibraryController cloud;
  final List<String> favourites;

  @override
  Widget build(BuildContext context) {
    final layout = buildDiscoverLayout(songs, favourites: favourites);
    if (layout.isEmpty) return const SizedBox.shrink();
    // With no genres yet there is nowhere to go, so the banner is just a banner.
    final top = layout.shelves.isEmpty
        ? null
        : (layout.favourites.isNotEmpty ? layout.favourites : layout.shelves)
              .first;
    return _HeroBanner(
      line: layout.heroLine,
      enabled: top != null,
      onTap: () {
        if (top == null) return;
        Haptics.selection();
        Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => GenrePage(genre: top.genre, cloud: cloud),
          ),
        );
      },
    );
  }
}

class _HeroBanner extends StatelessWidget {
  const _HeroBanner({
    required this.line,
    required this.onTap,
    required this.enabled,
  });

  final String? line;
  final VoidCallback onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      button: enabled,
      label: 'Picked for you. ${line ?? 'Songs from the ChordSync library'}',
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            key: const ValueKey('heroBanner'),
            onTap: enabled ? onTap : null,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(20),
              child: SizedBox(
                height: 148,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.asset(
                      _heroImage,
                      fit: BoxFit.cover,
                      alignment: const Alignment(0, -0.2),
                      cacheWidth: 900,
                    ),
                    const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.centerLeft,
                          end: Alignment.centerRight,
                          colors: [Color(0xE61A0E08), Color(0x331A0E08)],
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.all(18),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Text(
                            'Picked for you',
                            style: textTheme.headlineSmall?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            line ?? 'Songs from the ChordSync library',
                            style: textTheme.bodyMedium?.copyWith(
                              color: const Color(0xFFFBEBD3),
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
      ),
    );
  }
}

/// A title and a row of songs that scrolls sideways.
class _Shelf extends StatelessWidget {
  const _Shelf({
    super.key,
    required this.title,
    required this.songs,
    required this.cloud,
    this.onSeeAll,
  });

  final String title;
  final List<CloudSong> songs;
  final CloudLibraryController cloud;
  final VoidCallback? onSeeAll;

  static const _tile = 132.0;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.only(top: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(title, style: textTheme.titleLarge),
                ),
              ),
              if (onSeeAll != null)
                TextButton(
                  key: ValueKey('seeAll-$title'),
                  onPressed: onSeeAll,
                  child: Text('See all (${songs.length})'),
                ),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            height: _tile + 62,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              clipBehavior: Clip.none,
              itemCount: songs.length,
              separatorBuilder: (_, _) => const SizedBox(width: 12),
              itemBuilder: (context, index) =>
                  _SongTile(song: songs[index], cloud: cloud, width: _tile),
            ),
          ),
        ],
      ),
    );
  }
}

class _SongTile extends StatelessWidget {
  const _SongTile({
    required this.song,
    required this.cloud,
    required this.width,
  });

  final CloudSong song;
  final CloudLibraryController cloud;
  final double width;

  @override
  Widget build(BuildContext context) {
    final identity = SongIdentity.fromFileName(song.title);
    final artist = song.artist ?? identity.artist;
    final textTheme = Theme.of(context).textTheme;
    return Semantics(
      button: true,
      label: '${identity.title}${artist == null ? '' : ', $artist'}',
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            key: ValueKey('cloudSong-${song.jobId}'),
            behavior: HitTestBehavior.opaque,
            onTap: () => showSongSheet(context, cloud, song),
            child: SizedBox(
              width: width,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SongCover(
                    seed: identity.title,
                    coverUrl: song.coverUrl,
                    coverKey: song.jobId,
                    genres: song.genres,
                    size: width,
                    radius: 14,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    identity.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                      color: ChordSyncColors.textPrimary,
                    ),
                  ),
                  if (artist != null)
                    Text(
                      artist,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.bodySmall?.copyWith(
                        color: UploadPalette.secondaryText,
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

class _GenreGrid extends StatelessWidget {
  const _GenreGrid({required this.shelves, required this.onOpen});

  final List<GenreShelf> shelves;
  final ValueChanged<String> onOpen;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 12.0;
        final width = (constraints.maxWidth - gap) / 2;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final shelf in shelves)
              _GenreTile(
                shelf: shelf,
                width: width,
                onTap: () => onOpen(shelf.genre),
              ),
          ],
        );
      },
    );
  }
}

class _GenreTile extends StatelessWidget {
  const _GenreTile({
    required this.shelf,
    required this.width,
    required this.onTap,
  });

  final GenreShelf shelf;
  final double width;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final style = GenreStyle.of(shelf.genre);
    final textTheme = Theme.of(context).textTheme;
    final count = shelf.songs.length;
    return Semantics(
      button: true,
      label: '${shelf.genre}, $count ${count == 1 ? 'song' : 'songs'}',
      child: ExcludeSemantics(
        child: PressableScale(
          child: GestureDetector(
            key: ValueKey('genreTile-${shelf.genre}'),
            onTap: onTap,
            child: Container(
              width: width,
              height: 86,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                gradient: style.gradient,
                borderRadius: BorderRadius.circular(16),
              ),
              alignment: Alignment.bottomLeft,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    shelf.genre,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: textTheme.titleMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  Text(
                    '$count ${count == 1 ? 'song' : 'songs'}',
                    style: textTheme.bodySmall?.copyWith(
                      color: const Color(0xE6FFFFFF),
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

/// Every song of one genre, under a banner in the genre's colours.
class GenrePage extends StatelessWidget {
  const GenrePage({super.key, required this.genre, required this.cloud});

  final String genre;
  final CloudLibraryController cloud;

  @override
  Widget build(BuildContext context) {
    final style = GenreStyle.of(genre);
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      body: ListenableBuilder(
        listenable: cloud,
        builder: (context, _) {
          final songs = [
            for (final song in cloud.songs)
              if (song.genres.contains(genre) && !cloud.isSaved(song.jobId))
                song,
          ]..sort((a, b) => b.createdAt.compareTo(a.createdAt));
          return CustomScrollView(
            slivers: [
              SliverAppBar(
                pinned: true,
                expandedHeight: 170,
                backgroundColor: style.dark,
                foregroundColor: Colors.white,
                flexibleSpace: FlexibleSpaceBar(
                  titlePadding: const EdgeInsetsDirectional.only(
                    start: 56,
                    bottom: 14,
                  ),
                  title: Text(
                    genre,
                    style: textTheme.titleLarge?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  background: DecoratedBox(
                    decoration: BoxDecoration(gradient: style.gradient),
                    child: Align(
                      alignment: Alignment.bottomLeft,
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(56, 0, 20, 48),
                        child: Text(
                          '${songs.length} ${songs.length == 1 ? 'song' : 'songs'}',
                          key: const ValueKey('genreCount'),
                          style: textTheme.bodyMedium?.copyWith(
                            color: const Color(0xE6FFFFFF),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              if (songs.isEmpty)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Text(
                        'Every $genre song is already on this phone.',
                        textAlign: TextAlign.center,
                        style: textTheme.bodyLarge,
                      ),
                    ),
                  ),
                )
              else
                SliverPadding(
                  padding: EdgeInsets.fromLTRB(
                    20,
                    16,
                    20,
                    32 + MediaQuery.paddingOf(context).bottom,
                  ),
                  sliver: SliverList.separated(
                    itemCount: songs.length,
                    separatorBuilder: (_, _) => const SizedBox(height: 10),
                    itemBuilder: (context, index) =>
                        _SongRow(song: songs[index], cloud: cloud),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class _SongRow extends StatelessWidget {
  const _SongRow({required this.song, required this.cloud});

  final CloudSong song;
  final CloudLibraryController cloud;

  @override
  Widget build(BuildContext context) {
    final identity = SongIdentity.fromFileName(song.title);
    final artist = song.artist ?? identity.artist;
    final textTheme = Theme.of(context).textTheme;
    final progress = cloud.progressOf(song.jobId);
    return Card(
      child: InkWell(
        key: ValueKey('cloudSong-${song.jobId}'),
        borderRadius: BorderRadius.circular(16),
        onTap: () => showSongSheet(context, cloud, song),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              SongCover(
                seed: identity.title,
                coverUrl: song.coverUrl,
                coverKey: song.jobId,
                genres: song.genres,
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      identity.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: ChordSyncColors.textPrimary,
                      ),
                    ),
                    if (artist != null)
                      Text(
                        artist,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodyMedium?.copyWith(
                          color: UploadPalette.secondaryText,
                        ),
                      ),
                    if (song.genres.isNotEmpty)
                      Text(
                        song.genres.join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: textTheme.bodySmall?.copyWith(
                          color: ChordSyncColors.brand,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              if (progress != null)
                SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(
                    value: progress > 0 ? progress : null,
                    strokeWidth: 3,
                  ),
                )
              else
                const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}

/// A song's details, with the button that saves it on this phone to practise.
Future<void> showSongSheet(
  BuildContext context,
  CloudLibraryController cloud,
  CloudSong song,
) {
  Haptics.selection();
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (sheetContext) => _SongSheet(song: song, cloud: cloud),
  );
}

class _SongSheet extends StatelessWidget {
  const _SongSheet({required this.song, required this.cloud});

  final CloudSong song;
  final CloudLibraryController cloud;

  @override
  Widget build(BuildContext context) {
    final identity = SongIdentity.fromFileName(song.title);
    final artist = song.artist ?? identity.artist;
    final textTheme = Theme.of(context).textTheme;
    final seconds = song.durationSeconds;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
        child: ListenableBuilder(
          listenable: cloud,
          builder: (context, _) {
            final progress = cloud.progressOf(song.jobId);
            final error = cloud.errorOf(song.jobId);
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SongCover(
                      seed: identity.title,
                      coverUrl: song.coverUrl,
                      coverKey: song.jobId,
                      genres: song.genres,
                      size: 96,
                      radius: 16,
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(identity.title, style: textTheme.titleLarge),
                          if (artist != null)
                            Text(
                              artist,
                              style: textTheme.bodyLarge?.copyWith(
                                color: UploadPalette.secondaryText,
                              ),
                            ),
                          if (seconds != null)
                            Text(
                              _duration(seconds),
                              style: textTheme.bodySmall?.copyWith(
                                color: UploadPalette.secondaryText,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                if (song.genres.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 8,
                    runSpacing: 6,
                    children: [
                      for (final genre in song.genres)
                        Chip(
                          label: Text(genre),
                          visualDensity: VisualDensity.compact,
                        ),
                    ],
                  ),
                ],
                if (error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(
                      error,
                      key: ValueKey('cloudError-${song.jobId}'),
                      style: textTheme.bodyMedium?.copyWith(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                const SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: progress != null
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            LinearProgressIndicator(
                              key: ValueKey('cloudProgress-${song.jobId}'),
                              value: progress > 0 ? progress : null,
                            ),
                            const SizedBox(height: 8),
                            const Text('Saving to your songs…'),
                          ],
                        )
                      : FilledButton.icon(
                          key: ValueKey('downloadCloudSong-${song.jobId}'),
                          icon: const Icon(Icons.download),
                          label: Text(
                            error == null ? 'Save to practise' : 'Try again',
                          ),
                          onPressed: () async {
                            final navigator = Navigator.of(context);
                            final sheet = ModalRoute.of(context);
                            await cloud.download(song);
                            // Only close this sheet. If it is already gone,
                            // a pop would remove the home page instead.
                            if (cloud.errorOf(song.jobId) == null &&
                                navigator.mounted &&
                                (sheet?.isCurrent ?? false)) {
                              navigator.pop();
                            }
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

  static String _duration(double seconds) {
    final total = seconds.round();
    return '${total ~/ 60}:${(total % 60).toString().padLeft(2, '0')}';
  }
}

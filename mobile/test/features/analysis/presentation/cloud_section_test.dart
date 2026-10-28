import 'dart:async';
import 'dart:io';

import 'package:chordsync/features/analysis/application/analyzed_practice_session.dart';
import 'package:chordsync/features/analysis/application/cloud_library_controller.dart';
import 'package:chordsync/features/analysis/application/cloud_library_service.dart';
import 'package:chordsync/features/analysis/data/analysis_job.dart';
import 'package:chordsync/features/analysis/data/analyzed_session_library.dart';
import 'package:chordsync/features/analysis/data/cloud_library_api.dart';
import 'package:chordsync/features/analysis/presentation/library_home.dart';
import 'package:chordsync/features/auth/application/auth_controller.dart';
import 'package:chordsync/features/auth/application/profile_controller.dart';
import 'package:chordsync/features/auth/data/auth_token_store.dart';
import 'package:chordsync/features/auth/data/profile_api.dart';
import 'package:chordsync/features/auth/data/profile_store.dart';
import 'package:chordsync/features/auth/data/user_profile.dart';
import 'package:chordsync/features/practice_timeline/data/shared_timeline.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../../auth/fake_cognito.dart';

const _sudu = '11111111-aaaa-4bbb-8ccc-000000000001';
const _tum = '22222222-aaaa-4bbb-8ccc-000000000002';
const _lemon = '33333333-aaaa-4bbb-8ccc-000000000003';

class _Api implements CloudLibraryApi {
  Object? listError;
  List<CloudSong> songs = [
    _song(_sudu, 'Sudu Gawuma - La Signore'),
    _song(_tum, 'Tum Hi Ho - Arijit Singh'),
    _song(_lemon, 'Lemon - Kenshi Yonezu'),
  ];
  int listCalls = 0;

  @override
  Future<List<CloudSong>> listSongs() async {
    listCalls++;
    if (listError != null) throw listError!;
    return songs;
  }

  @override
  Future<SharedTimeline> getSongTimeline(String jobId) async => _timeline();

  @override
  Future<CloudAudioLink> getSongAudioLink(String jobId) async =>
      const CloudAudioLink(
        url: 'https://bucket.invalid/a.mp3?sig=1',
        expiresInSeconds: 600,
        fileType: 'mp3',
      );
}

class _Downloader implements AudioDownloader {
  Completer<void>? gate;
  Object? error;

  @override
  Future<void> download(
    String url,
    String destination, {
    void Function(double progress)? onProgress,
  }) async {
    onProgress?.call(0.4);
    await gate?.future;
    if (error != null) throw error!;
    await File(destination).writeAsBytes([1]);
  }
}

void main() {
  late Directory documents;
  late _Api api;
  late _Downloader downloader;
  late CloudLibraryController cloud;
  var sessions = <AnalyzedPracticeSession>[];

  setUp(() {
    documents = Directory.systemTemp.createTempSync('chordsync-cloud-ui-');
    api = _Api();
    downloader = _Downloader();
    sessions = [];
    cloud = CloudLibraryController(
      service: CloudLibraryService(
        api: api,
        library: LocalAnalyzedSessionLibrary(
          documentsDirectory: () async => documents,
        ),
        downloader: downloader,
        documentsDirectory: () async => documents,
      ),
    );
  });

  tearDown(() {
    cloud.dispose();
    documents.deleteSync(recursive: true);
  });

  /// The download mixes real file work with the test clock, so alternate:
  /// give the files real time, then let the widgets run what they now have.
  Future<void> letFilesSettle(WidgetTester tester) async {
    for (var step = 0; step < 30; step++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 20)),
      );
      await tester.pump(const Duration(milliseconds: 20));
    }
  }

  /// Scrolls the page itself (not a sideways shelf) until [finder] can be tapped.
  Future<void> bringIntoView(WidgetTester tester, Finder finder) async {
    final page = find.byType(ListView).first;
    final screen =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;
    for (var i = 0; i < 60 && tester.getCenter(finder).dy > screen - 90; i++) {
      await tester.drag(page, const Offset(0, -150));
      await tester.pump();
    }
    await tester.pumpAndSettle();
  }

  /// Brings a tile into view, then taps it (the shelves are below the fold).
  Future<void> tapTile(WidgetTester tester, Finder finder) async {
    await bringIntoView(tester, finder);
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> pump(
    WidgetTester tester, {
    bool withCloud = true,
    ProfileController? profile,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) {
              cloud.onDownloaded = (session) =>
                  setState(() => sessions = [...sessions, session]);
              return LibraryHome(
                sessions: sessions,
                onOpen: (_) {},
                onAddSong: () {},
                cloud: withCloud ? cloud : null,
                profile: profile,
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('shows the cloud songs to discover, with a banner', (
    tester,
  ) async {
    await pump(tester);

    expect(api.listCalls, 1);
    expect(find.text('Discover'), findsOneWidget);
    expect(find.byKey(const ValueKey('heroBanner')), findsOneWidget);
    expect(find.text('Picked for you'), findsOneWidget);
    // These songs have no genre yet, so they sit on one "More songs" shelf.
    expect(find.byKey(const ValueKey('shelf-more')), findsOneWidget);
    expect(find.text('Sudu Gawuma'), findsOneWidget);
    expect(find.text('La Signore'), findsOneWidget);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsOneWidget);
    expect(
      find.text('Browse all genres'),
      findsNothing,
    ); // there are no genres to browse
  });

  testWidgets(
    'each genre gets a shelf and a tile, and songs sit on every shelf they belong to',
    (tester) async {
      api.songs = _tagged();
      await pump(tester);

      for (final genre in ['Sinhala', 'Pop', 'Rock']) {
        expect(
          find.byKey(ValueKey('shelf-$genre'), skipOffstage: false),
          findsOneWidget,
        );
      }
      final pop = find.descendant(
        of: find.byKey(const ValueKey('shelf-Pop'), skipOffstage: false),
        matching: find.byType(GestureDetector),
        skipOffstage: false,
      );
      expect(pop, findsWidgets);
      await bringIntoView(tester, find.byKey(const ValueKey('genreTile-Rock')));
      expect(find.text('Browse all genres'), findsOneWidget);
      expect(find.byKey(const ValueKey('genreTile-Rock')), findsOneWidget);
    },
  );

  testWidgets(
    '"See all" opens the genre page with a banner and every song of the genre',
    (tester) async {
      api.songs = _tagged();
      await pump(tester);

      await tapTile(tester, find.byKey(const ValueKey('seeAll-Sinhala')));

      expect(find.text('Sinhala'), findsWidgets);
      expect(
        tester.widget<Text>(find.byKey(const ValueKey('genreCount'))).data,
        '2 songs',
      );
      expect(
        find.text('Sinhala · Pop'),
        findsOneWidget,
      ); // a song in two genres
      expect(find.text('Wonderwall'), findsNothing); // a Rock song is not here
      await tester.tap(find.byTooltip('Back'));
      await tester.pumpAndSettle();
      expect(find.text('Discover'), findsOneWidget);
    },
  );

  testWidgets(
    'the person\'s favourite genres come first, and the banner says why',
    (tester) async {
      api.songs = _tagged();
      final taste = await _profile(['Rock', 'Pop']);
      await pump(tester, profile: taste);

      expect(find.text('Because you like Rock and Pop'), findsOneWidget);
      final rock = tester.getTopLeft(find.byKey(const ValueKey('shelf-Rock')));
      final pop = tester.getTopLeft(find.byKey(const ValueKey('shelf-Pop')));
      final sinhala = tester.getTopLeft(
        find.byKey(const ValueKey('shelf-Sinhala'), skipOffstage: false),
      );
      expect(rock.dy, lessThan(pop.dy));
      expect(pop.dy, lessThan(sinhala.dy));
    },
  );

  testWidgets(
    'a tagged song shows the server\'s artist, and its genres in the sheet',
    (tester) async {
      api.songs = [
        CloudSong(
          jobId: 'tagged',
          title: 'Duvet',
          createdAt: DateTime.utc(2026, 10, 23),
          durationSeconds: 215.5,
          artist: 'Bôa',
          genres: const ['Rock', 'Indie'],
        ),
      ];
      await pump(tester);

      expect(find.text('Bôa'), findsWidgets);
      await tapTile(
        tester,
        find.byKey(const ValueKey('cloudSong-tagged')).first,
      );

      expect(find.text('Duvet'), findsWidgets);
      expect(find.widgetWithText(Chip, 'Rock'), findsOneWidget);
      expect(find.widgetWithText(Chip, 'Indie'), findsOneWidget);
      expect(find.text('3:36'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('downloadCloudSong-tagged')),
        findsOneWidget,
      );
    },
  );

  testWidgets('search finds cloud songs by genre', (tester) async {
    sessions = [
      _session(documents, _tum),
    ]; // the search box shows once a song is saved
    api.songs = [
      CloudSong(
        jobId: 'a',
        title: 'Sandapana Wage',
        createdAt: DateTime.utc(2026, 10, 23),
        genres: const ['Sinhala'],
      ),
      CloudSong(
        jobId: 'b',
        title: 'Wonderwall',
        createdAt: DateTime.utc(2026, 10, 23),
        genres: const ['Rock', 'Indie'],
      ),
    ];
    await pump(tester);

    await tester.enterText(
      find.byKey(const ValueKey('songSearchField')),
      'sinhala',
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('cloudSong-a')), findsOneWidget);
    expect(find.byKey(const ValueKey('cloudSong-b')), findsNothing);
  });

  testWidgets(
    'a long list of your own songs shows five, with a button for the rest',
    (tester) async {
      sessions = [
        for (var i = 1; i <= 7; i++)
          _session(documents, '4444444$i-aaaa-4bbb-8ccc-00000000000$i'),
      ];
      api.songs = [];
      await pump(tester);

      await tester.scrollUntilVisible(
        find.byKey(const ValueKey('toggleAllSaved')),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Show all 7 songs'), findsOneWidget);
      expect(
        find.byWidgetPredicate(
          (w) => w.key.toString().contains('savedPractice-'),
          skipOffstage: false,
        ),
        findsNWidgets(5),
      );

      await tester.ensureVisible(find.byKey(const ValueKey('toggleAllSaved')));
      await tester.tap(find.byKey(const ValueKey('toggleAllSaved')));
      await tester.pumpAndSettle();
      // Seven songs are listed now, so the button has moved further down.
      await tester.scrollUntilVisible(
        find.text('Show fewer'),
        200,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Show fewer'), findsOneWidget);
      expect(
        find.byWidgetPredicate(
          (w) => w.key.toString().contains('savedPractice-'),
          skipOffstage: false,
        ),
        findsNWidgets(7),
      );
    },
  );

  testWidgets('five songs or fewer need no button', (tester) async {
    sessions = [
      for (var i = 1; i <= 5; i++)
        _session(documents, '5555555$i-aaaa-4bbb-8ccc-00000000000$i'),
    ];
    api.songs = [];
    await pump(tester);

    expect(
      find.byKey(const ValueKey('toggleAllSaved'), skipOffstage: false),
      findsNothing,
    );
  });

  // --- the genre chips above the person's own songs ---

  /// Two saved songs, whose genres the cloud knows by id.
  Future<void> twoSavedSongs(
    WidgetTester tester, {
    ProfileController? profile,
  }) async {
    sessions = [
      _sessionTitled(documents, _sudu, 'Sudu Gawuma - La Signore'),
      _sessionTitled(documents, _lemon, 'Lemon - Kenshi Yonezu'),
    ];
    api.songs = [
      CloudSong(
        jobId: _sudu,
        title: 'Sudu Gawuma - La Signore',
        createdAt: DateTime.utc(2026, 10, 1),
        genres: const ['Sinhala', 'Pop'],
      ),
      CloudSong(
        jobId: _lemon,
        title: 'Lemon - Kenshi Yonezu',
        createdAt: DateTime.utc(2026, 10, 2),
        genres: const ['Pop'],
      ),
    ];
    await pump(tester, profile: profile);
  }

  testWidgets(
    'your songs are labelled "Your songs" and filter by genre chips',
    (tester) async {
      await twoSavedSongs(tester);

      expect(find.text('Your songs'), findsOneWidget);
      expect(find.text('Previously analyzed'), findsNothing);
      expect(find.text('All · 2'), findsOneWidget);
      expect(
        find.text('Pop · 2'),
        findsOneWidget,
      ); // a song in two genres counts in both
      expect(find.text('Sinhala · 1'), findsOneWidget);
      expect(find.byKey(ValueKey('card-$_sudu')), findsOneWidget);
      expect(find.byKey(ValueKey('card-$_lemon')), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('genreChip-Sinhala')));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey('card-$_sudu')), findsOneWidget);
      expect(find.byKey(ValueKey('card-$_lemon')), findsNothing);
      expect(find.text('1 of 2'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('genreChip-all')));
      await tester.pumpAndSettle();
      expect(find.byKey(ValueKey('card-$_lemon')), findsOneWidget);
      expect(find.text('2 saved'), findsOneWidget);
    },
  );

  testWidgets('a saved card shows its genres', (tester) async {
    await twoSavedSongs(tester);

    expect(find.byKey(ValueKey('savedGenres-$_sudu')), findsOneWidget);
    expect(find.text('Sinhala · Pop'), findsOneWidget);
    expect(find.text('Pop'), findsWidgets);
  });

  testWidgets('a saved song whose copy was replaced is matched by its title', (
    tester,
  ) async {
    sessions = [
      _sessionTitled(
        documents,
        'old-copy-0000-aaaa-4bbb-8ccc-000000000009',
        'Lemon - Kenshi Yonezu - Spotimate.app',
      ),
    ];
    api.songs = [
      CloudSong(
        jobId: _lemon,
        title: 'Lemon',
        createdAt: DateTime.utc(2026, 10, 2),
        genres: const ['Pop'],
      ),
    ];
    await pump(tester);

    expect(find.byKey(const ValueKey('genreChip-Pop')), findsOneWidget);
  });

  testWidgets('songs with no genre yet get their own chip', (tester) async {
    sessions = [
      _sessionTitled(documents, _sudu, 'Sudu Gawuma - La Signore'),
      _sessionTitled(documents, _lemon, 'Some Home Recording'),
    ];
    api.songs = [
      CloudSong(
        jobId: _sudu,
        title: 'Sudu Gawuma - La Signore',
        createdAt: DateTime.utc(2026, 10, 1),
        genres: const ['Sinhala'],
      ),
    ];
    await pump(tester);

    expect(find.text('No genre yet · 1'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('genreChip-\u0000none')));
    await tester.pumpAndSettle();
    expect(find.byKey(ValueKey('card-$_lemon')), findsOneWidget);
    expect(find.byKey(ValueKey('card-$_sudu')), findsNothing);
  });

  testWidgets('with no genres known there are no chips', (tester) async {
    sessions = [_sessionTitled(documents, _sudu, 'Sudu Gawuma - La Signore')];
    api.songs = [_song(_sudu, 'Sudu Gawuma - La Signore')]; // not tagged yet
    await pump(tester);

    expect(find.byKey(const ValueKey('genreChip-all')), findsNothing);
    expect(find.text('Your songs'), findsOneWidget);
    await pump(tester, withCloud: false);
    expect(find.byKey(const ValueKey('genreChip-all')), findsNothing);
  });

  testWidgets(
    'the chips step aside while searching, and the search covers every song',
    (tester) async {
      await twoSavedSongs(tester);
      await tester.tap(find.byKey(const ValueKey('genreChip-Sinhala')));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const ValueKey('songSearchField')),
        'lemon',
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const ValueKey('genreChip-all')), findsNothing);
      expect(
        find.byKey(ValueKey('card-$_lemon')),
        findsOneWidget,
      ); // found despite the Sinhala chip
    },
  );

  testWidgets('the page says Home, or greets the person by first name', (
    tester,
  ) async {
    await pump(tester);
    expect(find.text('Home'), findsOneWidget);

    final taste = await _profile(['Pop']);
    await pump(tester, profile: taste);
    expect(find.text('Hello, Kim'), findsOneWidget);
    expect(find.text('Home'), findsNothing);
  });

  testWidgets('songs already on the phone are not offered again', (
    tester,
  ) async {
    sessions = [_session(documents, _tum)];
    await pump(tester);

    expect(find.byKey(ValueKey('cloudSong-$_tum')), findsNothing);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsOneWidget);
    // Only the saved copy of that song is on screen.
    expect(find.text('Tum Hi Ho'), findsOneWidget);
  });

  testWidgets('downloading shows progress, then the song moves to the phone', (
    tester,
  ) async {
    downloader.gate = Completer<void>();
    await pump(tester);

    await tapTile(tester, find.byKey(ValueKey('cloudSong-$_sudu')));
    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await tester.pump();
    await tester.pump();
    expect(find.byKey(ValueKey('cloudProgress-$_sudu')), findsOneWidget);
    expect(find.byKey(ValueKey('downloadCloudSong-$_sudu')), findsNothing);

    downloader.gate!.complete();
    await letFilesSettle(tester);
    await tester.pumpAndSettle();

    expect(sessions.single.job.jobId, _sudu);
    expect(sessions.single.audioFile.existsSync(), isTrue);
    expect(
      find.byKey(ValueKey('cloudProgress-$_sudu')),
      findsNothing,
    ); // the sheet closed
    expect(
      find.byKey(ValueKey('cloudSong-$_sudu')),
      findsNothing,
    ); // off the shelf
    expect(find.byKey(ValueKey('savedPractice-$_sudu')), findsOneWidget);
  });

  testWidgets('a failed download says so and offers to try again', (
    tester,
  ) async {
    downloader.error = const SocketException('offline');
    await pump(tester);

    await tapTile(tester, find.byKey(ValueKey('cloudSong-$_sudu')));
    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await letFilesSettle(tester);

    expect(find.byKey(ValueKey('cloudError-$_sudu')), findsOneWidget);
    expect(sessions, isEmpty);
    expect(find.text('Try again'), findsOneWidget); // the sheet stays open

    downloader.error = null;
    await tester.tap(find.byKey(ValueKey('downloadCloudSong-$_sudu')));
    await letFilesSettle(tester);
    await tester.pumpAndSettle();
    expect(sessions.single.job.jobId, _sudu);
  });

  testWidgets('an unreachable cloud shows a message and can be retried', (
    tester,
  ) async {
    api.listError = const SocketException('offline');
    await pump(tester);
    expect(find.byKey(const ValueKey('cloudFailed')), findsOneWidget);

    api.listError = null;
    await tester.tap(find.byKey(const ValueKey('refreshCloudSongs')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('cloudFailed')), findsNothing);
    expect(find.text('Lemon'), findsOneWidget);
  });

  testWidgets('search also filters the cloud songs', (tester) async {
    sessions = [_session(documents, _tum)];
    await pump(tester);

    await tester.enterText(
      find.byKey(const ValueKey('songSearchField')),
      'kenshi',
    );
    await tester.pump();
    expect(find.byKey(ValueKey('cloudSong-$_lemon')), findsOneWidget);
    expect(find.byKey(ValueKey('cloudSong-$_sudu')), findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('songSearchField')),
      'zzz',
    );
    await tester.pump();
    expect(find.text('No cloud songs match your search.'), findsOneWidget);
  });

  testWidgets('with nothing in the cloud and nothing on the phone', (
    tester,
  ) async {
    api.songs = [];
    await pump(tester);

    expect(find.text('No analyzed songs yet'), findsOneWidget);
    expect(find.byKey(const ValueKey('cloudEmpty')), findsOneWidget);
  });

  testWidgets('no cloud section when the app has no cloud', (tester) async {
    await pump(tester, withCloud: false);

    expect(find.text('Discover'), findsNothing);
    expect(find.byKey(const ValueKey('heroBanner')), findsNothing);
    expect(api.listCalls, 0);
  });
}

/// Five songs: two Sinhala (one also Pop), a Pop one, a Rock one, and a Rock-Indie one.
List<CloudSong> _tagged() => [
  CloudSong(
    jobId: 's1',
    title: 'Sandapana Wage',
    createdAt: DateTime.utc(2026, 10, 1),
    genres: const ['Sinhala'],
  ),
  CloudSong(
    jobId: 's2',
    title: 'Pem Lowe',
    createdAt: DateTime.utc(2026, 10, 2),
    genres: const ['Sinhala', 'Pop'],
  ),
  CloudSong(
    jobId: 'p1',
    title: 'Lemon',
    createdAt: DateTime.utc(2026, 10, 3),
    genres: const ['Pop'],
  ),
  CloudSong(
    jobId: 'r1',
    title: 'Wonderwall',
    createdAt: DateTime.utc(2026, 10, 4),
    genres: const ['Rock', 'Indie'],
  ),
  CloudSong(
    jobId: 'r2',
    title: 'Duvet',
    createdAt: DateTime.utc(2026, 10, 5),
    genres: const ['Rock'],
  ),
];

class _SavedProfileApi implements ProfileApi {
  _SavedProfileApi(this.profile);
  final UserProfile profile;
  @override
  Future<UserProfile?> fetch() async => profile;
  @override
  Future<UserProfile> save(UserProfile profile) async => profile;
}

/// A signed-in person whose profile lists these favourite genres.
Future<ProfileController> _profile(List<String> genres) async {
  final cognito = FakeCognito();
  final auth = AuthController(
    api: cognito,
    store: MemoryAuthTokenStore(cognito.tokens('kim@example.com')),
    clock: () => DateTime.utc(2026, 1, 1, 0, 10),
  );
  final controller = ProfileController(
    api: _SavedProfileApi(
      UserProfile(
        name: 'Kim',
        birthYear: 2000,
        genres: genres,
        experience: GuitarExperience.beginner,
      ),
    ),
    store: MemoryProfileStore(),
    auth: auth,
  );
  await auth.restore();
  await controller.sync();
  return controller;
}

CloudSong _song(String id, String title) => CloudSong(
  jobId: id,
  title: title,
  createdAt: DateTime.utc(2026, 10, 23),
  durationSeconds: 215.5,
);

SharedTimeline _timeline() => const SharedTimeline(
  schemaVersion: 1,
  bpm: 88,
  beatsPerBar: 4,
  beatSource: 'test',
  lyricSource: 'test',
  bars: [],
  lyrics: [],
);

AnalyzedPracticeSession _sessionTitled(
  Directory directory,
  String id,
  String title,
) {
  final base = _session(directory, id);
  return AnalyzedPracticeSession(
    title: title,
    job: base.job,
    audioFile: base.audioFile,
    timeline: base.timeline,
  );
}

AnalyzedPracticeSession _session(Directory directory, String id) {
  File('${directory.path}/$id.mp3').writeAsBytesSync([1]);
  return AnalyzedPracticeSession(
    title: 'Tum Hi Ho - Arijit Singh',
    job: AnalysisJob(
      jobId: id,
      status: AnalysisJobStatus.completed,
      createdAt: DateTime.utc(2026, 10, 22),
      updatedAt: DateTime.utc(2026, 10, 22),
      error: null,
      resultAvailable: true,
    ),
    audioFile: File('${directory.path}/$id.mp3'),
    timeline: _timeline(),
  );
}

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'design_system/chordsync_design_system.dart';
import 'design_system/motion.dart';
import 'features/analysis/application/analysis_job_poller.dart';
import 'features/analysis/application/cloud_library_controller.dart';
import 'features/analysis/application/cloud_library_service.dart';
import 'features/analysis/application/analysis_practice_coordinator.dart';
import 'features/analysis/data/analysis_api_client.dart';
import 'features/analysis/application/hosted_analysis_client.dart';
import 'features/analysis/data/analysis_api_config.dart';
import 'features/analysis/data/hosted_analysis_api.dart';
import 'features/analysis/data/presigned_uploader.dart';
import 'features/analysis/data/analyzed_session_library.dart';
import 'features/analysis/data/sample_song.dart';
import 'features/analysis/presentation/analysis_progress_banner.dart';
import 'features/analysis/presentation/audio_file_selector.dart';
import 'features/analysis/presentation/page_route_tracker.dart';
import 'features/auth/application/auth_controller.dart';
import 'features/auth/data/auth_token_store.dart';
import 'features/auth/data/cognito_api.dart';
import 'features/auth/data/cognito_config.dart';
import 'features/auth/application/profile_controller.dart';
import 'features/auth/data/profile_api.dart';
import 'features/auth/data/profile_store.dart';
import 'features/auth/presentation/account_button.dart';
import 'features/auth/presentation/auth_gate.dart';
import 'features/splash/chordsync_splash_screen.dart';
import 'features/splash/splash_sound.dart';
import 'features/analysis/presentation/audio_import_controller.dart';
import 'features/analysis/presentation/audio_import_screen.dart';
import 'features/practice_timeline/application/practice_audio_player.dart';
import 'features/practice_timeline/application/practice_session_factory.dart';
import 'features/practice_timeline/presentation/practice_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // The app is portrait-only; turning the phone does not rotate it.
  await SystemChrome.setPreferredOrientations(const [
    DeviceOrientation.portraitUp,
  ]);
  runApp(const MyApp(showSplash: true));
}

class MyApp extends StatefulWidget {
  const MyApp({
    super.key,
    this.audioPlayer,
    this.analyzedSession,
    this.sessionFactory,
    this.importController,
    this.fileSelector,
    this.showSplash = false,
    this.splashSound,
    this.authController,
    this.profileStore,
  });

  /// Signs people in. Made from the build settings when null, and only when the
  /// build names a Cognito app client; without one the app opens straight on
  /// the home screen, as before.
  final AuthController? authController;
  final ProfileStore? profileStore;

  /// Plays the opening animation before the first screen. Off by default so
  /// tests and fixtures open straight on their screen.
  final bool showSplash;

  /// The chord strummed on the splash. The real recording when null; tests
  /// pass a silent one.
  final SplashSound? splashSound;

  final PracticeAudioPlayer? audioPlayer;
  final AnalyzedPracticeSession? analyzedSession;
  final PracticeSessionFactory? sessionFactory;
  final AudioImportController? importController;
  final AudioFileSelector? fileSelector;

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  AudioImportController? _importController;
  AnalyzedSessionLibrary? _sessionLibrary;
  CloudLibraryController? _cloudLibrary;
  AuthController? _auth;
  ProfileController? _profileController;
  late final ProfileStore _profiles =
      widget.profileStore ?? SecureProfileStore();

  bool get _usesPracticeFixture =>
      widget.audioPlayer != null || widget.analyzedSession != null;

  @override
  void initState() {
    super.initState();
    if (!_usesPracticeFixture) {
      _auth = widget.authController ?? _createAuthController();
      _profileController = _createProfileController();
      _sessionLibrary = _withSample(LocalAnalyzedSessionLibrary());
      _importController = widget.importController ?? _createImportController();
      _cloudLibrary = _createCloudLibrary();
    }
  }

  AuthController? _createAuthController() {
    const cognito = CognitoConfig.fromEnvironment;
    if (!cognito.isConfigured) return null;
    return AuthController(
      api: DioCognitoApi(config: cognito),
      store: SecureAuthTokenStore(),
    )..restore();
  }

  /// Keeps the signed-in person's profile; only when the app has sign-in and
  /// talks to the hosted API.
  ProfileController? _createProfileController() {
    final auth = _auth;
    final config = AnalysisApiConfig.development;
    if (auth == null || !config.isHosted) return null;
    return ProfileController(
      api: DioProfileApi(
        baseUrl: config.baseUrl,
        tokenProvider: auth.accessToken,
      ),
      store: _profiles,
      auth: auth,
    );
  }

  /// The token each API request carries: the signed-in person's own when the
  /// app has sign-in, otherwise the build-time demo token.
  Future<String?> Function() _tokenProvider(AnalysisApiConfig config) {
    final auth = _auth;
    return auth == null ? () async => config.authToken : auth.accessToken;
  }

  /// The shared library only exists on the hosted API; local development has
  /// no cloud to ask.
  CloudLibraryController? _createCloudLibrary() {
    final config = AnalysisApiConfig.development;
    if (!config.isHosted) return null;
    return CloudLibraryController(
      service: CloudLibraryService(
        api: DioHostedAnalysisApi(
          baseUrl: config.baseUrl,
          tokenProvider: _tokenProvider(config),
        ),
        library: _sessionLibrary!,
      ),
    );
  }

  /// Builds that pass `--dart-define=CHORDSYNC_SHOW_CHORD_SAMPLE=true` also list
  /// a built-in song that plays through the 7th and sus chord shapes.
  static const _showChordSample = bool.fromEnvironment(
    'CHORDSYNC_SHOW_CHORD_SAMPLE',
  );

  AnalyzedSessionLibrary _withSample(AnalyzedSessionLibrary library) =>
      _showChordSample
      ? SampleAugmentedLibrary(library, SampleSong())
      : library;

  AudioImportController _createImportController() {
    final config = AnalysisApiConfig.development;
    final client = _createAnalysisClient(config);
    return AudioImportController(
      preparation: AnalysisPracticeCoordinator(
        client: client,
        polling: AnalysisJobPoller(
          client: client,
          // The hosted API is rate limited and a job takes minutes.
          pollingInterval: Duration(seconds: config.isHosted ? 3 : 1),
        ),
      ),
      sessionLibrary: _sessionLibrary,
    );
  }

  /// Local development keeps the one-request multipart upload. The hosted API
  /// uses a presigned upload: create the job, send the audio straight to
  /// storage, then confirm.
  AnalysisApiClient _createAnalysisClient(AnalysisApiConfig config) {
    if (!config.hasSecureHostedUrl) {
      // A build-time mistake: stop at once rather than send the token in the
      // clear.
      throw StateError('CHORDSYNC_API_BASE_URL must be https in hosted mode.');
    }
    if (!config.isHosted) {
      return DioAnalysisApiClient(baseUrl: config.baseUrl);
    }
    return HostedAnalysisClient(
      api: DioHostedAnalysisApi(
        baseUrl: config.baseUrl,
        tokenProvider: _tokenProvider(config),
      ),
      // A separate plain client: the bearer token must never reach storage.
      uploader: DioPresignedUploader(),
    );
  }

  final _navigatorKey = GlobalKey<NavigatorState>();
  final _routes = PageRouteTracker();
  final _bannerInset = ValueNotifier<double>(0);

  void _playFinished(AnalyzedPracticeSession session) {
    _importController?.reset();
    _navigatorKey.currentState?.push<void>(
      MaterialPageRoute(
        builder: (_) => PracticeScreen(
          analyzedSession: session,
          sessionFactory: widget.sessionFactory,
        ),
      ),
    );
  }

  @override
  void dispose() {
    _importController?.dispose();
    _cloudLibrary?.dispose();
    _profileController?.dispose();
    if (widget.authController == null) _auth?.dispose();
    _bannerInset.dispose();
    super.dispose();
  }

  late bool _splashDone = !widget.showSplash;
  // One sound for the app's whole opening, made only when it will be used.
  late final SplashSound _splashSound =
      widget.splashSound ?? JustAudioSplashSound();

  Widget _home() => _usesPracticeFixture
      ? PracticeScreen(
          audioPlayer: widget.audioPlayer,
          analyzedSession: widget.analyzedSession,
          sessionFactory: widget.sessionFactory,
        )
      : AudioImportScreen(
          controller: _importController!,
          fileSelector: widget.fileSelector ?? const NativeAudioFileSelector(),
          practiceSessionFactory: widget.sessionFactory,
          sessionLibrary: _sessionLibrary,
          cloudLibrary: _cloudLibrary,
          profile: _profileController,
          accountButton: _auth == null
              ? null
              : AccountButton(auth: _auth!, profile: _profileController),
          bannerInset: _bannerInset,
        );

  /// With sign-in set up, the app opens on the welcome screens until someone
  /// signs in.
  Widget _gated(Widget home) {
    final auth = _auth;
    if (auth == null) return home;
    return AuthGate(auth: auth, profiles: _profiles, signedIn: home);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      navigatorObservers: [_routes],
      title: 'ChordSync',
      theme: ChordSyncTheme.light(),
      // Follow the person's text size setting (Dynamic Type), up to a size the
      // fixed-height rows (lyrics, chord cards) can still hold.
      builder: (context, child) {
        final media = MediaQuery.of(context);
        final importController = _importController;
        return MediaQuery(
          data: media.copyWith(
            textScaler: media.textScaler.clamp(maxScaleFactor: 1.3),
          ),
          // The banner floats above every screen, so a song being analyzed
          // stays in view wherever the person goes.
          child: Stack(
            children: [
              child!,
              if (importController != null)
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: AnalysisProgressBanner(
                    controller: importController,
                    // Hidden over pages, dialogs and sheets.
                    atHome: _routes.uncovered,
                    onInsetChanged: (inset) => _bannerInset.value = inset,
                    onPlay: _playFinished,
                  ),
                ),
            ],
          ),
        );
      },
      // A Builder, so the hand-over can read the app's own MediaQuery.
      home: Builder(
        // The parchment behind the hand-over: with nothing there, the two
        // screens fading past each other let black show through.
        builder: (context) => ColoredBox(
          color: ChordSyncColors.background,
          child: AnimatedSwitcher(
            duration: ChordSyncMotion.of(context, ChordSyncMotion.quick),
            child: _splashDone
                ? _gated(_home())
                : ChordSyncSplashScreen(
                    sound: _splashSound,
                    onFinished: () => setState(() => _splashDone = true),
                  ),
          ),
        ),
      ),
    );
  }
}

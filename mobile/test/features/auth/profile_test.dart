import 'dart:convert';
import 'dart:typed_data';

import 'package:chordsync/features/auth/application/auth_controller.dart';
import 'package:chordsync/features/auth/application/profile_controller.dart';
import 'package:chordsync/features/auth/data/auth_token_store.dart';
import 'package:chordsync/features/auth/data/profile_api.dart';
import 'package:chordsync/features/auth/data/profile_store.dart';
import 'package:chordsync/features/auth/data/user_profile.dart';
import 'package:dio/dio.dart';
import 'package:chordsync/features/auth/presentation/account_button.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_cognito.dart';

const _kim = UserProfile(
  name: 'Kim Lee',
  birthYear: 2000,
  genres: ['Pop', 'Jazz'],
  experience: GuitarExperience.intermediate,
);
const _server = UserProfile(
  name: 'Kim From Server',
  birthYear: 1999,
  genres: ['Folk'],
  experience: GuitarExperience.advanced,
);

class _FakeProfileApi implements ProfileApi {
  UserProfile? onServer;
  bool offline = false;
  final calls = <String>[];

  @override
  Future<UserProfile?> fetch() async {
    calls.add('fetch');
    if (offline) throw const ProfileApiException('offline');
    return onServer;
  }

  @override
  Future<UserProfile> save(UserProfile profile) async {
    calls.add('save:${profile.name}');
    if (offline) throw const ProfileApiException('offline');
    return onServer = profile;
  }
}

/// Lets queued work finish. Microtasks only, so it also works under the widget
/// tester's fake clock (a real timer would never fire there).
Future<void> _settle() async {
  for (var i = 0; i < 20; i++) {
    await Future<void>.value();
  }
}

void main() {
  _registerHttpTests();
  late FakeCognito cognito;
  late MemoryAuthTokenStore tokens;
  late AuthController auth;
  late _FakeProfileApi api;
  late MemoryProfileStore store;

  Future<ProfileController> build({
    bool signedIn = true,
    String email = 'kim@example.com',
  }) async {
    cognito = FakeCognito();
    tokens = MemoryAuthTokenStore(signedIn ? cognito.tokens(email) : null);
    auth = AuthController(
      api: cognito,
      store: tokens,
      clock: () => DateTime.utc(2026, 1, 1, 0, 10),
    );
    api = _FakeProfileApi();
    store = MemoryProfileStore();
    final controller = ProfileController(api: api, store: store, auth: auth);
    await auth.restore();
    await _settle();
    await _settle();
    return controller;
  }

  test(
    'an edited profile is saved to the account and kept on the phone',
    () async {
      final controller = await build();
      expect(controller.profile, isNull);

      await controller.save(_kim);

      expect(controller.profile?.name, 'Kim Lee');
      expect(api.onServer?.name, 'Kim Lee');
      expect(store.local?.profile.name, 'Kim Lee');
    },
  );

  test('a failed save keeps the earlier profile', () async {
    api = _FakeProfileApi()..onServer = _server;
    final controller = await build();
    api.onServer = _server;
    await controller.sync();
    api.offline = true;

    await expectLater(
      controller.save(_kim),
      throwsA(isA<ProfileApiException>()),
    );
    expect(controller.profile?.name, _server.name);
  });

  test('the profile on the account is shown and kept on the phone', () async {
    api = _FakeProfileApi()..onServer = _server;
    final controller = await build();
    api.onServer = _server;
    await controller.sync();

    expect(controller.profile?.name, 'Kim From Server');
    expect(controller.status, ProfileStatus.ready);
    expect(store.local?.email, 'kim@example.com');
    expect(store.profile?.name, 'Kim From Server');
  });

  test(
    'the sign-up answers kept on the phone are sent to a new account',
    () async {
      cognito = FakeCognito();
      tokens = MemoryAuthTokenStore(cognito.tokens('kim@example.com'));
      auth = AuthController(
        api: cognito,
        store: tokens,
        clock: () => DateTime.utc(2026, 1, 1, 0, 10),
      );
      api = _FakeProfileApi();
      store = MemoryProfileStore();
      await store.write(_kim, email: 'kim@example.com');
      final controller = ProfileController(api: api, store: store, auth: auth);

      await auth.restore();
      await _settle();
      await _settle();

      expect(api.calls, ['fetch', 'save:Kim Lee']);
      expect(controller.profile, isNotNull);
      expect(controller.profile?.name, 'Kim Lee');
      expect(api.onServer?.name, 'Kim Lee');
      expect(controller.status, ProfileStatus.ready);
    },
  );

  test(
    "another person's unfinished sign-up is never sent to this account",
    () async {
      cognito = FakeCognito();
      tokens = MemoryAuthTokenStore(cognito.tokens('kim@example.com'));
      auth = AuthController(
        api: cognito,
        store: tokens,
        clock: () => DateTime.utc(2026, 1, 1, 0, 10),
      );
      api = _FakeProfileApi();
      store = MemoryProfileStore();
      await store.write(_kim, email: 'someone.else@example.com');
      final controller = ProfileController(api: api, store: store, auth: auth);

      await auth.restore();
      await _settle();
      await _settle();

      expect(api.calls, ['fetch']); // no save
      expect(controller.profile, isNull);
      expect(controller.status, ProfileStatus.ready);
      expect(store.local, isNull); // and the stray copy is wiped
    },
  );

  test(
    'an account with no profile and nothing on the phone simply has none',
    () async {
      final controller = await build();

      expect(controller.profile, isNull);
      expect(controller.status, ProfileStatus.ready);
      expect(api.calls, ['fetch']);
    },
  );

  test('offline: the phone copy is shown, and trying again works', () async {
    cognito = FakeCognito();
    tokens = MemoryAuthTokenStore(cognito.tokens('kim@example.com'));
    auth = AuthController(
      api: cognito,
      store: tokens,
      clock: () => DateTime.utc(2026, 1, 1, 0, 10),
    );
    api = _FakeProfileApi()..offline = true;
    store = MemoryProfileStore();
    await store.write(_kim, email: 'kim@example.com');
    final controller = ProfileController(api: api, store: store, auth: auth);
    await auth.restore();
    await _settle();
    await _settle();

    expect(controller.status, ProfileStatus.failed);
    expect(controller.profile?.name, 'Kim Lee');

    api.offline = false;
    await controller.sync();

    expect(controller.status, ProfileStatus.ready);
    expect(api.onServer?.name, 'Kim Lee');
  });

  test('nothing is asked of the server while signed out', () async {
    final controller = await build(signedIn: false);

    expect(api.calls, isEmpty);
    expect(controller.status, ProfileStatus.idle);
  });

  test('logging out wipes the profile from the phone', () async {
    final controller = await build();
    api.onServer = _server;
    await controller.sync();
    expect(store.local, isNotNull);

    await auth.signOut();
    await _settle();

    expect(controller.profile, isNull);
    expect(controller.status, ProfileStatus.idle);
    expect(store.local, isNull);
  });

  test(
    'the profile is looked up again after logging in as someone else',
    () async {
      final controller = await build();
      api.onServer = _server;
      await controller.sync();
      await auth.signOut();
      await _settle();
      api.calls.clear();
      api.onServer = null;

      await auth.beginLogIn('other@example.com');
      await auth.submitCode('12345678');
      await _settle();
      await _settle();

      expect(api.calls, ['fetch']);
      expect(controller.profile, isNull);
    },
  );

  testWidgets('the account sheet shows the name, level and favourite genres', (
    tester,
  ) async {
    final controller = await build();
    api.onServer = _kim;
    await controller.sync();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Center(
            child: AccountButton(auth: auth, profile: controller),
          ),
        ),
      ),
    );

    await tester.tap(find.byTooltip('Account'));
    await tester.pumpAndSettle();

    expect(find.text('Kim Lee'), findsOneWidget);
    expect(find.text('kim@example.com'), findsOneWidget);
    expect(find.text('Intermediate'), findsOneWidget);
    expect(find.text('Pop, Jazz'), findsOneWidget);
    expect(find.text('Try again'), findsNothing);
  });

  testWidgets(
    'when the profile cannot be loaded the sheet offers to try again',
    (tester) async {
      final controller = await build();
      api.offline = true;
      await controller.sync();
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Center(
              child: AccountButton(auth: auth, profile: controller),
            ),
          ),
        ),
      );

      await tester.tap(find.byTooltip('Account'));
      await tester.pumpAndSettle();
      expect(find.text('Try again'), findsOneWidget);

      api.offline = false;
      api.onServer = _kim;
      await tester.tap(find.text('Try again'));
      await tester.pumpAndSettle();

      expect(find.text('Kim Lee'), findsOneWidget);
      expect(find.text('Try again'), findsNothing);
    },
  );

  test('a profile survives a round trip through the phone storage format', () {
    final copy = LocalProfile.tryFromJson(
      jsonDecode(
        jsonEncode(
          LocalProfile(email: 'kim@example.com', profile: _kim).toJson(),
        ),
      ),
    );

    expect(copy?.email, 'kim@example.com');
    expect(copy?.profile.name, 'Kim Lee');
    expect(copy?.profile.birthYear, 2000);
    expect(copy?.profile.genres, ['Pop', 'Jazz']);
    expect(copy?.profile.experience, GuitarExperience.intermediate);
    for (final bad in [
      null,
      'x',
      <String, Object?>{},
      {'email': '', 'profile': _kim.toJson()},
      {
        'email': 'a@b.c',
        'profile': {'name': ''},
      },
    ]) {
      expect(LocalProfile.tryFromJson(bad), isNull);
    }
  });

  test('age is counted in whole years, and 13 is the youngest', () {
    final today = DateTime(2026, 10, 27);

    expect(UserProfile.ageOn(DateTime(2013, 10, 27), today), 13);
    expect(UserProfile.ageOn(DateTime(2013, 10, 28), today), 12);
    expect(UserProfile.youngestBirthDate(today), DateTime(2013, 10, 27));
  });
}

// --- the HTTP side ---

class _Adapter implements HttpClientAdapter {
  _Adapter(this.status, this.body);

  final int status;
  final Object? body;
  RequestOptions? last;
  DioExceptionType? failWith;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    last = options;
    if (failWith != null) {
      throw DioException(requestOptions: options, type: failWith!);
    }
    return ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

({DioProfileApi api, _Adapter adapter}) _http(
  int status,
  Object? body, {
  String? token = 'tok',
}) {
  final adapter = _Adapter(status, body);
  final dio = Dio(
    BaseOptions(
      baseUrl: 'https://api.example.com',
      validateStatus: (_) => true,
    ),
  )..httpClientAdapter = adapter;
  return (
    api: DioProfileApi(
      baseUrl: 'https://api.example.com',
      tokenProvider: () => token,
      dio: dio,
    ),
    adapter: adapter,
  );
}

const _serverJson = {
  'name': 'Kim Lee',
  'birth_year': 2000,
  'genres': ['Pop', 'Jazz'],
  'experience': 'intermediate',
  'updated_at': '2026-10-27T12:00:00+00:00',
};

void _registerHttpTests() {
  group('the profile over HTTP', () {
    test(
      'reading maps the server fields and sends the signed-in token',
      () async {
        final t = _http(200, _serverJson);

        final profile = await t.api.fetch();

        expect(profile?.name, 'Kim Lee');
        expect(profile?.birthYear, 2000);
        expect(profile?.genres, ['Pop', 'Jazz']);
        expect(profile?.experience, GuitarExperience.intermediate);
        expect(t.adapter.last?.method, 'GET');
        expect(t.adapter.last?.path, '/me/profile');
        expect(t.adapter.last?.headers['Authorization'], 'Bearer tok');
      },
    );

    test('no profile yet is null, not an error', () async {
      expect(
        await _http(404, {
          'error': {'code': 'profile_not_found'},
        }).api.fetch(),
        isNull,
      );
    });

    test('saving sends only the four profile fields', () async {
      final t = _http(200, _serverJson);

      final saved = await t.api.save(_kim);

      expect(saved.name, 'Kim Lee');
      expect(t.adapter.last?.method, 'PUT');
      expect(t.adapter.last?.data, {
        'name': 'Kim Lee',
        'birth_year': 2000,
        'genres': ['Pop', 'Jazz'],
        'experience': 'intermediate',
      });
    });

    test(
      'a failed request, an odd answer, or no token are all clear errors',
      () async {
        await expectLater(
          _http(500, {}).api.fetch(),
          throwsA(
            isA<ProfileApiException>().having(
              (e) => e.statusCode,
              'status',
              500,
            ),
          ),
        );
        await expectLater(
          _http(200, {'name': 'x'}).api.fetch(),
          throwsA(isA<ProfileApiException>()),
        );
        final noToken = _http(200, _serverJson, token: null);
        await expectLater(
          noToken.api.fetch(),
          throwsA(
            isA<ProfileApiException>().having(
              (e) => e.statusCode,
              'status',
              401,
            ),
          ),
        );
        expect(noToken.adapter.last, isNull); // nothing was sent
        final down = _http(200, _serverJson)
          ..adapter.failWith = DioExceptionType.connectionError;
        await expectLater(
          down.api.save(_kim),
          throwsA(isA<ProfileApiException>()),
        );
      },
    );
  });
}

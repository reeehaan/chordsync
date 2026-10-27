import 'dart:async';

import 'package:dio/dio.dart';

import 'user_profile.dart';

class ProfileApiException implements Exception {
  const ProfileApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => 'ProfileApiException($statusCode, $message)';
}

/// The signed-in person's profile on the server.
abstract interface class ProfileApi {
  /// The saved profile, or null when none has been saved yet.
  Future<UserProfile?> fetch();

  /// Saves the profile and returns what the server kept.
  Future<UserProfile> save(UserProfile profile);
}

class DioProfileApi implements ProfileApi {
  DioProfileApi({
    required String baseUrl,
    required this._tokenProvider,
    Dio? dio,
  }) : _dio =
           dio ??
           Dio(
             BaseOptions(
               baseUrl: baseUrl,
               connectTimeout: const Duration(seconds: 15),
               receiveTimeout: const Duration(seconds: 20),
               validateStatus: (_) => true,
             ),
           );

  final Dio _dio;
  final FutureOr<String?> Function() _tokenProvider;

  @override
  Future<UserProfile?> fetch() async {
    final response = await _send('GET');
    if (response.statusCode == 404) return null;
    return _parse(response);
  }

  @override
  Future<UserProfile> save(UserProfile profile) async {
    final response = await _send(
      'PUT',
      body: {
        'name': profile.name,
        'birth_year': profile.birthYear,
        'genres': profile.genres,
        'experience': profile.experience.name,
      },
    );
    return _parse(response);
  }

  Future<Response<Object?>> _send(String method, {Object? body}) async {
    final token = (await _tokenProvider())?.trim();
    if (token == null || token.isEmpty) {
      throw const ProfileApiException('Not signed in.', statusCode: 401);
    }
    try {
      return await _dio.request<Object?>(
        '/me/profile',
        data: body,
        options: Options(
          method: method,
          headers: {'Authorization': 'Bearer $token'},
        ),
      );
    } on DioException catch (error) {
      throw ProfileApiException(
        'Could not reach ChordSync (${error.type.name}).',
      );
    }
  }

  UserProfile _parse(Response<Object?> response) {
    final status = response.statusCode ?? 0;
    if (status < 200 || status >= 300) {
      throw ProfileApiException(
        'The profile request failed.',
        statusCode: status,
      );
    }
    final profile = UserProfile.tryFromJson(_fromServer(response.data));
    if (profile == null) {
      throw const ProfileApiException(
        'The profile response was not understood.',
      );
    }
    return profile;
  }

  /// The server says `birth_year`; the app's own copy says `birthYear`.
  static Object? _fromServer(Object? data) {
    if (data is! Map) return null;
    return {
      'name': data['name'],
      'birthYear': data['birth_year'],
      'genres': data['genres'],
      'experience': data['experience'],
    };
  }
}

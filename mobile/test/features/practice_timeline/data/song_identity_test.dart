import 'package:chordsync/features/practice_timeline/data/song_identity.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('reads title and artist and drops the download site', () {
    final identity = SongIdentity.fromFileName(
      'Lemon - Kenshi Yonezu - Spotimate.app',
    );
    expect(identity.title, 'Lemon');
    expect(identity.artist, 'Kenshi Yonezu');
  });

  test('drops an audio extension', () {
    final identity = SongIdentity.fromFileName('Lemon - Kenshi Yonezu.mp3');
    expect(identity.title, 'Lemon');
    expect(identity.artist, 'Kenshi Yonezu');
  });

  test('a name with no artist stays whole', () {
    final identity = SongIdentity.fromFileName('safe_song');
    expect(identity.title, 'safe_song');
    expect(identity.artist, isNull);
  });

  test('leaves a real title alone that looks like a site name', () {
    final identity = SongIdentity.fromFileName('Youtube - Some Artist');
    expect(identity.title, 'Youtube');
    expect(identity.artist, 'Some Artist');
  });

  test('drops a download site from the middle of the name', () {
    final identity = SongIdentity.fromFileName(
      'Lemon - Spotimate.app - Kenshi',
    );
    expect(identity.title, 'Lemon');
    expect(identity.artist, 'Kenshi');
  });
}

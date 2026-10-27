/// How much guitar the person has played, in their own words.
enum GuitarExperience {
  beginner('Complete beginner', 'Just got my first guitar'),
  little('A little experience', 'Know some chords / basic songs'),
  intermediate('Intermediate', 'Can play a few songs'),
  advanced('Advanced', 'Comfortable with most techniques');

  const GuitarExperience(this.title, this.subtitle);

  final String title;
  final String subtitle;
}

/// What the person tells us when they create an account. It shapes which songs
/// are suggested, and nothing else.
class UserProfile {
  const UserProfile({
    required this.name,
    required this.birthDate,
    required this.genres,
    required this.experience,
  });

  /// The youngest age that can create an account.
  static const minimumAge = 13;

  final String name;
  final DateTime birthDate;
  final List<String> genres;
  final GuitarExperience experience;

  /// Whole years old on [today].
  static int ageOn(DateTime birthDate, DateTime today) {
    var years = today.year - birthDate.year;
    final hadBirthday =
        today.month > birthDate.month ||
        (today.month == birthDate.month && today.day >= birthDate.day);
    if (!hadBirthday) years -= 1;
    return years;
  }

  /// The latest birth date that is old enough on [today].
  static DateTime youngestBirthDate(DateTime today) =>
      DateTime(today.year - minimumAge, today.month, today.day);

  Map<String, Object?> toJson() => {
    'name': name,
    'birthDate': _date(birthDate),
    'genres': genres,
    'experience': experience.name,
  };

  static UserProfile? tryFromJson(Object? value) {
    if (value is! Map) return null;
    final name = value['name'];
    final birth = DateTime.tryParse('${value['birthDate']}');
    final genres = value['genres'];
    final experience = GuitarExperience.values
        .where((e) => e.name == value['experience'])
        .firstOrNull;
    if (name is! String ||
        name.trim().isEmpty ||
        birth == null ||
        genres is! List ||
        experience == null) {
      return null;
    }
    return UserProfile(
      name: name,
      birthDate: birth,
      genres: [
        for (final genre in genres)
          if (genre is String) genre,
      ],
      experience: experience,
    );
  }

  static String _date(DateTime date) =>
      '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-'
      '${date.day.toString().padLeft(2, '0')}';
}

/// The music styles to choose from. Plain labels, so they can be matched to
/// songs later.
const musicGenres = [
  'Rock',
  'Pop',
  'Indie',
  'Jazz',
  'Hip-Hop',
  'Classical',
  'Country',
  'Folk',
  'Blues',
  'R&B',
  'Metal',
  'Other',
];

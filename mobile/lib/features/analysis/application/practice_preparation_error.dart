enum PracticePreparationErrorCode {
  localAudioUnavailable,
  timelineIncompatible,
  initializationFailed,
}

class PracticePreparationException implements Exception {
  const PracticePreparationException(this.code, this.message);

  final PracticePreparationErrorCode code;
  final String message;

  @override
  String toString() => 'PracticePreparationException: $message';
}

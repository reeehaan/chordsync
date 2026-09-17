import 'dart:io';

import 'package:file_selector/file_selector.dart';

abstract interface class AudioFileSelector {
  Future<File?> chooseAudio();
}

class NativeAudioFileSelector implements AudioFileSelector {
  const NativeAudioFileSelector();

  static const _audioTypes = XTypeGroup(
    label: 'Audio',
    extensions: ['wav', 'mp3', 'm4a'],
    uniformTypeIdentifiers: [
      'com.microsoft.waveform-audio',
      'public.mp3',
      'public.mpeg-4-audio',
    ],
  );

  @override
  Future<File?> chooseAudio() async {
    final selected = await openFile(
      acceptedTypeGroups: const [_audioTypes],
      confirmButtonText: 'Choose Audio',
    );
    if (selected == null) return null;
    return File(selected.path);
  }
}

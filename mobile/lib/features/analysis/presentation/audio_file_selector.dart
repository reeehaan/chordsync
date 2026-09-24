import 'dart:io';
import 'dart:math';

import 'package:file_selector/file_selector.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

abstract interface class AudioFileSelector {
  Future<SelectedAudioFile?> chooseAudio();
}

/// The durable file used for upload/playback and its human-readable source name.
class SelectedAudioFile {
  const SelectedAudioFile({required this.file, required this.displayName});

  final File file;
  final String displayName;
}

typedef AudioFilePicker = Future<File?> Function();
typedef DocumentsDirectoryProvider = Future<Directory> Function();
typedef AudioFileCopier =
    Future<File> Function(File source, String destination);

/// A safe, path-free error for a file that could not be imported.
class AudioFileSelectionException implements Exception {
  const AudioFileSelectionException();

  @override
  String toString() => 'Could not import that audio file. Please try again.';
}

Future<File?> _pickNativeAudio() async {
  final selected = await openFile(
    acceptedTypeGroups: const [NativeAudioFileSelector.audioTypes],
    confirmButtonText: 'Choose Audio',
  );
  return selected == null ? null : File(selected.path);
}

Future<File> _copyAudioFile(File source, String destination) =>
    source.copy(destination);

/// Picks an audio file and copies it out of the OS document picker's
/// temporary hand-off location into storage this app owns.
///
/// The picker (`file_selector`) may return a path into a transient location
/// such as iOS's picker Inbox, which the OS can reclaim shortly after the
/// pick completes. Downstream code (upload, then later local playback on
/// the Practice screen) needs the file to still exist minutes later, so it
/// must not hold onto that ephemeral path.
class NativeAudioFileSelector implements AudioFileSelector {
  const NativeAudioFileSelector({
    this.pickFile = _pickNativeAudio,
    this.documentsDirectory = getApplicationDocumentsDirectory,
    this.copyFile = _copyAudioFile,
  });

  final AudioFilePicker pickFile;
  final DocumentsDirectoryProvider documentsDirectory;
  final AudioFileCopier copyFile;

  static const audioTypes = XTypeGroup(
    label: 'Audio',
    extensions: ['wav', 'mp3', 'm4a'],
    uniformTypeIdentifiers: [
      'com.microsoft.waveform-audio',
      'public.mp3',
      'public.mpeg-4-audio',
    ],
  );

  @override
  Future<SelectedAudioFile?> chooseAudio() async {
    try {
      final selected = await pickFile();
      if (selected == null) return null;
      final imported = await _persist(selected);
      return SelectedAudioFile(
        file: imported,
        displayName: p.basename(selected.path),
      );
    } on Object {
      throw const AudioFileSelectionException();
    }
  }

  Future<File> _persist(File source) async {
    final extension = p.extension(source.path).toLowerCase();
    if (!const {'.wav', '.mp3', '.m4a'}.contains(extension)) {
      throw const AudioFileSelectionException();
    }

    File? temporary;
    File? destination;
    var finalCreated = false;
    try {
      final importsDir = Directory(
        p.join((await documentsDirectory()).path, 'imported_audio'),
      );
      await importsDir.create(recursive: true);

      // Files that this selector already imported do not need another copy.
      final sourcePath = await source.resolveSymbolicLinks();
      final importsPath = await importsDir.resolveSymbolicLinks();
      if (p.dirname(sourcePath) == importsPath &&
          RegExp(
            r'^[0-9a-f]{32}\.(wav|mp3|m4a)$',
          ).hasMatch(p.basename(sourcePath)) &&
          await source.length() > 0) {
        return source;
      }

      final random = Random.secure();
      String name;
      do {
        name = List<int>.generate(
          16,
          (_) => random.nextInt(256),
        ).map((byte) => byte.toRadixString(16).padLeft(2, '0')).join();
        destination = File(p.join(importsDir.path, '$name$extension'));
      } while (await destination.exists());

      temporary = File('${destination.path}.partial');
      final copied = await copyFile(source, temporary.path);
      if (!await copied.exists() || await copied.length() == 0) {
        throw const AudioFileSelectionException();
      }
      final imported = await copied.rename(destination.path);
      finalCreated = true;
      if (!await imported.exists() || await imported.length() == 0) {
        throw const AudioFileSelectionException();
      }
      return imported;
    } on Object {
      await _discard(temporary);
      if (finalCreated) await _discard(destination);
      throw const AudioFileSelectionException();
    }
  }

  Future<void> _discard(File? file) async {
    if (file == null) return;
    try {
      if (await file.exists()) await file.delete();
    } on FileSystemException {
      // Keep the original safe import error; orphan cleanup is best-effort.
    }
  }
}

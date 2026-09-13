import 'package:flutter/material.dart';

import 'features/practice_timeline/application/practice_audio_player.dart';
import 'features/practice_timeline/presentation/practice_screen.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key, this.audioPlayer});

  final PracticeAudioPlayer? audioPlayer;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ChordSync',
      theme: ThemeData(colorScheme: .fromSeed(seedColor: Colors.deepPurple)),
      home: PracticeScreen(audioPlayer: audioPlayer),
    );
  }
}

import 'package:chordsync/features/practice_timeline/presentation/chord_diagram.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _roots = [
  'C',
  'C#',
  'D',
  'D#',
  'E',
  'F',
  'F#',
  'G',
  'G#',
  'A',
  'A#',
  'B',
];
// Open strings, low E to high e, as pitch classes (C = 0).
const _openStrings = [4, 9, 2, 7, 11, 4];

/// The notes (in semitones above the root) a chord may contain, and the ones
/// besides the root it must contain to be that chord at all.
const _chordTypes = {
  '7': (allowed: {0, 4, 7, 10}, needed: {4, 10}),
  'maj7': (allowed: {0, 4, 7, 11}, needed: {4, 11}),
  'm7': (allowed: {0, 3, 7, 10}, needed: {3, 10}),
  'sus2': (allowed: {0, 2, 7}, needed: {2}),
  'sus4': (allowed: {0, 5, 7}, needed: {5}),
};

void main() {
  test('every root has a shape for every beginner chord type', () {
    for (final root in _roots) {
      for (final type in _chordTypes.keys) {
        expect(
          ChordDiagram.fretsFor('$root$type'),
          isNotNull,
          reason: '$root$type has no shape',
        );
      }
    }
  });

  test('each shape sounds exactly the notes of its chord', () {
    for (var rootIndex = 0; rootIndex < 12; rootIndex++) {
      for (final entry in _chordTypes.entries) {
        final name = '${_roots[rootIndex]}${entry.key}';
        final frets = ChordDiagram.fretsFor(name)!;
        expect(frets, hasLength(6), reason: name);

        final notes = {
          for (var string = 0; string < 6; string++)
            if (frets[string] >= 0)
              (_openStrings[string] + frets[string] - rootIndex) % 12,
        };
        expect(
          entry.value.allowed.containsAll(notes),
          isTrue,
          reason: '$name sounds a note that is not in the chord: $notes',
        );
        expect(notes.contains(0), isTrue, reason: '$name has no root');
        expect(
          notes.containsAll(entry.value.needed),
          isTrue,
          reason: '$name is missing the note that defines it: $notes',
        );
      }
    }
  });

  test('shapes stay on frets 0 to 10 and fit one hand position', () {
    for (final root in _roots) {
      for (final type in _chordTypes.keys) {
        final frets = ChordDiagram.fretsFor('$root$type')!;
        final pressed = frets.where((fret) => fret > 0).toList();
        if (pressed.isEmpty) continue;
        final highest = pressed.reduce((a, b) => a > b ? a : b);
        final lowest = pressed.reduce((a, b) => a < b ? a : b);
        expect(highest, lessThanOrEqualTo(10), reason: '$root$type');
        expect(highest - lowest, lessThanOrEqualTo(3), reason: '$root$type');
        // At least three strings ring, so it sounds like a chord.
        expect(
          frets.where((fret) => fret >= 0).length,
          greaterThanOrEqualTo(4),
        );
      }
    }
  });

  testWidgets('a chord diagram is drawn for each of them, never just a name', (
    tester,
  ) async {
    for (final root in _roots) {
      for (final type in _chordTypes.keys) {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(body: ChordDiagram(chord: '$root$type')),
          ),
        );
        expect(
          find.byKey(const ValueKey('chordDiagram')),
          findsOneWidget,
          reason: '$root$type',
        );
        expect(
          find.byKey(const ValueKey('unknownChordFallback')),
          findsNothing,
        );
      }
    }
  });

  test('the plain major and minor chords are unchanged', () {
    expect(ChordDiagram.fretsFor('C'), [-1, 3, 2, 0, 1, 0]);
    expect(ChordDiagram.fretsFor('Em'), [0, 2, 2, 0, 0, 0]);
    expect(ChordDiagram.fretsFor('F#m'), [2, 4, 4, 2, 2, 2]);
  });
}

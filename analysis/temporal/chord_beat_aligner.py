from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.temporal.models import TimelineEvent


def chord_at_time(
    time: float,
    chords: list[ChordSegment],
) -> ChordSegment | None:
    for chord in chords:
        if chord.start <= time < chord.end:
            return chord

    return None


def align_chords_to_beats(
    beats: list[BeatEvent],
    chords: list[ChordSegment],
) -> list[TimelineEvent]:
    aligned = []

    for beat in beats:
        chord = chord_at_time(
            beat.time,
            chords,
        )

        aligned.append(
            TimelineEvent(
                time=beat.time,
                beat_number=beat.beat_number,
                is_downbeat=beat.is_downbeat,
                chord=(
                    chord.normalized_label
                    if chord is not None
                    else "N"
                ),
            )
        )

    return aligned

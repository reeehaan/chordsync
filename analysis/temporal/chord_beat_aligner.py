from analysis.beats.models import BeatEvent
from analysis.chords.models import ChordSegment
from analysis.temporal.models import TimelineEvent

_MAX_BEAT_SNAP_SECONDS = 0.2


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
    snapped_chords = _snap_chords_to_beats(chords, beats)
    aligned = []

    for beat in beats:
        chord = chord_at_time(
            beat.time,
            snapped_chords,
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


def _snap_chords_to_beats(
    chords: list[ChordSegment],
    beats: list[BeatEvent],
) -> list[ChordSegment]:
    """Moves each chord's onset to whichever beat is closest to it.

    The estimator's own segment boundaries carry frame-level uncertainty, and
    a chord change almost always musically lands on a beat. Snapping each
    onset to the nearest beat (rather than only ever waiting for the next
    beat at or after it) keeps a chord that was detected slightly early or
    slightly late from being displayed a full beat later than it should be.
    """
    if not beats or not chords:
        return chords

    beat_times = [beat.time for beat in beats]
    original_starts = [chord.start for chord in chords]
    snapped_starts = [original_starts[0]]
    for index in range(1, len(chords)):
        original = original_starts[index]
        candidate = _nearest_time(original, beat_times)
        next_boundary = (
            original_starts[index + 1]
            if index + 1 < len(chords)
            else chords[index].end
        )
        can_snap = (
            abs(candidate - original) <= _MAX_BEAT_SNAP_SECONDS
            and snapped_starts[-1] < candidate < next_boundary
        )
        snapped_starts.append(candidate if can_snap else original)

    snapped = []
    for index, chord in enumerate(chords):
        next_start = index + 1
        end = (
            snapped_starts[next_start]
            if next_start < len(snapped_starts)
            else chord.end
        )
        snapped.append(
            chord.model_copy(
                update={"start": snapped_starts[index], "end": end}
            )
        )

    return snapped


def _nearest_time(time: float, candidates: list[float]) -> float:
    return min(candidates, key=lambda candidate: abs(candidate - time))

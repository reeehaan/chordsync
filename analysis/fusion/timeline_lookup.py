from analysis.fusion.models import SharedTimeline
from analysis.lyrics.models import LyricWord
from analysis.temporal.models import TimelineEvent


def get_current_beat(
    timeline: SharedTimeline,
    time: float,
) -> TimelineEvent | None:
    current_beat = None

    for bar in timeline.bars:
        for beat in bar.beats:
            if beat.time <= time:
                current_beat = beat
            else:
                return current_beat

    return current_beat


def get_current_lyric_word(
    timeline: SharedTimeline,
    time: float,
) -> LyricWord | None:
    for segment in timeline.lyrics:
        for word in segment.words:
            if word.start <= time < word.end:
                return word

    return None


def get_playback_state(
    timeline: SharedTimeline,
    time: float,
) -> dict:
    beat = get_current_beat(
        timeline,
        time,
    )

    word = get_current_lyric_word(
        timeline,
        time,
    )

    return {
        "time": time,
        "chord": (
            beat.chord
            if beat is not None
            else "N"
        ),
        "beat_number": (
            beat.beat_number
            if beat is not None
            else None
        ),
        "is_downbeat": (
            beat.is_downbeat
            if beat is not None
            else False
        ),
        "lyric_word": (
            word.text
            if word is not None
            else None
        ),
    }

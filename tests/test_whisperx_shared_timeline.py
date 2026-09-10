from analysis.fusion.models import SharedTimeline
from analysis.fusion.timeline_lookup import get_playback_state


def create_synthetic_timeline() -> SharedTimeline:
    return SharedTimeline.model_validate({
        "schema_version": 1,
        "bpm": 120.0,
        "beats_per_bar": 4,
        "beat_source": "synthetic-beats",
        "lyric_source": "synthetic-whisperx",
        "bars": [
            {
                "bar_number": 1,
                "start_time": 0.0,
                "end_time": 2.0,
                "beats": [
                    {
                        "time": 0.0,
                        "beat_number": 1,
                        "is_downbeat": True,
                        "chord": "C",
                    },
                    {
                        "time": 0.5,
                        "beat_number": 2,
                        "is_downbeat": False,
                        "chord": "G",
                    },
                ],
            }
        ],
        "lyrics": [
            {
                "start": 0.1,
                "end": 1.5,
                "text": "Count ready",
                "words": [
                    {
                        "start": 0.1,
                        "end": 0.4,
                        "text": "Count",
                    },
                    {
                        "start": 1.0,
                        "end": 1.5,
                        "text": "ready",
                    },
                ],
            }
        ],
    })


def test_synthetic_whisperx_shared_timeline_creation() -> None:
    timeline = create_synthetic_timeline()

    assert timeline.schema_version == 1
    assert timeline.lyric_source == "synthetic-whisperx"
    assert len(timeline.bars) == 1
    assert len(timeline.bars[0].beats) == 2
    assert len(timeline.lyrics[0].words) == 2


def test_synthetic_whisperx_playback_lookup() -> None:
    state = get_playback_state(
        create_synthetic_timeline(),
        0.2,
    )

    assert state["chord"] == "C"
    assert state["beat_number"] == 1
    assert state["is_downbeat"] is True
    assert state["lyric_word"] == "Count"


def test_synthetic_whisperx_gap_returns_none() -> None:
    state = get_playback_state(
        create_synthetic_timeline(),
        0.75,
    )

    assert state["chord"] == "G"
    assert state["lyric_word"] is None

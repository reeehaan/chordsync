import json
from pathlib import Path

from analysis.beats.models import (
    BeatEvent,
    BeatGrid,
)
from analysis.fusion.timeline_exporter import (
    export_shared_timeline,
)
from analysis.fusion.timeline_fusion import (
    build_shared_timeline,
)
from analysis.fusion.timeline_lookup import (
    get_current_beat,
    get_current_lyric_word,
    get_playback_state,
)
from analysis.lyrics.models import (
    LyricSegment,
    LyricTranscript,
    LyricWord,
)
from analysis.temporal.models import (
    Bar,
    TimelineEvent,
)


def test_build_shared_timeline():
    beat_grid = BeatGrid(
        bpm=70.0,
        beats_per_bar=4,
        beats=[
            BeatEvent(
                time=0.0,
                beat_number=1,
                is_downbeat=True,
                source="test",
            )
        ],
        source="test",
    )

    bars = [
        Bar(
            bar_number=1,
            start_time=0.0,
            end_time=4.0,
            beats=[
                TimelineEvent(
                    time=0.0,
                    beat_number=1,
                    is_downbeat=True,
                    chord="C",
                ),
                TimelineEvent(
                    time=1.0,
                    beat_number=2,
                    is_downbeat=False,
                    chord="C",
                ),
            ],
        )
    ]

    lyrics = LyricTranscript(
        language="en",
        source="test-whisper",
        segments=[
            LyricSegment(
                start=0.5,
                end=2.0,
                text="Hello world",
                words=[
                    LyricWord(
                        start=0.5,
                        end=1.0,
                        text="Hello",
                    ),
                    LyricWord(
                        start=1.0,
                        end=1.5,
                        text="world",
                    ),
                ],
            )
        ],
    )

    timeline = build_shared_timeline(
        beat_grid,
        bars,
        lyrics,
    )

    assert timeline.schema_version == 1
    assert timeline.bpm == 70.0
    assert timeline.beats_per_bar == 4
    assert timeline.beat_source == "test"
    assert timeline.lyric_source == "test-whisper"

    assert len(timeline.bars) == 1
    assert len(timeline.lyrics) == 1

    assert timeline.bars[0].beats[0].chord == "C"
    assert timeline.lyrics[0].words[0].text == "Hello"


def test_export_shared_timeline(tmp_path: Path):
    beat_grid = BeatGrid(
        bpm=70.0,
        beats_per_bar=4,
        beats=[],
        source="test",
    )

    bars = []

    lyrics = LyricTranscript(
        language="en",
        source="test-whisper",
        segments=[],
    )

    timeline = build_shared_timeline(
        beat_grid,
        bars,
        lyrics,
    )

    output_path = (
        tmp_path
        / "shared_timeline.json"
    )

    export_shared_timeline(
        timeline,
        output_path,
    )

    assert output_path.exists()

    data = json.loads(
        output_path.read_text(
            encoding="utf-8",
        )
    )

    assert data["schema_version"] == 1
    assert data["bpm"] == 70.0
    assert data["beats_per_bar"] == 4
    assert data["beat_source"] == "test"
    assert data["lyric_source"] == "test-whisper"
    assert data["bars"] == []
    assert data["lyrics"] == []


def create_test_timeline():
    beat_grid = BeatGrid(
        bpm=60.0,
        beats_per_bar=4,
        beats=[
            BeatEvent(
                time=0.0,
                beat_number=1,
                is_downbeat=True,
                source="test",
            ),
            BeatEvent(
                time=1.0,
                beat_number=2,
                is_downbeat=False,
                source="test",
            ),
        ],
        source="test",
    )

    bars = [
        Bar(
            bar_number=1,
            start_time=0.0,
            end_time=2.0,
            beats=[
                TimelineEvent(
                    time=0.0,
                    beat_number=1,
                    is_downbeat=True,
                    chord="C",
                ),
                TimelineEvent(
                    time=1.0,
                    beat_number=2,
                    is_downbeat=False,
                    chord="G",
                ),
            ],
        )
    ]

    lyrics = LyricTranscript(
        language="en",
        source="test-whisper",
        segments=[
            LyricSegment(
                start=0.5,
                end=2.0,
                text="Hello world",
                words=[
                    LyricWord(
                        start=0.5,
                        end=1.0,
                        text="Hello",
                    ),
                    LyricWord(
                        start=1.0,
                        end=1.5,
                        text="world",
                    ),
                ],
            )
        ],
    )

    return build_shared_timeline(
        beat_grid,
        bars,
        lyrics,
    )


def test_get_current_beat():
    timeline = create_test_timeline()

    beat = get_current_beat(
        timeline,
        1.2,
    )

    assert beat is not None
    assert beat.chord == "G"
    assert beat.beat_number == 2


def test_get_current_lyric_word():
    timeline = create_test_timeline()

    word = get_current_lyric_word(
        timeline,
        0.7,
    )

    assert word is not None
    assert word.text == "Hello"


def test_get_playback_state():
    timeline = create_test_timeline()

    state = get_playback_state(
        timeline,
        1.2,
    )

    assert state["time"] == 1.2
    assert state["chord"] == "G"
    assert state["beat_number"] == 2
    assert state["is_downbeat"] is False
    assert state["lyric_word"] == "world"

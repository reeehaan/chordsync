import json
from pathlib import Path

from analysis.lyrics.lyric_exporter import (
    export_lyrics_json,
)
from analysis.lyrics.lyric_parser import (
    whisper_result_to_transcript,
)


def test_whisper_result_to_transcript():
    result = {
        "language": "en",
        "segments": [
            {
                "start": 1.0,
                "end": 3.0,
                "text": " Hello world",
                "words": [
                    {
                        "start": 1.0,
                        "end": 1.5,
                        "word": " Hello",
                    },
                    {
                        "start": 1.5,
                        "end": 2.0,
                        "word": " world",
                    },
                ],
            }
        ],
    }

    transcript = whisper_result_to_transcript(
        result,
        source="whisper-base",
    )

    assert transcript.language == "en"
    assert transcript.source == "whisper-base"

    assert len(transcript.segments) == 1

    segment = transcript.segments[0]

    assert segment.start == 1.0
    assert segment.end == 3.0
    assert segment.text == "Hello world"

    assert len(segment.words) == 2

    assert segment.words[0].text == "Hello"
    assert segment.words[0].start == 1.0
    assert segment.words[0].end == 1.5

    assert segment.words[1].text == "world"


def test_whisper_result_handles_empty_words():
    result = {
        "language": "en",
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": " Instrumental",
                "words": [],
            }
        ],
    }

    transcript = whisper_result_to_transcript(
        result,
        source="test",
    )

    assert len(transcript.segments) == 1
    assert transcript.segments[0].words == []


def test_export_lyrics_json(tmp_path: Path):
    result = {
        "language": "en",
        "segments": [
            {
                "start": 1.0,
                "end": 2.0,
                "text": " Hello",
                "words": [
                    {
                        "start": 1.0,
                        "end": 1.5,
                        "word": " Hello",
                    }
                ],
            }
        ],
    }

    transcript = whisper_result_to_transcript(
        result,
        source="whisper-base",
    )

    output_path = tmp_path / "lyrics.json"

    export_lyrics_json(
        transcript,
        output_path,
    )

    assert output_path.exists()

    data = json.loads(
        output_path.read_text(
            encoding="utf-8",
        )
    )

    assert data["language"] == "en"
    assert data["source"] == "whisper-base"

    assert len(data["segments"]) == 1

    first_segment = data["segments"][0]

    assert first_segment["text"] == "Hello"

    first_word = first_segment["words"][0]

    assert first_word["text"] == "Hello"
    assert first_word["start"] == 1.0
    assert first_word["end"] == 1.5

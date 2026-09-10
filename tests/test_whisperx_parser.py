from analysis.lyrics.whisperx_parser import (
    parse_whisperx_result,
)


def test_parse_whisperx_result():
    raw_result = {
        "language": "en",
        "segments": [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "Hello world",
                "words": [
                    {
                        "word": "Hello",
                        "start": 1.0,
                        "end": 1.4,
                        "score": 0.95,
                    },
                    {
                        "word": "world",
                        "start": 1.5,
                        "end": 2.0,
                        "score": 0.91,
                    },
                ],
            }
        ],
    }

    transcript = parse_whisperx_result(
        raw_result
    )

    assert transcript.language == "en"
    assert transcript.source == "whisperx-base"

    assert len(transcript.segments) == 1

    segment = transcript.segments[0]

    assert segment.start == 1.0
    assert segment.end == 2.0
    assert segment.text == "Hello world"

    assert len(segment.words) == 2

    assert segment.words[0].text == "Hello"
    assert segment.words[0].start == 1.0
    assert segment.words[0].end == 1.4

    assert segment.words[1].text == "world"
    assert segment.words[1].start == 1.5
    assert segment.words[1].end == 2.0

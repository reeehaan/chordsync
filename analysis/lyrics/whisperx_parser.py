from analysis.lyrics.models import (
    LyricSegment,
    LyricTranscript,
    LyricWord,
)


def parse_whisperx_result(
    result: dict,
    source: str = "whisperx-base",
) -> LyricTranscript:
    language = result.get("language", "unknown")

    segments: list[LyricSegment] = []

    for raw_segment in result.get("segments", []):
        words: list[LyricWord] = []

        for raw_word in raw_segment.get("words", []):
            if (
                "start" not in raw_word
                or "end" not in raw_word
            ):
                continue

            text = str(
                raw_word.get("word", "")
            ).strip()

            if not text:
                continue

            words.append(
                LyricWord(
                    start=float(
                        raw_word["start"]
                    ),
                    end=float(
                        raw_word["end"]
                    ),
                    text=text,
                )
            )

        if not words:
            continue

        segment_text = str(
            raw_segment.get("text", "")
        ).strip()

        segment_start = float(
            raw_segment.get(
                "start",
                words[0].start,
            )
        )

        segment_end = float(
            raw_segment.get(
                "end",
                words[-1].end,
            )
        )

        segments.append(
            LyricSegment(
                start=segment_start,
                end=segment_end,
                text=segment_text,
                words=words,
            )
        )

    return LyricTranscript(
        language=language,
        segments=segments,
        source=source,
    )

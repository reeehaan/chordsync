from analysis.lyrics.models import (
    LyricSegment,
    LyricTranscript,
    LyricWord,
)


def whisper_result_to_transcript(
    result: dict,
    source: str = "whisper-base",
) -> LyricTranscript:
    segments = []

    for segment in result.get("segments", []):
        words = []

        for word in segment.get("words", []):
            words.append(
                LyricWord(
                    start=float(word["start"]),
                    end=float(word["end"]),
                    text=word["word"].strip(),
                )
            )

        segments.append(
            LyricSegment(
                start=float(segment["start"]),
                end=float(segment["end"]),
                text=segment["text"].strip(),
                words=words,
            )
        )

    return LyricTranscript(
        language=result.get("language", "unknown"),
        segments=segments,
        source=source,
    )

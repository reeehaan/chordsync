from __future__ import annotations

import pytest

from analysis.lyrics.mms_alignment import (
    MINIMUM_WORD_SECONDS,
    refine_transcript,
    romanize_word,
)


def _transcript(*lines: tuple[float, float, list[str]]) -> dict:
    segments = []
    for start, end, words in lines:
        step = (end - start) / len(words)
        segments.append(
            {
                "start": start,
                "end": end,
                "text": " " + " ".join(words),
                "words": [
                    {"word": w, "start": start + i * step, "end": start + (i + 1) * step}
                    for i, w in enumerate(words)
                ],
            }
        )
    return {
        "segments": segments,
        "word_segments": [w for s in segments for w in s["words"]],
        "language": "synced",
    }


def _starts(transcript: dict, segment: int = 0) -> list[float]:
    return [w["start"] for w in transcript["segments"][segment]["words"]]


def test_aligned_times_replace_the_estimate():
    transcript = _transcript((10.0, 14.0, ["one", "two", "three"]))

    def align(start, end, words):
        return [(10.4, 10.9), (11.5, 12.0), (13.0, 13.8)]

    report = refine_transcript(transcript, align, total_seconds=60.0)

    assert (report.aligned_segments, report.failed_segments) == (1, 0)
    assert _starts(transcript) == [10.4, 11.5, 13.0]
    segment = transcript["segments"][0]
    assert (segment["start"], segment["end"]) == (10.4, 13.8)
    assert transcript["word_segments"] == segment["words"]


def test_each_line_is_aligned_in_a_window_around_its_synced_time():
    transcript = _transcript((10.0, 14.0, ["a", "b"]), (20.0, 24.0, ["c", "d"]))
    windows = []

    def align(start, end, words):
        windows.append((start, end, words))
        return None

    refine_transcript(transcript, align, total_seconds=22.0, pad_seconds=1.0)

    assert windows == [(9.0, 15.0, ["a", "b"]), (19.0, 22.0, ["c", "d"])]


def test_a_failing_line_keeps_its_estimate_and_others_still_align():
    transcript = _transcript((10.0, 12.0, ["a", "b"]), (20.0, 22.0, ["c", "d"]))
    original = _starts(transcript)

    def align(start, end, words):
        if words == ["a", "b"]:
            raise RuntimeError("alignment blew up")
        return [(20.2, 20.8), (21.0, 21.6)]

    report = refine_transcript(transcript, align, total_seconds=60.0)

    assert (report.aligned_segments, report.failed_segments) == (1, 1)
    assert _starts(transcript, 0) == original
    assert _starts(transcript, 1) == [20.2, 21.0]


@pytest.mark.parametrize(
    "answer",
    [None, [], [None, None], [(1.0, 2.0)]],  # none, empty, nothing aligned, wrong count
)
def test_unusable_answers_keep_the_estimate(answer):
    transcript = _transcript((10.0, 12.0, ["a", "b"]))
    original = _starts(transcript)

    report = refine_transcript(transcript, lambda *_: answer, total_seconds=60.0)

    assert report.failed_segments == 1
    assert _starts(transcript) == original


def test_words_that_could_not_be_aligned_fill_the_gap_between_neighbours():
    transcript = _transcript((10.0, 16.0, ["a", "...", "...", "d"]))

    def align(start, end, words):
        return [(10.0, 11.0), None, None, (14.0, 15.0)]

    refine_transcript(transcript, align, total_seconds=60.0)

    words = transcript["segments"][0]["words"]
    assert (words[0]["start"], words[3]["end"]) == (10.0, 15.0)
    assert 11.0 <= words[1]["start"] < words[1]["end"] <= words[2]["start"]
    assert words[2]["end"] <= 14.0


def test_overlapping_or_backwards_times_are_made_ordered():
    transcript = _transcript((10.0, 14.0, ["a", "b", "c"]))

    def align(start, end, words):
        return [(10.5, 11.5), (11.0, 11.2), (10.9, 10.95)]  # messy model output

    refine_transcript(transcript, align, total_seconds=60.0)

    words = transcript["segments"][0]["words"]
    for earlier, later in zip(words, words[1:]):
        assert earlier["end"] <= later["start"] + 1e-9
    assert all(w["end"] - w["start"] >= MINIMUM_WORD_SECONDS - 1e-9 for w in words)


def test_a_line_never_starts_before_the_previous_one_ended():
    transcript = _transcript((10.0, 14.0, ["a", "b"]), (14.5, 18.0, ["c", "d"]))

    def align(start, end, words):
        if words == ["a", "b"]:
            return [(10.5, 12.0), (12.5, 15.0)]  # spills into the next line
        return [(14.6, 15.4), (16.0, 17.0)]

    refine_transcript(transcript, align, total_seconds=60.0)

    first, second = transcript["segments"]
    assert first["end"] <= second["start"] + 1e-9


def test_a_result_far_outside_the_window_is_not_trusted():
    transcript = _transcript((10.0, 12.0, ["a", "b"]))
    original = _starts(transcript)

    report = refine_transcript(
        transcript, lambda *_: [(40.0, 41.0), (42.0, 43.0)], total_seconds=60.0
    )

    assert report.failed_segments == 1
    assert _starts(transcript) == original


def test_segments_without_words_are_left_alone():
    transcript = {"segments": [{"start": 1.0, "end": 2.0, "text": " x"}], "language": "x"}

    report = refine_transcript(transcript, lambda *_: [(1.0, 2.0)], total_seconds=10.0)

    assert (report.aligned_segments, report.failed_segments) == (0, 0)


def test_romanizing_keeps_only_letters_and_apostrophes():
    class Fake:
        def romanize_string(self, word):
            return {"නුඹ": "Nuba!", "x": "1 2 3", "don't": "Don't,"}[word]

    assert romanize_word(Fake(), "නුඹ") == "nuba"
    assert romanize_word(Fake(), "x") == ""
    assert romanize_word(Fake(), "don't") == "don't"

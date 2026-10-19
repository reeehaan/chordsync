from __future__ import annotations

from analysis.lyrics.repetition_guard import remove_repetition_loops


def _words(texts: list[str], start: float = 0.0, step: float = 0.5) -> list[dict]:
    return [
        {"word": text, "start": start + i * step, "end": start + i * step + 0.4, "score": 0.9}
        for i, text in enumerate(texts)
    ]


def _transcript(*segments: list[str]) -> dict:
    built = []
    cursor = 0.0
    for texts in segments:
        words = _words(texts, cursor)
        cursor = words[-1]["end"] + 1
        built.append(
            {
                "start": words[0]["start"],
                "end": words[-1]["end"],
                "text": " " + " ".join(texts),
                "words": words,
            }
        )
    return {
        "segments": built,
        "word_segments": [word for segment in built for word in segment["words"]],
        "language": "en",
    }


def _texts(transcript: dict, segment: int) -> list[str]:
    return [word["word"] for word in transcript["segments"][segment]["words"]]


def test_a_long_phrase_loop_is_cut_to_three_repeats():
    phrase = ["hold", "me", "like", "this"]
    transcript = _transcript(["so", "tonight"] + phrase * 30 + ["the", "end"])

    report = remove_repetition_loops(transcript)

    assert report.loops == 1
    assert report.removed_words == 27 * 4
    assert _texts(transcript, 0) == ["so", "tonight"] + phrase * 3 + ["the", "end"]


def test_a_single_word_loop_is_cut():
    transcript = _transcript(["la"] * 25 + ["done"])

    report = remove_repetition_loops(transcript)

    assert report.removed_words == 22
    assert _texts(transcript, 0) == ["la"] * 3 + ["done"]


def test_ordinary_repeats_are_left_alone():
    chorus = ["na"] * 8 + ["hey", "jude"] * 5 + ["oh", "oh", "oh", "oh"]
    transcript = _transcript(chorus)
    original = _texts(transcript, 0)

    report = remove_repetition_loops(transcript)

    assert (report.removed_words, report.loops) == (0, 0)
    assert _texts(transcript, 0) == original


def test_case_and_punctuation_do_not_hide_a_loop():
    words = ["Hold,", "me.", "HOLD", "me"] * 4 + ["hold", "me"] * 4
    transcript = _transcript(words)

    assert remove_repetition_loops(transcript).loops == 1


def test_segment_text_times_and_flat_words_stay_consistent():
    transcript = _transcript(["intro", "words"], ["a", "b"] * 20 + ["last"])

    remove_repetition_loops(transcript)

    segment = transcript["segments"][1]
    kept = segment["words"]
    assert segment["text"] == " " + " ".join(word["word"] for word in kept)
    assert segment["start"] == kept[0]["start"]
    assert segment["end"] == kept[-1]["end"]
    flat_texts = [word["word"] for word in transcript["word_segments"]]
    assert flat_texts == [w["word"] for s in transcript["segments"] for w in s["words"]]
    assert _texts(transcript, 0) == ["intro", "words"]


def test_other_segments_are_not_touched():
    transcript = _transcript(["one", "two", "three"], ["x", "y"] * 20)

    remove_repetition_loops(transcript)

    assert _texts(transcript, 0) == ["one", "two", "three"]
    assert len(transcript["segments"]) == 2


def test_empty_and_malformed_payloads_are_safe():
    for payload in ({}, {"segments": None}, {"segments": [{}]}, {"segments": [{"words": []}]}):
        before = repr(payload)
        report = remove_repetition_loops(payload)
        assert (report.removed_words, report.loops) == (0, 0)
        assert repr(payload) == before


def test_words_without_timestamps_do_not_break_the_guard():
    words = [{"word": "la"} for _ in range(20)]
    transcript = {"segments": [{"text": "x", "words": words}], "word_segments": []}

    report = remove_repetition_loops(transcript)

    assert report.loops == 1
    assert len(transcript["segments"][0]["words"]) == 3


def test_a_word_made_of_one_stuck_character_is_dropped():
    stuck = "ḍ" + "ᴀ" * 70
    transcript = _transcript(["so", stuck, "tonight"])

    report = remove_repetition_loops(transcript)

    assert report.removed_words == 1
    assert _texts(transcript, 0) == ["so", "tonight"]


def test_a_stretched_vowel_is_a_real_word_and_stays():
    transcript = _transcript(["yeeeeeeeeeah", "ooooooooh", "love"])

    report = remove_repetition_loops(transcript)

    assert (report.removed_words, report.loops) == (0, 0)
    assert _texts(transcript, 0) == ["yeeeeeeeeeah", "ooooooooh", "love"]

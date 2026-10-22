from analysis.lyrics.lyrics_decision import (
    LyricsPath,
    decide_with_reference,
    low_confidence_reason,
    mean_word_score,
)


def test_a_transcript_that_mostly_agrees_is_kept():
    decision = decide_with_reference(
        error_rate=0.2, compared_words=200, reference_is_timed=True
    )
    assert decision.path is LyricsPath.TRANSCRIPT


def test_a_transcript_that_mostly_disagrees_is_replaced_by_a_timed_reference():
    decision = decide_with_reference(
        error_rate=0.74, compared_words=300, reference_is_timed=True
    )
    assert decision.path is LyricsPath.REFERENCE


def test_a_transcript_that_mostly_disagrees_with_an_untimed_reference_gives_none():
    decision = decide_with_reference(
        error_rate=0.74, compared_words=300, reference_is_timed=False
    )
    assert decision.path is LyricsPath.NONE


def test_too_few_compared_words_is_not_judged():
    decision = decide_with_reference(
        error_rate=0.9, compared_words=10, reference_is_timed=True
    )
    assert decision.path is LyricsPath.TRANSCRIPT


def _transcript(scores):
    return {
        "segments": [{"words": [{"word": "x", "score": score} for score in scores]}]
    }


def test_low_recogniser_confidence_is_reported_without_a_reference():
    assert "unsure" in low_confidence_reason(_transcript([0.2] * 30))
    assert low_confidence_reason(_transcript([0.8] * 30)) is None


def test_few_scored_words_are_not_judged():
    assert low_confidence_reason(_transcript([0.1] * 5)) is None
    assert mean_word_score({"segments": []}) == (None, 0)


def test_a_non_english_song_without_a_timed_reference_gets_no_lyrics():
    from analysis.lyrics.lyrics_decision import non_english_without_timed_lyrics_reason

    transcript = {"language": "ko", "segments": [{"text": "한국어 가사"}]}
    assert "non-English" in non_english_without_timed_lyrics_reason(
        transcript, reference_plain_lyrics=None
    )
    # With an untimed non-English reference there is still nothing to follow.
    assert non_english_without_timed_lyrics_reason(
        {"language": "si", "segments": []}, reference_plain_lyrics="මන්දාරම් හැන්දෑවේ"
    )


def test_english_songs_and_reference_built_lyrics_are_left_alone():
    from analysis.lyrics.lyrics_decision import non_english_without_timed_lyrics_reason

    assert non_english_without_timed_lyrics_reason(
        {"language": "en", "segments": []}, reference_plain_lyrics=None
    ) is None
    assert non_english_without_timed_lyrics_reason(
        {"language": "synced", "segments": []}, reference_plain_lyrics="x"
    ) is None
    assert non_english_without_timed_lyrics_reason(
        {"language": "en", "segments": []}, reference_plain_lyrics="short"
    ) is None


def test_text_in_another_script_is_not_english_whatever_it_was_labelled():
    from analysis.lyrics.lyrics_decision import non_english_without_timed_lyrics_reason

    hangul = [{"text": "안녕하세요 사랑해요 안녕하세요 사랑해요"}]
    for label in ("en", "ko", ""):
        reason = non_english_without_timed_lyrics_reason(
            {"language": label, "segments": hangul}, reference_plain_lyrics=None
        )
        assert reason and "Hangul" in reason

    english = [{"text": "I know that you are all that I need and the sky is blue"}]
    assert non_english_without_timed_lyrics_reason(
        {"language": "nn", "segments": english * 5}, reference_plain_lyrics=None
    ) is None


def test_aligned_plain_lyrics_are_trusted_only_when_they_fit():
    from analysis.lyrics.lyrics_decision import plain_alignment_is_trustworthy

    assert plain_alignment_is_trustworthy(0.68, 0.08)[0]  # Hindi, right lyrics
    assert plain_alignment_is_trustworthy(0.49, 0.21)[0]  # Sinhala, right lyrics
    assert not plain_alignment_is_trustworthy(0.14, 0.81)[0]  # wrong song
    assert not plain_alignment_is_trustworthy(0.31, 0.52)[0]  # scrambled lines
    assert not plain_alignment_is_trustworthy(0.38, 0.35)[0]  # wrong song, other pair


def test_reference_lyrics_are_non_english_by_script_or_by_words():
    from analysis.lyrics.lyrics_decision import reference_is_non_english

    assert reference_is_non_english("මන්දාරම් හැන්දෑවේ ආදරයෙන් වෙලා ඔබ රාගයක මා හට පෙම් කරන මාලයේ රඟා")
    romanized_hindi = " ".join(["dil ka dariya bah hi gaya"] * 8)
    assert reference_is_non_english(romanized_hindi)
    english = (
        "I know that you are all that I need and I love the way you hold me in the "
        "night when the world is quiet and we are alone with the stars"
    )
    assert not reference_is_non_english(english)
    assert not reference_is_non_english("too short")

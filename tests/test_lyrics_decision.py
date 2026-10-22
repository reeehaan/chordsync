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

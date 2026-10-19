from __future__ import annotations

from analysis.lyrics.lyric_quality import (
    english_vocabulary_reason,
    unreliable_reason,
    without_lyrics,
)


def _transcript(*lines, language="hi"):
    segments = []
    cursor = 0.0
    for words, seconds in lines:
        segments.append(
            {
                "start": cursor,
                "end": cursor + seconds,
                "text": " " + " ".join(words),
                "words": [{"word": w, "start": cursor, "end": cursor + 0.4} for w in words],
            }
        )
        cursor += seconds + 1
    return {"segments": segments, "language": language}


def _varied(count):
    return [f"word{chr(97 + i % 26)}{i}" for i in range(count)]


def test_a_normal_transcript_is_trusted():
    assert unreliable_reason(_transcript((_varied(30), 10), (_varied(30), 10))) is None


def test_too_few_words_to_judge_is_trusted():
    assert unreliable_reason(_transcript((["la", "la", "la"], 20))) is None


def test_two_scripts_in_one_song_are_not_trusted():
    words = ["hello", "there", "friend", "again", "today"] * 4 + ["नमस्ते", "दोस्त", "फिर", "आज"] * 5

    reason = unreliable_reason(_transcript((words, 20)))

    assert reason == "mixed scripts: DEVANAGARI, LATIN"


def test_a_stray_foreign_word_is_not_enough_to_distrust_a_transcript():
    words = _varied(60) + ["नमस्ते"]

    assert unreliable_reason(_transcript((words, 30))) is None


def test_one_word_repeated_dozens_of_times_is_not_trusted():
    words = _varied(30) + ["ahhh"] * 40

    assert unreliable_reason(_transcript((words, 30))) == "one word repeated 40 times"


def test_a_chorus_that_repeats_a_little_is_trusted():
    words = _varied(40) + ["oh"] * 8

    assert unreliable_reason(_transcript((words, 30))) is None


def test_extreme_lack_of_variety_is_not_trusted():
    words = [f"w{i % 12}" for i in range(120)]  # 12 distinct words in 120

    assert unreliable_reason(_transcript((words, 30))) == "very little variety in the words"


def test_ordinary_song_repetition_is_trusted():
    # A real song with a repeated chorus: about a third of the words are distinct.
    words = [f"w{i % 40}" for i in range(120)]

    assert unreliable_reason(_transcript((words, 30))) is None


def test_several_long_lines_with_one_word_are_not_trusted():
    lines = [(_varied(10), 6), (["la"], 20), (_varied(10), 6), (["na"], 25)]

    assert unreliable_reason(_transcript(*lines)) == (
        "several long lines with only one or two words"
    )


def test_one_long_held_word_is_fine():
    lines = [(_varied(10), 6), (["ahh"], 12), (_varied(10), 6)]

    assert unreliable_reason(_transcript(*lines)) is None


def test_without_lyrics_keeps_nothing_but_the_language_note():
    result = without_lyrics({"segments": [{"x": 1}], "language": "hi"})

    assert result == {
        "segments": [],
        "word_segments": [],
        "language": "unreliable",
        "original_language": "hi",
    }


SINGLISH = (
    "Ob my hadeh lehi randindin Mal maavate sar nethu sihinen ahasa "
    "diyath manaram kandulu galaya kiyaa yanna balan inna handa pena "
).split() * 2
ENGLISH = (
    "I know that you are all that I need and I love the way you hold me in the "
    "night when the world is quiet and we are alone with the stars and the sky"
).split() * 2


def test_sinhala_spelled_in_english_letters_is_not_english():
    reason = english_vocabulary_reason(_transcript((SINGLISH, 30), language="en"))

    assert reason is not None and reason.startswith("labelled English but only")


def test_real_english_lyrics_pass_the_english_check():
    assert english_vocabulary_reason(_transcript((ENGLISH, 30), language="en")) is None


def test_a_short_english_transcript_is_not_judged():
    assert english_vocabulary_reason(_transcript((SINGLISH[:20], 10), language="en")) is None


def test_english_songs_with_unusual_words_still_have_common_words():
    words = ("yo yo gonna flow like a river in the night " * 6).split()

    assert english_vocabulary_reason(_transcript((words, 30), language="en")) is None

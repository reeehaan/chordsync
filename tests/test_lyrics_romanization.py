from analysis.lyrics.romanization import romanize_whisperx_result


def _result(language: str, text: str) -> dict:
    return {
        "language": language,
        "segments": [
            {
                "start": 1.25,
                "end": 2.75,
                "text": text,
                "words": [
                    {
                        "start": 1.25,
                        "end": 2.75,
                        "word": text,
                        "score": 0.91,
                    }
                ],
            }
        ],
        "word_segments": [
            {
                "start": 1.25,
                "end": 2.75,
                "word": text,
                "score": 0.91,
            }
        ],
    }


def test_english_result_remains_exactly_unchanged():
    result = _result("en", "Stay with me")

    romanized = romanize_whisperx_result(result)

    assert romanized is result
    assert romanized == _result("en", "Stay with me")


def test_hindi_result_uses_latin_letters_without_changing_timing():
    result = _result("hi", "महासमुंद")

    romanized = romanize_whisperx_result(result)

    assert romanized is not result
    assert romanized["segments"][0]["text"] == "mhasmumd"
    assert romanized["segments"][0]["words"][0] == {
        "start": 1.25,
        "end": 2.75,
        "word": "mhasmumd",
        "score": 0.91,
    }
    assert romanized["word_segments"][0]["word"] == "mhasmumd"
    assert result == _result("hi", "महासमुंद")


def test_non_latin_script_is_romanized_when_whisperx_mislabels_it_as_english():
    result = _result("en", "महासमुंद")

    romanized = romanize_whisperx_result(result)

    assert romanized["segments"][0]["text"] == "mhasmumd"


def test_japanese_and_sinhala_results_use_latin_letters():
    assert (
        romanize_whisperx_result(_result("ja", "さいたま"))["segments"][0][
            "text"
        ]
        == "saitama"
    )
    assert (
        romanize_whisperx_result(_result("si", "රත්නපුර"))["segments"][0][
            "text"
        ]
        == "rtnpur"
    )


def test_mixed_ascii_words_and_punctuation_are_preserved():
    result = _result("hi", "Hello, महासमुंद!")

    romanized = romanize_whisperx_result(result)

    assert romanized["segments"][0]["text"] == "Hello, mhasmumd!"

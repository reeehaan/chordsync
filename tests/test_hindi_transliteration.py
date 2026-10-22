import pytest

from analysis.lyrics.hindi_transliteration import (
    contains_devanagari,
    transliterate_hindi,
)


@pytest.mark.parametrize(
    "hindi, english_letters",
    [
        # Lines whose English-letter spelling was written by people on LRCLIB.
        ("दिल का दरिया बह ही गया", "dil ka dariya bah hi gaya"),
        ("इश्क़ इबादत बन ही गया", "ishq ibaadat ban hi gaya"),
        ("खुद को मुझे तू सौंप दे", "khud ko mujhe tu saunp de"),
        ("जो तुम मेरे हो", "jo tum mere ho"),
    ],
)
def test_lines_read_the_way_people_write_hindi_in_english_letters(
    hindi, english_letters
):
    assert transliterate_hindi(hindi) == english_letters


@pytest.mark.parametrize(
    "hindi, english_letters",
    [
        ("नज़रों में", "nazron mein"),  # the dotted ज़ is kept
        ("ख़ुद", "khud"),
        ("नहीं", "nahin"),
        ("मैंने", "maine"),
        ("हम", "hum"),
        ("लेंगे", "lenge"),  # the -ein ending is only for the end of a word
        ("जाएँगे", "jaayenge"),
        ("कुछ", "kuch"),
    ],
)
def test_common_spellings_and_special_letters(hindi, english_letters):
    assert transliterate_hindi(hindi) == english_letters


def test_the_dotted_letters_work_in_either_unicode_form():
    precomposed = "ज़"  # ज़ as one character
    decomposed = "ज़"  # ज + the dot
    assert transliterate_hindi(f"{precomposed}मीं") == transliterate_hindi(
        f"{decomposed}मीं"
    )


def test_other_text_is_left_alone():
    assert transliterate_hindi("Hello हम, world!") == "Hello hum, world!"
    assert transliterate_hindi("no hindi here") == "no hindi here"
    assert transliterate_hindi("") == ""


def test_contains_devanagari():
    assert contains_devanagari("जो तुम")
    assert not contains_devanagari("jo tum")
    assert not contains_devanagari(None)

from analysis.lyrics.language_hint import looks_english

ENGLISH = (
    "I know that you are all that I need and I love the way you hold me in the "
    "night when the world is quiet and we are alone with the stars and the sky"
)
ROMANISED_HINDI = (
    "tum mere ho tum mere ho kya kahun main tujhse dil mein basa hai tu hi mera "
    "sab kuch hai tu hi meri duniya hai bas tu hi tu hi hai mere liye tera naam"
)


def test_english_lyrics_are_recognised():
    assert looks_english(ENGLISH)


def test_romanised_hindi_is_not_english():
    assert not looks_english(ROMANISED_HINDI)


def test_non_latin_scripts_are_not_english():
    assert not looks_english("මන්දාරම් හැන්දෑවේ " * 30)
    assert not looks_english("महासमुंद " * 40)


def test_too_little_text_is_not_enough_evidence():
    assert not looks_english("I love you so much")
    assert not looks_english("")
    assert not looks_english(None)

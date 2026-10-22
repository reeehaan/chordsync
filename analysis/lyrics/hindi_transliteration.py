"""Write Devanagari (Hindi) in English letters, the way people type Hindi.

"दिल का दरिया बह ही गया" becomes "dil ka dariya bah hi gaya". A plain letter-by-letter
table gives "dil ka driya bh hi gya", because Devanagari does not write the short "a"
that follows most consonants. Readers of English-letter Hindi expect it back, except
where it is not pronounced. The rules for that ("schwa deletion") are the usual simple
ones: it is dropped at the end of a word and between two syllables that carry a vowel
(dar-i-ya keeps it, but ibaadat-b-d does not).

No dependencies, so it runs anywhere the worker does.
"""

from __future__ import annotations

import re
import unicodedata

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
}
_INDEPENDENT_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o",
}
_NUKTA = "़"
_VIRAMA = "्"
_NASALS = {"ं": "n", "ँ": "n"}  # anusvara, chandrabindu
_VISARGA = "ः"
_PUNCTUATION = {"।": ".", "॥": "."}
# Spellings that differ from what the rules give, because that is how they are
# written in English-letter Hindi.
_COMMON_WORDS = {
    "हम": "hum",
    "ओ": "oh",
    "कुछ": "kuch",
    "मैंने": "maine",
    "तूने": "tune",
    "हमने": "humne",
}
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[ऀ-ॿ]+")


def contains_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text or ""))


def transliterate_hindi(text: str) -> str:
    """The text with every Devanagari word written in English letters."""
    # Dotted letters (ज़, क़, ख़) come both as one character and as a letter plus a
    # dot; this makes them all the second kind, which is the one the tables read.
    text = unicodedata.normalize("NFC", text)
    text = "".join(_PUNCTUATION.get(c, c) for c in text)
    return _WORD.sub(lambda match: _transliterate_word(match.group(0)), text)


def _syllables(word: str) -> list[list]:
    """[[consonant_or_None, vowel_text_or_None, nasal_text], ...] in order.

    A vowel of ``None`` on a consonant means the inherent "a" (not yet decided).
    A conjunct (consonant + virama + consonant) keeps its first consonant with the
    vowel text ``""`` (silent), so it never gets an "a".
    """
    items: list[list] = []
    index = 0
    while index < len(word):
        char = word[index]
        letter = None
        if index + 1 < len(word) and word[index + 1] == _NUKTA:
            composed = char + "़"
            letter = _NUKTA_MAP.get(composed)
            if letter is not None:
                index += 2
        if letter is None and char in _CONSONANTS:
            letter = _CONSONANTS[char]
            index += 1
        if letter is not None:
            vowel: str | None = None
            if index < len(word) and word[index] == _VIRAMA:
                vowel = ""
                index += 1
            elif index < len(word) and word[index] in _MATRAS:
                vowel = _MATRAS[word[index]]
                index += 1
            items.append([letter, vowel, ""])
            continue
        if char in _INDEPENDENT_VOWELS:
            items.append([None, _INDEPENDENT_VOWELS[char], ""])
        elif char in _NASALS or char == _VISARGA:
            nasal = _NASALS.get(char, "h")
            if items:
                items[-1][2] += nasal
            else:
                items.append([None, "", nasal])
        index += 1
    return items


_NUKTA_MAP = {
    "क़": "q",
    "ख़": "kh",
    "ग़": "g",
    "ज़": "z",
    "ड़": "r",
    "ढ़": "rh",
    "फ़": "f",
}


def _transliterate_word(word: str) -> str:
    if word in _COMMON_WORDS:
        return _COMMON_WORDS[word]
    items = _syllables(word)
    if not items:
        return word
    # Decide each inherent "a". Only a consonant with no written vowel needs it.
    has_vowel = [item[1] is not None and item[1] != "" for item in items]
    for position, item in enumerate(items):
        if item[0] is None or item[1] is not None:
            continue
        last = position == len(items) - 1
        first = position == 0
        # Does the next syllable end up with a spoken vowel? (A final bare
        # consonant will lose its "a", so it does not count.)
        next_vowel = (
            position + 1 < len(items)
            and (
                items[position + 1][1] not in (None, "")
                or (items[position + 1][1] is None and position + 2 < len(items))
            )
        )
        previous_vowel = position > 0 and has_vowel[position - 1]
        if len(items) == 1:
            keep = True  # a one-letter word ("न") is "na"
        elif last:
            keep = False
        elif first:
            keep = True
        else:
            keep = not (previous_vowel and next_vowel)
        item[1] = "a" if keep else ""
        has_vowel[position] = keep
    pieces: list[str] = []
    for position, (letter, vowel, nasal) in enumerate(items):
        text = (letter or "") + (vowel or "")
        if nasal == "n":
            following = items[position + 1][0] if position + 1 < len(items) else None
            if following in ("n", "m"):
                nasal = ""  # मैंने is "maine", not "mainne"
            elif letter is not None and position == len(items) - 1:
                # At the end of a word: नहीं is "nahin", में is "mein".
                if vowel == "ee":
                    text = letter + "i"
                elif vowel == "e":
                    text = letter + "ei"
        if letter is None and vowel == "e" and pieces and pieces[-1].endswith("a"):
            text = "y" + text  # आए is "aaye"
        pieces.append(text + nasal)
    return _short_ending("".join(pieces))


_SHORT_ENDINGS = (("aa", "a"), ("ee", "i"), ("oo", "u"), ("chh", "ch"))


def _short_ending(word: str) -> str:
    """People write a word-final long vowel short: "ka", "hi", "tu", not "kaa"."""
    if len(word) <= 2:
        return word  # "aa", "ee" alone, or a bare vowel
    for long_vowel, short in _SHORT_ENDINGS:
        if word.endswith(long_vowel):
            return word[: -len(long_vowel)] + short
    return word

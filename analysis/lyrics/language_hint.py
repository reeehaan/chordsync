"""Tell whether reference lyrics are English, without a model or the network.

WhisperX guesses a song's language from the first seconds of the vocals, and a
quiet or unusual intro can make it pick the wrong one (an English song came back
as Nynorsk). The cloud worker only has the English alignment model, so a wrong
guess used to fail the whole job. The reference lyrics give a better signal.
"""

from __future__ import annotations

import re

# Very common English words that are rare in other languages written in Latin
# script (including romanised Hindi and Sinhala).
_ENGLISH_WORDS = frozenset(
    "the and you i to a of it in is that my me we your this for on with be are "
    "but all so not just oh when what up no yeah like if can as at they he she "
    "do don't i'm it's know love".split()
)
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")

_MINIMUM_WORDS = 30
_MINIMUM_SHARE = 0.25


def looks_english(text: str | None) -> bool:
    words = _WORD.findall((text or "").casefold())
    if len(words) < _MINIMUM_WORDS:
        return False
    common = sum(1 for word in words if word in _ENGLISH_WORDS)
    return common / len(words) >= _MINIMUM_SHARE

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from analysis.lyrics.lyrics_reference import LyricsReferenceSource, SongIdentity


class AlignmentOperation(str, Enum):
    MATCH = "MATCH"
    SUBSTITUTION = "SUBSTITUTION"
    INSERTION = "INSERTION"
    DELETION = "DELETION"


class VerificationState(str, Enum):
    VERIFIED_REFERENCE = "VERIFIED_REFERENCE"
    ASR_ONLY = "ASR_ONLY"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class TimedAsrWord:
    word: str
    start: float
    end: float


@dataclass(frozen=True)
class ReferenceWord:
    display: str
    normalized: str


@dataclass(frozen=True)
class AlignedToken:
    operation: AlignmentOperation
    asr_word: TimedAsrWord | None
    reference_word: ReferenceWord | None


@dataclass(frozen=True)
class VerifiedToken:
    display_word: str
    asr_word: str | None
    reference_word: str | None
    verification: VerificationState
    start: float | None
    end: float | None
    operation: AlignmentOperation


@dataclass(frozen=True)
class WordErrorMetrics:
    matches: int
    substitutions: int
    insertions: int
    deletions: int
    reference_words: int

    @property
    def wer(self) -> float:
        if self.reference_words == 0:
            return 0.0
        return (
            self.substitutions + self.insertions + self.deletions
        ) / self.reference_words


@dataclass(frozen=True)
class LyricsVerificationResult:
    song_identity: SongIdentity
    aligned_tokens: tuple[AlignedToken, ...]
    tokens: tuple[VerifiedToken, ...]
    raw_metrics: WordErrorMetrics
    corrected_metrics: WordErrorMetrics


_TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
_ASR_INTERJECTIONS = frozenset({"ah", "hey", "la", "oh", "ooh", "uh", "yeah"})
_MAX_LOCAL_GAP_SECONDS = 2.0
_CONTRACTION_EQUIVALENTS = {
    "can't": "cannot",
    "couldn't": "couldnot",
    "didn't": "didnot",
    "doesn't": "doesnot",
    "don't": "donot",
    "hadn't": "hadnot",
    "hasn't": "hasnot",
    "haven't": "havenot",
    "he'll": "hewill",
    "he's": "heis",
    "i'll": "iwill",
    "i'm": "iam",
    "i've": "ihave",
    "isn't": "isnot",
    "it's": "itis",
    "she'll": "shewill",
    "she's": "sheis",
    "shouldn't": "shouldnot",
    "that's": "thatis",
    "they'll": "theywill",
    "they're": "theyare",
    "they've": "theyhave",
    "wasn't": "wasnot",
    "we'll": "wewill",
    "we're": "weare",
    "we've": "wehave",
    "weren't": "werenot",
    "won't": "willnot",
    "wouldn't": "wouldnot",
    "you'll": "youwill",
    "you're": "youare",
    "you've": "youhave",
}


def normalize_word(word: str) -> str:
    """Normalize a token for comparison without changing display spelling."""
    normalized = unicodedata.normalize("NFKC", word).casefold()
    normalized = normalized.replace("’", "'")
    normalized = _CONTRACTION_EQUIVALENTS.get(normalized, normalized)
    normalized = normalized.replace("'", "")
    return "".join(character for character in normalized if character.isalnum())


def tokenize_reference(text: str) -> list[ReferenceWord]:
    return [
        ReferenceWord(display=match.group(0), normalized=normalize_word(match.group(0)))
        for match in _TOKEN_PATTERN.finditer(text)
        if normalize_word(match.group(0))
    ]


def parse_whisperx_words(result: Mapping[str, object]) -> list[TimedAsrWord]:
    words: list[TimedAsrWord] = []
    for segment in result.get("segments", []):
        if not isinstance(segment, Mapping):
            continue
        for item in segment.get("words", []):
            if not isinstance(item, Mapping):
                continue
            if "start" not in item or "end" not in item:
                continue
            word = str(item.get("word", "")).strip()
            if not normalize_word(word):
                continue
            start = float(item["start"])
            end = float(item["end"])
            if end < start:
                continue
            words.append(TimedAsrWord(word=word, start=start, end=end))
    return words


def align_words(
    asr_words: Sequence[TimedAsrWord],
    reference_words: Sequence[ReferenceWord],
) -> list[AlignedToken]:
    """Return a deterministic Levenshtein alignment with explicit operations."""
    rows = len(asr_words) + 1
    columns = len(reference_words) + 1
    costs = [[0] * columns for _ in range(rows)]
    operations: list[list[AlignmentOperation | None]] = [
        [None] * columns for _ in range(rows)
    ]
    for asr_index in range(1, rows):
        costs[asr_index][0] = asr_index
        operations[asr_index][0] = AlignmentOperation.INSERTION
    for reference_index in range(1, columns):
        costs[0][reference_index] = reference_index
        operations[0][reference_index] = AlignmentOperation.DELETION

    priority = {
        AlignmentOperation.MATCH: 0,
        AlignmentOperation.SUBSTITUTION: 1,
        AlignmentOperation.DELETION: 2,
        AlignmentOperation.INSERTION: 3,
    }
    for asr_index in range(1, rows):
        for reference_index in range(1, columns):
            equal = normalize_word(asr_words[asr_index - 1].word) == (
                reference_words[reference_index - 1].normalized
            )
            diagonal_operation = (
                AlignmentOperation.MATCH if equal else AlignmentOperation.SUBSTITUTION
            )
            candidates = [
                (costs[asr_index - 1][reference_index - 1] + (not equal), diagonal_operation),
                (costs[asr_index][reference_index - 1] + 1, AlignmentOperation.DELETION),
                (costs[asr_index - 1][reference_index] + 1, AlignmentOperation.INSERTION),
            ]
            cost, operation = min(
                candidates,
                key=lambda candidate: (candidate[0], priority[candidate[1]]),
            )
            costs[asr_index][reference_index] = int(cost)
            operations[asr_index][reference_index] = operation

    aligned: list[AlignedToken] = []
    asr_index = len(asr_words)
    reference_index = len(reference_words)
    while asr_index or reference_index:
        operation = operations[asr_index][reference_index]
        if operation in {AlignmentOperation.MATCH, AlignmentOperation.SUBSTITUTION}:
            aligned.append(
                AlignedToken(
                    operation=operation,
                    asr_word=asr_words[asr_index - 1],
                    reference_word=reference_words[reference_index - 1],
                )
            )
            asr_index -= 1
            reference_index -= 1
        elif operation is AlignmentOperation.INSERTION:
            aligned.append(
                AlignedToken(operation, asr_words[asr_index - 1], None)
            )
            asr_index -= 1
        else:
            aligned.append(
                AlignedToken(operation, None, reference_words[reference_index - 1])
            )
            reference_index -= 1
    aligned.reverse()
    return aligned


def calculate_metrics(alignment: Iterable[AlignedToken]) -> WordErrorMetrics:
    counts = Counter(token.operation for token in alignment)
    return WordErrorMetrics(
        matches=counts[AlignmentOperation.MATCH],
        substitutions=counts[AlignmentOperation.SUBSTITUTION],
        insertions=counts[AlignmentOperation.INSERTION],
        deletions=counts[AlignmentOperation.DELETION],
        reference_words=(
            counts[AlignmentOperation.MATCH]
            + counts[AlignmentOperation.SUBSTITUTION]
            + counts[AlignmentOperation.DELETION]
        ),
    )


def classify_alignment(alignment: Sequence[AlignedToken]) -> list[VerifiedToken]:
    asr_counts = Counter(
        normalize_word(token.asr_word.word)
        for token in alignment
        if token.asr_word is not None
    )
    reference_counts = Counter(
        token.reference_word.normalized
        for token in alignment
        if token.reference_word is not None
    )
    return [
        _classify_token(alignment, index, asr_counts, reference_counts)
        for index in range(len(alignment))
    ]


def _classify_token(
    alignment: Sequence[AlignedToken],
    index: int,
    asr_counts: Counter[str],
    reference_counts: Counter[str],
) -> VerifiedToken:
    token = alignment[index]
    asr = token.asr_word
    reference = token.reference_word
    if token.operation is AlignmentOperation.MATCH:
        assert asr is not None and reference is not None
        return VerifiedToken(
            reference.display,
            asr.word,
            reference.display,
            VerificationState.VERIFIED_REFERENCE,
            asr.start,
            asr.end,
            token.operation,
        )

    previous = alignment[index - 1] if index > 0 else None
    following = alignment[index + 1] if index + 1 < len(alignment) else None
    bounded_by_matches = (
        previous is not None
        and following is not None
        and previous.operation is AlignmentOperation.MATCH
        and following.operation is AlignmentOperation.MATCH
    )
    timing_is_local = _timing_is_local(previous, token, following)

    if token.operation is AlignmentOperation.SUBSTITUTION:
        assert asr is not None and reference is not None
        repeated = (
            asr_counts[normalize_word(asr.word)] > 1
            or reference_counts[reference.normalized] > 1
        )
        if bounded_by_matches and timing_is_local and not repeated:
            return VerifiedToken(
                reference.display,
                asr.word,
                reference.display,
                VerificationState.VERIFIED_REFERENCE,
                None,
                None,
                token.operation,
            )
        return _uncertain(token)

    if token.operation is AlignmentOperation.INSERTION:
        assert asr is not None
        if (
            normalize_word(asr.word) in _ASR_INTERJECTIONS
            and bounded_by_matches
            and timing_is_local
        ):
            return VerifiedToken(
                asr.word,
                asr.word,
                None,
                VerificationState.ASR_ONLY,
                asr.start,
                asr.end,
                token.operation,
            )
        return _uncertain(token)

    return _uncertain(token)


def _timing_is_local(
    previous: AlignedToken | None,
    current: AlignedToken,
    following: AlignedToken | None,
) -> bool:
    before = previous.asr_word if previous else None
    after = following.asr_word if following else None
    if before is None or after is None or after.start < before.end:
        return False
    if current.asr_word is None:
        return False
    return (
        current.asr_word.start >= before.end
        and current.asr_word.end <= after.start
        and current.asr_word.start - before.end <= _MAX_LOCAL_GAP_SECONDS
        and after.start - current.asr_word.end <= _MAX_LOCAL_GAP_SECONDS
    )


def _uncertain(token: AlignedToken) -> VerifiedToken:
    asr = token.asr_word
    reference = token.reference_word
    return VerifiedToken(
        display_word=(asr.word if asr else reference.display),
        asr_word=asr.word if asr else None,
        reference_word=reference.display if reference else None,
        verification=VerificationState.UNCERTAIN,
        start=asr.start if asr else None,
        end=asr.end if asr else None,
        operation=token.operation,
    )


class LyricsVerifier:
    def __init__(self, reference_source: LyricsReferenceSource) -> None:
        self._reference_source = reference_source

    def verify(
        self,
        song_identity: SongIdentity,
        whisperx_result: Mapping[str, object],
    ) -> LyricsVerificationResult:
        reference = tokenize_reference(
            self._reference_source.get_lyrics(song_identity)
        )
        asr = parse_whisperx_words(whisperx_result)
        alignment = align_words(asr, reference)
        tokens = classify_alignment(alignment)
        corrected_asr = [
            TimedAsrWord(token.display_word, index, index + 0.5)
            for index, token in enumerate(tokens)
            if token.operation is not AlignmentOperation.DELETION
        ]
        corrected_alignment = align_words(corrected_asr, reference)
        return LyricsVerificationResult(
            song_identity=song_identity,
            aligned_tokens=tuple(alignment),
            tokens=tuple(tokens),
            raw_metrics=calculate_metrics(alignment),
            corrected_metrics=calculate_metrics(corrected_alignment),
        )

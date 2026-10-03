from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from analysis.lyrics.forced_alignment import (
    ReferenceAlignmentSegment,
    select_forced_alignment_context,
)
from analysis.lyrics.lyrics_verification import (
    AlignmentOperation,
    TimedAsrWord,
    VerificationState,
    align_words,
    calculate_metrics,
    classify_alignment,
    normalize_word,
    parse_whisperx_words,
    tokenize_reference,
)


class ReferenceAligner(Protocol):
    def align(
        self,
        audio_path: Path,
        segments: Sequence[ReferenceAlignmentSegment],
    ) -> Mapping[str, object]: ...


MAXIMUM_BOUNDARY_OVERLAP_SECONDS = 0.1
MAXIMUM_WORD_DURATION_SECONDS = 2.5
MINIMUM_WORD_DURATION_SECONDS = 0.000001


class TimingProvenanceState(str, Enum):
    EXACT_FORCED_ALIGNMENT = "EXACT_FORCED_ALIGNMENT"
    BOUNDARY_RECONCILED = "BOUNDARY_RECONCILED"


@dataclass(frozen=True)
class CorrectionTimingProvenance:
    state: TimingProvenanceState
    word_index: int
    forced_timing: TimedAsrWord
    final_timing: TimedAsrWord
    previous_original: TimedAsrWord | None = None
    previous_adjusted: TimedAsrWord | None = None
    next_original: TimedAsrWord | None = None
    next_adjusted: TimedAsrWord | None = None


@dataclass(frozen=True)
class LyricsVerificationDiagnostics:
    matches: int
    substitutions: int
    insertions: int
    deletions: int
    raw_wer: float
    corrected_wer: float
    verified_candidates: int
    forced_alignment_candidates: int
    forced_alignment_successes: int
    forced_alignment_failures: int
    reconciliation_candidates: int
    accepted_corrections: int
    rejected_corrections: int
    safety_rejections: int


@dataclass(frozen=True)
class ProductionLyricsVerificationResult:
    whisperx_result: Mapping[str, object]
    diagnostics: LyricsVerificationDiagnostics
    timing_provenance: tuple[CorrectionTimingProvenance, ...] = ()

    @property
    def changed(self) -> bool:
        return self.diagnostics.accepted_corrections > 0


def verify_and_correct_whisperx(
    whisperx_result: Mapping[str, object],
    reference_text: str,
    audio_path: Path,
    aligner: ReferenceAligner,
) -> ProductionLyricsVerificationResult:
    reference_words = tokenize_reference(reference_text)
    asr_words = parse_whisperx_words(whisperx_result)
    alignment = align_words(asr_words, reference_words)
    verified_tokens = classify_alignment(alignment)
    raw_metrics = calculate_metrics(alignment)
    replacements: dict[int, TimedAsrWord] = {}
    touched_word_indices: set[int] = set()
    timing_provenance: list[CorrectionTimingProvenance] = []
    verified_candidates = 0
    forced_candidates = 0
    forced_successes = 0
    forced_failures = 0
    reconciliation_candidates = 0
    safety_rejections = 0
    asr_index = 0

    for alignment_index, (aligned, verified) in enumerate(
        zip(alignment, verified_tokens)
    ):
        current_asr_index = asr_index if aligned.asr_word is not None else None
        if aligned.asr_word is not None:
            asr_index += 1
        if not (
            aligned.operation is AlignmentOperation.SUBSTITUTION
            and verified.verification is VerificationState.VERIFIED_REFERENCE
        ):
            continue
        verified_candidates += 1
        context = select_forced_alignment_context(
            alignment,
            verified_tokens,
            alignment_index,
        )
        if context is None or current_asr_index is None:
            safety_rejections += 1
            continue
        forced_candidates += 1
        try:
            forced_result = aligner.align(audio_path, [context.segment])
        except Exception:
            forced_failures += 1
            continue
        candidate = _validated_forced_candidate(
            forced_result,
            context.segment,
            context.candidate_offset,
        )
        if candidate is None or aligned.reference_word is None:
            safety_rejections += 1
            continue
        forced_successes += 1
        corrected_candidate = TimedAsrWord(
            word=aligned.reference_word.display,
            start=candidate.start,
            end=candidate.end,
        )
        needs_reconciliation = _has_neighbor_overlap(
            corrected_candidate,
            asr_words,
            current_asr_index,
        )
        if needs_reconciliation:
            reconciliation_candidates += 1
        reconciled = _reconcile_timing(
            corrected_candidate,
            asr_words,
            current_asr_index,
            context.segment,
        )
        if reconciled is None:
            safety_rejections += 1
            continue
        replacement_updates, provenance = reconciled
        if touched_word_indices.intersection(replacement_updates):
            safety_rejections += 1
            continue
        touched_word_indices.update(replacement_updates)
        replacements.update(replacement_updates)
        timing_provenance.append(provenance)

    final_words = [
        replacements.get(index, word) for index, word in enumerate(asr_words)
    ]
    corrected_metrics = calculate_metrics(align_words(final_words, reference_words))
    corrected_result = (
        _replace_whisperx_words(whisperx_result, replacements)
        if replacements
        else whisperx_result
    )
    return ProductionLyricsVerificationResult(
        whisperx_result=corrected_result,
        diagnostics=LyricsVerificationDiagnostics(
            matches=raw_metrics.matches,
            substitutions=raw_metrics.substitutions,
            insertions=raw_metrics.insertions,
            deletions=raw_metrics.deletions,
            raw_wer=raw_metrics.wer,
            corrected_wer=corrected_metrics.wer,
            verified_candidates=verified_candidates,
            forced_alignment_candidates=forced_candidates,
            forced_alignment_successes=forced_successes,
            forced_alignment_failures=forced_failures,
            reconciliation_candidates=reconciliation_candidates,
            accepted_corrections=len(timing_provenance),
            rejected_corrections=verified_candidates - len(timing_provenance),
            safety_rejections=safety_rejections,
        ),
        timing_provenance=tuple(timing_provenance),
    )


def _has_neighbor_overlap(
    candidate: TimedAsrWord,
    original_words: Sequence[TimedAsrWord],
    word_index: int,
) -> bool:
    return bool(
        (word_index > 0 and candidate.start < original_words[word_index - 1].end)
        or (
            word_index + 1 < len(original_words)
            and candidate.end > original_words[word_index + 1].start
        )
    )


def _reconcile_timing(
    candidate: TimedAsrWord,
    original_words: Sequence[TimedAsrWord],
    word_index: int,
    context: ReferenceAlignmentSegment,
) -> tuple[dict[int, TimedAsrWord], CorrectionTimingProvenance] | None:
    previous = original_words[word_index - 1] if word_index > 0 else None
    following = (
        original_words[word_index + 1]
        if word_index + 1 < len(original_words)
        else None
    )
    previous_overlap = max(
        0.0,
        previous.end - candidate.start if previous is not None else 0.0,
    )
    next_overlap = max(
        0.0,
        candidate.end - following.start if following is not None else 0.0,
    )
    if previous_overlap > 0 and next_overlap > 0:
        return None
    if (
        previous_overlap > MAXIMUM_BOUNDARY_OVERLAP_SECONDS
        or next_overlap > MAXIMUM_BOUNDARY_OVERLAP_SECONDS
    ):
        return None
    if not _duration_is_sane(candidate) or not _inside_context(candidate, context):
        return None

    updates = {word_index: candidate}
    if previous_overlap > 0 and previous is not None:
        boundary = (previous.end + candidate.start) / 2
        adjusted_previous = TimedAsrWord(previous.word, previous.start, boundary)
        adjusted_candidate = TimedAsrWord(candidate.word, boundary, candidate.end)
        if not _neighbor_adjustment_is_safe(
            adjusted_previous,
            original_words,
            word_index - 1,
            context,
        ) or not _duration_is_sane(adjusted_candidate):
            return None
        updates[word_index - 1] = adjusted_previous
        updates[word_index] = adjusted_candidate
        return updates, CorrectionTimingProvenance(
            state=TimingProvenanceState.BOUNDARY_RECONCILED,
            word_index=word_index,
            forced_timing=candidate,
            final_timing=adjusted_candidate,
            previous_original=previous,
            previous_adjusted=adjusted_previous,
        )

    if next_overlap > 0 and following is not None:
        boundary = (candidate.end + following.start) / 2
        adjusted_candidate = TimedAsrWord(candidate.word, candidate.start, boundary)
        adjusted_next = TimedAsrWord(following.word, boundary, following.end)
        if not _neighbor_adjustment_is_safe(
            adjusted_next,
            original_words,
            word_index + 1,
            context,
        ) or not _duration_is_sane(adjusted_candidate):
            return None
        updates[word_index] = adjusted_candidate
        updates[word_index + 1] = adjusted_next
        return updates, CorrectionTimingProvenance(
            state=TimingProvenanceState.BOUNDARY_RECONCILED,
            word_index=word_index,
            forced_timing=candidate,
            final_timing=adjusted_candidate,
            next_original=following,
            next_adjusted=adjusted_next,
        )

    if not _chronological_with_neighbors(candidate, original_words, word_index):
        return None
    return updates, CorrectionTimingProvenance(
        state=TimingProvenanceState.EXACT_FORCED_ALIGNMENT,
        word_index=word_index,
        forced_timing=candidate,
        final_timing=candidate,
    )


def _neighbor_adjustment_is_safe(
    adjusted: TimedAsrWord,
    original_words: Sequence[TimedAsrWord],
    word_index: int,
    context: ReferenceAlignmentSegment,
) -> bool:
    return bool(
        _duration_is_sane(adjusted)
        and _inside_context(adjusted, context)
        and _chronological_with_neighbors(adjusted, original_words, word_index)
    )


def _chronological_with_neighbors(
    word: TimedAsrWord,
    original_words: Sequence[TimedAsrWord],
    word_index: int,
) -> bool:
    if word_index > 0 and word.start < original_words[word_index - 1].end:
        return False
    if (
        word_index + 1 < len(original_words)
        and word.end > original_words[word_index + 1].start
    ):
        return False
    return True


def _duration_is_sane(word: TimedAsrWord) -> bool:
    duration = word.end - word.start
    return MINIMUM_WORD_DURATION_SECONDS < duration <= MAXIMUM_WORD_DURATION_SECONDS


def _inside_context(
    word: TimedAsrWord,
    context: ReferenceAlignmentSegment,
) -> bool:
    return word.start >= context.start and word.end <= context.end


def _validated_forced_candidate(
    forced_result: Mapping[str, object],
    segment: ReferenceAlignmentSegment,
    candidate_offset: int,
) -> TimedAsrWord | None:
    words = parse_whisperx_words(forced_result)
    expected = tokenize_reference(segment.text)
    if len(words) != len(expected) or not 0 <= candidate_offset < len(words):
        return None
    if any(
        normalize_word(word.word) != reference.normalized
        for word, reference in zip(words, expected)
    ):
        return None
    candidate = words[candidate_offset]
    if (
        candidate.start < segment.start
        or candidate.end > segment.end
        or candidate.end <= candidate.start
        or candidate.end - candidate.start > 2.5
    ):
        return None
    if candidate_offset > 0 and words[candidate_offset - 1].end > candidate.start:
        return None
    if (
        candidate_offset + 1 < len(words)
        and candidate.end > words[candidate_offset + 1].start
    ):
        return None
    if any(
        current.start < previous.end
        for previous, current in zip(words, words[1:])
    ):
        return None
    return candidate


def _replace_whisperx_words(
    whisperx_result: Mapping[str, object],
    replacements: Mapping[int, TimedAsrWord],
) -> Mapping[str, object]:
    corrected = copy.deepcopy(dict(whisperx_result))
    word_index = 0
    for segment in corrected.get("segments", []):
        if not isinstance(segment, dict):
            continue
        segment_changed = False
        for word in segment.get("words", []):
            if not isinstance(word, dict):
                continue
            if "start" not in word or "end" not in word:
                continue
            if not normalize_word(str(word.get("word", "")).strip()):
                continue
            replacement = replacements.get(word_index)
            if replacement is not None:
                word["word"] = replacement.word
                word["start"] = replacement.start
                word["end"] = replacement.end
                segment_changed = True
            word_index += 1
        if segment_changed:
            segment["text"] = " ".join(
                str(word.get("word", "")).strip()
                for word in segment.get("words", [])
                if isinstance(word, dict) and str(word.get("word", "")).strip()
            )
    return corrected

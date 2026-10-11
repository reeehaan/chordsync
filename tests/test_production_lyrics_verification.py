
import pytest

from analysis.lyrics.production_verification import (
    MAXIMUM_BOUNDARY_OVERLAP_SECONDS,
    TimingProvenanceState,
    verify_and_correct_whisperx,
)


# Real WhisperX inference is nondeterministic across runs. These tests use
# synthetic word/timing inputs so regression expectations remain deterministic.


def _whisperx(*words):
    return {
        "language": "en",
        "segments": [
            {
                "start": 0.0,
                "end": len(words) * 0.5,
                "text": " ".join(words),
                "words": [
                    {
                        "word": word,
                        "start": index * 0.5,
                        "end": index * 0.5 + 0.4,
                    }
                    for index, word in enumerate(words)
                ],
            }
        ],
    }


def _forced(
    *words,
    candidate_start=0.92,
    candidate_end=1.18,
    previous_end=0.86,
    next_start=1.51,
):
    result = _whisperx(*words)
    timed_words = result["segments"][0]["words"]
    timings = [
        (0.02, 0.36),
        (0.51, previous_end),
        (candidate_start, candidate_end),
        (next_start, 1.86),
        (2.01, 2.36),
    ]
    for word, (start, end) in zip(timed_words, timings):
        word["start"] = start
        word["end"] = end
    return result


class FakeAligner:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def align(self, audio_path, segments):
        self.calls.append((audio_path, segments))
        if self.error is not None:
            raise self.error
        return self.result


def _display_words(result):
    return [
        word["word"]
        for segment in result["segments"]
        for word in segment["words"]
    ]


def test_exact_match_has_zero_corrections(tmp_path):
    whisperx = _whisperx("silver", "birds", "cross", "quiet", "skies")
    aligner = FakeAligner()

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.whisperx_result is whisperx
    assert result.diagnostics.matches == 5
    assert result.diagnostics.verified_candidates == 0
    assert result.diagnostics.forced_alignment_successes == 0
    assert aligner.calls == []


def test_isolated_verified_substitution_gets_reference_text_and_fresh_timing(
    tmp_path,
):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced("silver", "birds", "cross", "quiet", "skies")
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )
    corrected = result.whisperx_result["segments"][0]["words"][2]

    assert corrected == {"word": "cross", "start": 0.92, "end": 1.18}
    assert result.whisperx_result["segments"][0]["text"] == (
        "silver birds cross quiet skies"
    )
    assert whisperx["segments"][0]["words"][2] == {
        "word": "crest",
        "start": 1.0,
        "end": 1.4,
    }
    assert result.diagnostics.substitutions == 1
    assert result.diagnostics.verified_candidates == 1
    assert result.diagnostics.forced_alignment_successes == 1
    assert result.diagnostics.accepted_corrections == 1
    assert result.diagnostics.raw_wer == pytest.approx(0.2)
    assert result.diagnostics.corrected_wer == 0
    assert result.timing_provenance[0].state is (
        TimingProvenanceState.EXACT_FORCED_ALIGNMENT
    )


def test_small_previous_overlap_reconciles_shared_boundary(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.87,
            candidate_end=1.18,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )
    words = result.whisperx_result["segments"][0]["words"]
    provenance = result.timing_provenance[0]

    assert words[1]["end"] == pytest.approx(0.885)
    assert words[2]["start"] == pytest.approx(0.885)
    assert provenance.state is TimingProvenanceState.BOUNDARY_RECONCILED
    assert provenance.previous_original.end == 0.9
    assert provenance.previous_adjusted.end == pytest.approx(0.885)
    assert provenance.forced_timing.start == 0.87
    assert provenance.final_timing.start == pytest.approx(0.885)
    assert result.diagnostics.reconciliation_candidates == 1
    assert result.diagnostics.accepted_corrections == 1
    assert words[0] == whisperx["segments"][0]["words"][0]
    assert words[3:] == whisperx["segments"][0]["words"][3:]


def test_zero_overlap_accepts_exact_forced_timing_unchanged(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.9,
            candidate_end=1.18,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    provenance = result.timing_provenance[0]
    assert provenance.state is TimingProvenanceState.EXACT_FORCED_ALIGNMENT
    assert provenance.forced_timing == provenance.final_timing
    assert result.diagnostics.reconciliation_candidates == 0


def test_small_next_overlap_reconciles_shared_boundary(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.92,
            candidate_end=1.53,
            next_start=1.55,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )
    words = result.whisperx_result["segments"][0]["words"]
    provenance = result.timing_provenance[0]

    assert words[2]["end"] == pytest.approx(1.515)
    assert words[3]["start"] == pytest.approx(1.515)
    assert provenance.state is TimingProvenanceState.BOUNDARY_RECONCILED
    assert provenance.next_original.start == 1.5
    assert provenance.next_adjusted.start == pytest.approx(1.515)


def test_both_side_overlap_is_rejected_to_avoid_cascading_edits(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.87,
            candidate_end=1.53,
            previous_end=0.86,
            next_start=1.55,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.whisperx_result is whisperx
    assert result.diagnostics.reconciliation_candidates == 1
    assert result.diagnostics.accepted_corrections == 0
    assert result.diagnostics.safety_rejections == 1


def test_overlap_just_below_tolerance_is_accepted(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    start = 0.9 - MAXIMUM_BOUNDARY_OVERLAP_SECONDS + 0.000001
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=start,
            candidate_end=1.18,
            previous_end=start - 0.01,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.diagnostics.accepted_corrections == 1
    assert result.timing_provenance[0].state is (
        TimingProvenanceState.BOUNDARY_RECONCILED
    )


def test_overlap_above_tolerance_is_rejected(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.79,
            candidate_end=1.18,
            previous_end=0.78,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.diagnostics.forced_alignment_successes == 1
    assert result.diagnostics.accepted_corrections == 0
    assert result.diagnostics.safety_rejections == 1


def test_reconciliation_that_zeros_neighbor_duration_is_rejected(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    whisperx["segments"][0]["words"][1].update(start=0.85, end=0.9)
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.8,
            candidate_end=1.18,
            previous_end=0.79,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.diagnostics.accepted_corrections == 0
    assert result.diagnostics.safety_rejections == 1


def test_non_monotonic_forced_timing_is_rejected(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=0.8,
            candidate_end=1.18,
            previous_end=0.86,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.diagnostics.forced_alignment_successes == 0
    assert result.diagnostics.accepted_corrections == 0


def test_cascading_original_overlap_is_rejected_before_alignment(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    whisperx["segments"][0]["words"][0]["end"] = 0.6
    aligner = FakeAligner(
        _forced("silver", "birds", "cross", "quiet", "skies")
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert result.diagnostics.accepted_corrections == 0
    assert result.diagnostics.safety_rejections == 1
    assert aligner.calls == []


def test_repeated_section_ambiguity_keeps_original_word(tmp_path):
    whisperx = _whisperx(
        "silver", "birds", "crest", "quiet", "skies",
        "silver", "birds", "cross", "quiet", "skies",
    )
    aligner = FakeAligner(
        _forced("silver", "birds", "cross", "quiet", "skies")
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert _display_words(result.whisperx_result)[2] == "crest"
    assert result.diagnostics.forced_alignment_successes == 0
    assert aligner.calls == []


def test_forced_alignment_failure_keeps_original_word(tmp_path):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(error=RuntimeError("alignment unavailable"))

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert _display_words(result.whisperx_result)[2] == "crest"
    assert result.diagnostics.forced_alignment_failures == 1
    assert result.diagnostics.forced_alignment_successes == 0


@pytest.mark.parametrize(
    ("start", "end"),
    [(1.2, 1.1), (-0.1, 0.2), (0.9, 3.6), (0.8, 1.6)],
)
def test_invalid_corrected_timing_keeps_original_word(tmp_path, start, end):
    whisperx = _whisperx("silver", "birds", "crest", "quiet", "skies")
    aligner = FakeAligner(
        _forced(
            "silver", "birds", "cross", "quiet", "skies",
            candidate_start=start,
            candidate_end=end,
        )
    )

    result = verify_and_correct_whisperx(
        whisperx,
        "silver birds cross quiet skies",
        tmp_path / "audio.wav",
        aligner,
    )

    assert _display_words(result.whisperx_result)[2] == "crest"
    assert result.diagnostics.safety_rejections == 1
    assert result.diagnostics.forced_alignment_successes == 0

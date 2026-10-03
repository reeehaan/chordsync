import sys
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from analysis.lyrics.forced_alignment import (
    ReferenceAlignmentSegment,
    WhisperXReferenceAligner,
)
from analysis.lyrics.lyrics_reference import (
    LocalLyricsReferenceSource,
    LyricsReferenceNotFoundError,
    SongIdentity,
)
from analysis.lyrics.lyrics_verification import (
    AlignmentOperation,
    LyricsVerifier,
    VerificationState,
    align_words,
    calculate_metrics,
    normalize_word,
    parse_whisperx_words,
    tokenize_reference,
)


IDENTITY = SongIdentity(title="Paper Moons", artist="Example Ensemble")


class SyntheticReferenceSource:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requested_identity = None

    def get_lyrics(self, song_identity: SongIdentity) -> str:
        self.requested_identity = song_identity
        return self.text


def _whisperx(*words: str) -> dict:
    return {
        "language": "en",
        "segments": [
            {
                "text": " ".join(words),
                "words": [
                    {"word": word, "start": index * 0.5, "end": index * 0.5 + 0.4}
                    for index, word in enumerate(words)
                ],
            }
        ],
    }


def _verify(reference: str, *asr_words: str):
    return LyricsVerifier(SyntheticReferenceSource(reference)).verify(
        IDENTITY,
        _whisperx(*asr_words),
    )


def test_exact_match_is_verified_and_has_zero_wer():
    result = _verify("silver birds cross quiet skies", "silver", "birds", "cross", "quiet", "skies")

    assert all(
        token.verification is VerificationState.VERIFIED_REFERENCE
        for token in result.tokens
    )
    assert result.raw_metrics.matches == 5
    assert result.raw_metrics.wer == 0.0
    assert result.corrected_metrics.wer == 0.0


def test_isolated_substitution_uses_reference_spelling_but_not_asr_timing():
    result = _verify("silver birds cross quiet skies", "silver", "birds", "crest", "quiet", "skies")
    token = result.tokens[2]

    assert token.operation is AlignmentOperation.SUBSTITUTION
    assert token.display_word == "cross"
    assert token.asr_word == "crest"
    assert token.reference_word == "cross"
    assert token.verification is VerificationState.VERIFIED_REFERENCE
    assert token.start is None
    assert token.end is None
    assert result.raw_metrics.substitutions == 1
    assert result.raw_metrics.wer == pytest.approx(0.2)
    assert result.corrected_metrics.wer == 0.0


def test_non_interjection_insertion_is_uncertain_and_counted_in_wer():
    result = _verify("silver birds cross skies", "silver", "birds", "bright", "cross", "skies")
    inserted = next(
        token for token in result.tokens if token.operation is AlignmentOperation.INSERTION
    )

    assert inserted.verification is VerificationState.UNCERTAIN
    assert result.raw_metrics.insertions == 1
    assert result.raw_metrics.wer == pytest.approx(0.25)


def test_deletion_is_explicit_uncertain_and_has_no_timing():
    result = _verify("silver birds cross quiet skies", "silver", "birds", "quiet", "skies")
    deleted = next(
        token for token in result.tokens if token.operation is AlignmentOperation.DELETION
    )

    assert deleted.reference_word == "cross"
    assert deleted.asr_word is None
    assert deleted.verification is VerificationState.UNCERTAIN
    assert deleted.start is None
    assert result.raw_metrics.deletions == 1


def test_punctuation_case_and_apostrophes_normalize_for_comparison():
    result = _verify("We’ll build, PAPER moons!", "wewill", "build", "paper", "moons")

    assert normalize_word("We’ll") == normalize_word("wewill")
    assert normalize_word("can't") == normalize_word("cannot")
    assert normalize_word("we'll") != normalize_word("well")
    assert result.raw_metrics.matches == 4
    assert result.raw_metrics.wer == 0.0
    assert result.tokens[0].display_word == "We’ll"


def test_repeated_word_ambiguity_remains_uncertain():
    result = _verify("drift drift toward dawn", "drift", "toward", "dawn")

    ambiguous = next(
        token for token in result.tokens if token.operation is AlignmentOperation.DELETION
    )
    assert ambiguous.verification is VerificationState.UNCERTAIN


def test_adjacent_substitutions_are_not_auto_corrected():
    result = _verify("silver birds cross quiet skies", "silver", "birds", "turn", "softly", "skies")

    mismatches = [
        token
        for token in result.tokens
        if token.operation is AlignmentOperation.SUBSTITUTION
    ]
    assert len(mismatches) == 2
    assert all(
        token.verification is VerificationState.UNCERTAIN
        for token in mismatches
    )


def test_locally_coherent_interjection_is_preserved_as_asr_only():
    result = _verify("silver birds cross skies", "silver", "birds", "oh", "cross", "skies")
    interjection = next(
        token for token in result.tokens if token.operation is AlignmentOperation.INSERTION
    )

    assert interjection.display_word == "oh"
    assert interjection.reference_word is None
    assert interjection.verification is VerificationState.ASR_ONLY
    assert interjection.start is not None


def test_metrics_report_all_alignment_operations():
    asr = parse_whisperx_words(_whisperx("silver", "extra", "wrong"))
    reference = tokenize_reference("silver right missing")
    alignment = align_words(asr, reference)
    metrics = calculate_metrics(alignment)

    assert metrics.matches == 1
    assert metrics.substitutions == 2
    assert metrics.insertions == 0
    assert metrics.deletions == 0
    assert metrics.wer == pytest.approx(2 / 3)


def test_verifier_uses_reference_source_abstraction():
    source = SyntheticReferenceSource("silver birds")

    result = LyricsVerifier(source).verify(IDENTITY, _whisperx("silver", "birds"))

    assert source.requested_identity == IDENTITY
    assert result.song_identity == IDENTITY


def test_local_reference_source_uses_stable_song_identity(tmp_path):
    identity = SongIdentity(
        title="Paper Moons",
        artist="Example Ensemble",
        album="Synthetic Sessions",
        version="Acoustic Demo",
    )
    reference_path = tmp_path / "example-ensemble-paper-moons-acoustic-demo.txt"
    reference_path.write_text("silver birds cross quiet skies", encoding="utf-8")

    text = LocalLyricsReferenceSource(tmp_path).get_lyrics(identity)

    assert identity.album == "Synthetic Sessions"
    assert text == "silver birds cross quiet skies"


def test_missing_local_reference_fails_cleanly(tmp_path):
    with pytest.raises(LyricsReferenceNotFoundError, match="No local lyrics reference"):
        LocalLyricsReferenceSource(tmp_path).get_lyrics(IDENTITY)


def test_forced_aligner_passes_corrected_text_to_whisperx(monkeypatch, tmp_path):
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"synthetic audio placeholder")
    observed = {}

    def fake_load_align_model(*, language_code, device):
        observed["load"] = (language_code, device)
        return "model", {"language": language_code}

    def fake_align(transcript, model, metadata, audio_path, device, **kwargs):
        observed["align"] = (transcript, model, metadata, audio_path, device, kwargs)
        return {
            "segments": transcript,
            "word_segments": [
                {"word": "silver", "start": 0.1, "end": 0.4}
            ],
        }

    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        SimpleNamespace(
            load_align_model=fake_load_align_model,
            align=fake_align,
        ),
    )

    result = WhisperXReferenceAligner().align(
        audio,
        [ReferenceAlignmentSegment("silver birds", 0.0, 1.0)],
    )

    assert observed["load"] == ("en", "cpu")
    assert observed["align"][0] == [
        {"text": "silver birds", "start": 0.0, "end": 1.0}
    ]
    assert observed["align"][3] == str(audio)
    assert result["word_segments"][0]["start"] == 0.1


def test_forced_aligner_can_use_dedicated_python_environment(
    monkeypatch,
    tmp_path,
):
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"synthetic audio placeholder")
    python = tmp_path / "lyrics-python"
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed["kwargs"] = kwargs
        request_path = Path(argv[argv.index("--request") + 1])
        output_path = Path(argv[argv.index("--output") + 1])
        observed["request"] = json.loads(request_path.read_text(encoding="utf-8"))
        output_path.write_text(
            json.dumps({"segments": [{"words": []}]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(
        "analysis.lyrics.forced_alignment.subprocess.run",
        fake_run,
    )
    result = WhisperXReferenceAligner(
        python_executable=python,
        repo_root=tmp_path,
        timeout_seconds=17,
    ).align(
        audio,
        [ReferenceAlignmentSegment("silver birds", 0.0, 1.0)],
    )

    assert observed["argv"][:3] == [
        str(python),
        "-m",
        "analysis.lyrics.reference_alignment_cli",
    ]
    assert observed["kwargs"]["cwd"] == tmp_path
    assert observed["kwargs"]["timeout"] == 17
    assert observed["kwargs"]["shell"] is False
    assert observed["request"]["segments"] == [
        {"text": "silver birds", "start": 0.0, "end": 1.0}
    ]
    assert result == {"segments": [{"words": []}]}

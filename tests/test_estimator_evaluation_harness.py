import json

from analysis.chords.models import ChordSegment
from analysis.evaluation.estimator_harness import evaluate_track
from analysis.evaluation.models import EvaluationTrack


def segment(start, end, label, source):
    return ChordSegment(
        start=start,
        end=end,
        raw_label=label,
        normalized_label="deliberately-ignored",
        source=source,
    )


def test_harness_preprocesses_once_and_compares_both_against_same_reference(
    tmp_path,
):
    audio = tmp_path / "input.wav"
    reference = tmp_path / "reference.lab"
    audio.write_bytes(b"original")
    reference.write_text("0 1 C:maj\n1 2 A:min\n", encoding="utf-8")
    observed = {"preprocessing": 0, "inputs": [], "audio": []}

    def preprocess(input_path, output_path):
        observed["preprocessing"] += 1
        assert input_path == audio
        output_path.write_bytes(b"normalized")

    def chordino(input_path):
        observed["inputs"].append(input_path)
        observed["audio"].append(input_path.read_bytes())
        return [segment(0, 1, "C", "chordino"), segment(1, 2, "Am", "chordino")]

    def btc(input_path):
        observed["inputs"].append(input_path)
        observed["audio"].append(input_path.read_bytes())
        return [segment(0, 1, "G", "btc"), segment(1, 2, "A:min", "btc")]

    result = evaluate_track(
        EvaluationTrack(
            track_id="synthetic-two-chords",
            audio_path=audio,
            reference_lab_path=reference,
        ),
        chordino_estimator=chordino,
        btc_estimator=btc,
        preprocessor=preprocess,
        chordino_version="test-chordino",
        btc_version="test-btc",
        btc_checkpoint_sha256="abc123",
    )

    assert observed["preprocessing"] == 1
    assert observed["inputs"][0] == observed["inputs"][1]
    assert observed["audio"] == [b"normalized", b"normalized"]
    assert result.track_id == "synthetic-two-chords"
    assert result.duration == 2.0
    assert result.chordino.root_score == 1.0
    assert result.btc.root_score == 0.5
    assert result.chordino.segment_count == 2
    assert result.btc.segment_count == 2
    assert result.chordino.version == "test-chordino"
    assert result.btc.checkpoint_sha256 == "abc123"


def test_comparison_json_is_stable_and_contains_no_local_paths(tmp_path):
    audio = tmp_path / "private-name.wav"
    reference = tmp_path / "private-reference.lab"
    audio.write_bytes(b"audio")
    reference.write_text("0 1 C\n", encoding="utf-8")

    def preprocess(input_path, output_path):
        output_path.write_bytes(input_path.read_bytes())

    def estimator(source):
        return lambda _: [segment(0, 1, "C:maj", source)]

    result = evaluate_track(
        EvaluationTrack(
            track_id="safe-track-id",
            audio_path=audio,
            reference_lab_path=reference,
        ),
        chordino_estimator=estimator("chordino"),
        btc_estimator=estimator("btc"),
        preprocessor=preprocess,
        chordino_version="baseline-v1",
        btc_version="candidate-v1",
        btc_checkpoint_sha256="checksum",
    )
    payload = json.loads(result.model_dump_json())

    assert list(payload) == [
        "track_id",
        "duration",
        "preprocessing_seconds",
        "normalization",
        "chordino",
        "btc",
    ]
    assert list(payload["chordino"]) == [
        "estimator",
        "version",
        "duration",
        "root_score",
        "majmin_score",
        "triad_score",
        "no_chord",
        "runtime_seconds",
        "runtime_scope",
        "segment_count",
        "checkpoint_sha256",
    ]
    serialized = result.model_dump_json()
    assert "private-name" not in serialized
    assert "private-reference" not in serialized

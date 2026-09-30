import pytest

from analysis.evaluation.strumming_validation import (
    HUMAN_QUESTION,
    build_review_manifest,
    evaluate_review_manifest,
    validate_review_manifest,
)


def _item(identifier, song, prediction, label="UNLABELED"):
    return {
        "id": identifier,
        "song": song,
        "start": 10.0,
        "end": 18.0,
        "duration": 8.0,
        "raw_state": prediction,
        "consolidated_state": prediction,
        "evidence": {
            "model_uncertainty": "NORMAL",
            "structural_instability": "NORMAL",
            "section_consistency": "NORMAL",
            "estimator_disagreement": "NORMAL",
        },
        "human_label": label,
        "human_note": "",
        "human_question": HUMAN_QUESTION,
    }


def test_builds_manifest_with_safe_human_review_defaults():
    item = _item("R01", "Example", "PLAY_CHORD")
    del item["human_label"]
    del item["human_note"]
    del item["human_question"]

    result = build_review_manifest([item], checkpoint="abc123")

    assert result["items"][0]["human_label"] == "UNLABELED"
    assert result["items"][0]["human_note"] == ""
    assert result["items"][0]["human_question"] == HUMAN_QUESTION


def test_manifest_accepts_portable_logical_clip_identifier():
    item = _item("R01", "Example", "PLAY_CHORD")
    item["clip_id"] = "R01.m4a"

    result = build_review_manifest([item], checkpoint="abc123")

    assert result["items"][0]["clip_id"] == "R01.m4a"


def test_rejects_invalid_human_label():
    manifest = build_review_manifest(
        [_item("R01", "Example", "PLAY_CHORD")], checkpoint="abc123"
    )
    manifest["items"][0]["human_label"] = "INSTRUMENTAL"

    with pytest.raises(ValueError, match="invalid human label"):
        validate_review_manifest(manifest)


def test_calculates_metrics_from_synthetic_human_labels():
    manifest = build_review_manifest(
        [
            _item("R01", "A", "MUSIC_ONLY", "MUSIC_ONLY"),
            _item("R02", "A", "MUSIC_ONLY", "PLAY_CHORD"),
            _item("R03", "B", "UNCERTAIN", "MUSIC_ONLY"),
            _item("R04", "B", "PLAY_CHORD", "PLAY_CHORD"),
        ],
        checkpoint="abc123",
    )

    result = evaluate_review_manifest(manifest)

    assert result["music_only_precision"] == pytest.approx(0.5)
    assert result["music_only_recall"] == pytest.approx(0.5)
    assert result["play_chord_false_suppression_rate"] == pytest.approx(0.5)
    assert result["uncertain_rate"] == pytest.approx(0.25)
    assert result["false_positive_music_only_count"] == 1
    assert result["false_negative_music_only_count"] == 1


def test_unlabelled_items_are_excluded_from_scoring():
    manifest = build_review_manifest(
        [
            _item("R01", "A", "MUSIC_ONLY", "PLAY_CHORD"),
            _item("R02", "A", "MUSIC_ONLY"),
        ],
        checkpoint="abc123",
    )

    result = evaluate_review_manifest(manifest)

    assert result["labelled_count"] == 1
    assert result["false_positive_music_only_count"] == 1
    assert evaluate_review_manifest(
        build_review_manifest(
            [_item("R03", "A", "UNCERTAIN")], checkpoint="abc123"
        )
    ) is None


def test_reports_per_song_metrics():
    manifest = build_review_manifest(
        [
            _item("R01", "A", "MUSIC_ONLY", "MUSIC_ONLY"),
            _item("R02", "B", "PLAY_CHORD", "MUSIC_ONLY"),
            _item("R03", "B", "UNCERTAIN", "PLAY_CHORD"),
        ],
        checkpoint="abc123",
    )

    result = evaluate_review_manifest(manifest)

    assert result["per_song"]["A"]["music_only_recall"] == 1.0
    assert result["per_song"]["B"]["music_only_recall"] == 0.0
    assert result["per_song"]["B"]["uncertain_rate"] == pytest.approx(0.5)

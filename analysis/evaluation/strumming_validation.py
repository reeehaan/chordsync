"""Offline manifest and scoring helpers for strumming-suitability review.

This module is diagnostic-only. It deliberately keeps human labels separate
from classifier predictions and is not imported by the production pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping


LABELS = {"PLAY_CHORD", "MUSIC_ONLY", "UNCERTAIN", "UNLABELED"}
PREDICTIONS = {"PLAY_CHORD", "MUSIC_ONLY", "UNCERTAIN"}
HUMAN_QUESTION = (
    "Should a beginner guitarist be expected to strum chords through this section?"
)


def build_review_manifest(
    items: Iterable[Mapping[str, Any]],
    *,
    checkpoint: str,
) -> dict[str, Any]:
    """Build and validate an offline human-review manifest."""
    manifest = {
        "schema_version": 1,
        "task": "S5-T16B3",
        "checkpoint": checkpoint,
        "human_question": HUMAN_QUESTION,
        "items": [dict(item) for item in items],
    }
    for item in manifest["items"]:
        item.setdefault("human_label", "UNLABELED")
        item.setdefault("human_note", "")
        item.setdefault("human_question", HUMAN_QUESTION)
    validate_review_manifest(manifest)
    return manifest


def validate_review_manifest(manifest: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` when a review manifest is not safe to score."""
    items = manifest.get("items")
    if not isinstance(items, list):
        raise ValueError("manifest items must be a list")
    seen_ids = set()
    required = {
        "id",
        "song",
        "start",
        "end",
        "duration",
        "raw_state",
        "consolidated_state",
        "evidence",
        "human_label",
        "human_note",
        "human_question",
    }
    for item in items:
        missing = required - set(item)
        if missing:
            raise ValueError(f"review item is missing fields: {sorted(missing)}")
        if item["id"] in seen_ids:
            raise ValueError(f"duplicate review item id: {item['id']}")
        seen_ids.add(item["id"])
        if float(item["end"]) <= float(item["start"]):
            raise ValueError(f"review item {item['id']} has an invalid interval")
        expected_duration = float(item["end"]) - float(item["start"])
        if abs(float(item["duration"]) - expected_duration) > 0.02:
            raise ValueError(f"review item {item['id']} has an invalid duration")
        if item["raw_state"] not in PREDICTIONS:
            raise ValueError(f"invalid raw state: {item['raw_state']}")
        if item["consolidated_state"] not in PREDICTIONS:
            raise ValueError(
                f"invalid consolidated state: {item['consolidated_state']}"
            )
        if item["human_label"] not in LABELS:
            raise ValueError(f"invalid human label: {item['human_label']}")
        if not isinstance(item["evidence"], Mapping):
            raise ValueError(f"review item {item['id']} evidence must be an object")


def evaluate_review_manifest(manifest: Mapping[str, Any]) -> dict[str, Any] | None:
    """Score only human-labelled items; return ``None`` when none are labelled."""
    validate_review_manifest(manifest)
    labelled = [
        item for item in manifest["items"] if item["human_label"] != "UNLABELED"
    ]
    if not labelled:
        return None
    return {
        **_score_items(labelled),
        "per_song": {
            song: _score_items(song_items)
            for song, song_items in sorted(_group_by_song(labelled).items())
        },
    }


def _score_items(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    true_music = sum(item["human_label"] == "MUSIC_ONLY" for item in items)
    predicted_music = sum(
        item["consolidated_state"] == "MUSIC_ONLY" for item in items
    )
    true_positive = sum(
        item["human_label"] == "MUSIC_ONLY"
        and item["consolidated_state"] == "MUSIC_ONLY"
        for item in items
    )
    false_positive = sum(
        item["human_label"] != "MUSIC_ONLY"
        and item["consolidated_state"] == "MUSIC_ONLY"
        for item in items
    )
    false_negative = sum(
        item["human_label"] == "MUSIC_ONLY"
        and item["consolidated_state"] != "MUSIC_ONLY"
        for item in items
    )
    playable = sum(item["human_label"] == "PLAY_CHORD" for item in items)
    false_suppression = sum(
        item["human_label"] == "PLAY_CHORD"
        and item["consolidated_state"] == "MUSIC_ONLY"
        for item in items
    )
    uncertain = sum(
        item["consolidated_state"] == "UNCERTAIN" for item in items
    )
    return {
        "labelled_count": len(items),
        "music_only_precision": _ratio(true_positive, predicted_music),
        "music_only_recall": _ratio(true_positive, true_music),
        "play_chord_false_suppression_rate": _ratio(false_suppression, playable),
        "uncertain_rate": uncertain / len(items),
        "false_positive_music_only_count": false_positive,
        "false_negative_music_only_count": false_negative,
    }


def _group_by_song(items):
    grouped = defaultdict(list)
    for item in items:
        grouped[item["song"]].append(item)
    return grouped


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None

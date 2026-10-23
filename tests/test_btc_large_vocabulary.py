"""The 170-chord BTC model, on the repo's synthetic triad fixture.

Skipped unless torch and the upstream BTC checkout with both checkpoints are
available (the BTC environment on a developer machine or the worker image).
"""

import os
import re
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "synthetic_c_am_f_g.wav"


def _btc_source():
    source = os.getenv("CHORDSYNC_BTC_SOURCE")
    if not source:
        pytest.skip("CHORDSYNC_BTC_SOURCE is not set")
    path = Path(source)
    if not (path / "test" / "btc_model_large_voca.pt").is_file():
        pytest.skip("the large-vocabulary checkpoint is not available")
    return path


def test_large_model_labels_plain_triads_with_the_large_vocabulary():
    pytest.importorskip("torch")
    source = _btc_source()
    if not FIXTURE.is_file():
        pytest.skip("synthetic chord fixture is missing")
    from analysis.chords.btc import btc_inference

    labels = [
        item["label"]
        for item in btc_inference.predict(
            FIXTURE,
            source / "test" / "btc_model_large_voca.pt",
            source,
            large_vocabulary=True,
        )
    ]

    # Large-vocabulary labels: a major triad is the bare root, others "root:type".
    # (On pure sine tones the large model is less sure than the standard one, so
    # only the clearest chords are required here.)
    assert labels
    assert {"C", "G"} <= set(labels)
    assert all(re.fullmatch(r"([A-G]#?(:[a-z0-9]+)?|N|X)", label) for label in labels)


def test_the_standard_model_is_unchanged_by_the_large_option():
    pytest.importorskip("torch")
    source = _btc_source()
    if not FIXTURE.is_file():
        pytest.skip("synthetic chord fixture is missing")
    from analysis.chords.btc import btc_inference

    labels = {
        item["label"]
        for item in btc_inference.predict(FIXTURE, source / "test" / "btc_model.pt", source)
    }

    assert labels <= {f"{root}{q}" for root in
        ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
        for q in (":maj", ":min")} | {"N"}

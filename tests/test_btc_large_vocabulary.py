"""The 170-chord BTC model, on the repo's synthetic triad fixture.

The model runs in a separate process with the BTC environment's Python, so these
tests never load torch into the test process (other tests check that it is not
loaded). Skipped unless CHORDSYNC_BTC_PYTHON, CHORDSYNC_BTC_SOURCE and both
checkpoints are available (a developer machine or the worker image).
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "audio" / "synthetic_c_am_f_g.wav"

_SCRIPT = """
import json, sys
from pathlib import Path
from analysis.chords.btc import btc_inference
audio, checkpoint, source, large = sys.argv[1:5]
labels = [p["label"] for p in btc_inference.predict(
    Path(audio), Path(checkpoint), Path(source), large_vocabulary=(large == "1"))]
print(json.dumps(labels))
"""


def _labels(checkpoint_name: str, *, large: bool) -> list[str]:
    python = os.getenv("CHORDSYNC_BTC_PYTHON")
    source = os.getenv("CHORDSYNC_BTC_SOURCE")
    if not python or not source or not Path(python).is_file():
        pytest.skip("the BTC environment is not configured")
    checkpoint = Path(source) / "test" / checkpoint_name
    if not checkpoint.is_file() or not FIXTURE.is_file():
        pytest.skip(f"{checkpoint_name} or the synthetic fixture is not available")
    result = subprocess.run(
        [python, "-c", _SCRIPT, str(FIXTURE), str(checkpoint), source, "1" if large else "0"],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_large_model_labels_plain_triads_with_the_large_vocabulary():
    labels = _labels("btc_model_large_voca.pt", large=True)

    # Large-vocabulary labels: a major triad is the bare root, others "root:type".
    # (On pure sine tones the large model is less sure than the standard one, so
    # only the clearest chords are required here.)
    assert labels
    assert {"C", "G"} <= set(labels)
    assert all(re.fullmatch(r"([A-G]#?(:[a-z0-9]+)?|N|X)", label) for label in labels)


def test_the_standard_model_is_unchanged_by_the_large_option():
    labels = set(_labels("btc_model.pt", large=False))

    roots = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    assert labels <= {f"{root}{quality}" for root in roots for quality in (":maj", ":min")} | {"N"}

from pathlib import Path

import pytest

from analysis.chords.chordino.chordino_runner import (
    events_to_segments,
    get_sonic_annotator_path,
    get_vamp_simple_host_path,
    parse_chordino_csv,
    run_chordino,
    SonicAnnotatorNotFoundError,
)
from analysis.chords.models import ChordSegment


def test_configured_sonic_annotator_path_is_used(monkeypatch, tmp_path):
    executable = tmp_path / "sonic-annotator"
    executable.write_text("fake executable", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("CHORDSYNC_SONIC_ANNOTATOR", str(executable))

    assert get_sonic_annotator_path() == executable


def test_sonic_annotator_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_SONIC_ANNOTATOR", raising=False)
    monkeypatch.delenv("SONIC_ANNOTATOR_PATH", raising=False)
    monkeypatch.setattr(
        "analysis.chords.chordino.chordino_runner.shutil.which",
        lambda command: "/portable/bin/sonic-annotator",
    )

    assert get_sonic_annotator_path() == Path("/portable/bin/sonic-annotator")


def test_missing_sonic_annotator_fails_clearly(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_SONIC_ANNOTATOR", raising=False)
    monkeypatch.delenv("SONIC_ANNOTATOR_PATH", raising=False)
    monkeypatch.setattr(
        "analysis.chords.chordino.chordino_runner.shutil.which",
        lambda command: None,
    )

    with pytest.raises(SonicAnnotatorNotFoundError, match="not configured"):
        get_sonic_annotator_path()


def test_run_chordino_falls_back_to_vamp_simple_host(monkeypatch, tmp_path):
    audio = tmp_path / "normalized.wav"
    audio.write_bytes(b"audio")
    executable = tmp_path / "vamp-simple-host"
    executable.write_text("fake executable", encoding="utf-8")
    executable.chmod(0o755)
    observed = {}

    monkeypatch.setattr(
        "analysis.chords.chordino.chordino_runner.get_sonic_annotator_path",
        lambda: (_ for _ in ()).throw(SonicAnnotatorNotFoundError()),
    )
    monkeypatch.setattr(
        "analysis.chords.chordino.chordino_runner.get_vamp_simple_host_path",
        lambda: executable,
    )

    def fake_fallback(audio_path, *, executable):
        observed["audio_path"] = audio_path
        observed["executable"] = executable
        return [
            ChordSegment(
                start=0,
                end=1,
                raw_label="C:maj",
                normalized_label="C",
                source="chordino-diagnostic",
            )
        ]

    monkeypatch.setattr(
        "analysis.chords.chordino.vamp_simple_host_runner.run_chordino_diagnostic",
        fake_fallback,
    )

    chords = run_chordino(audio)

    assert observed == {"audio_path": audio, "executable": executable}
    assert [chord.source for chord in chords] == ["chordino"]


def test_vamp_simple_host_falls_back_to_path_lookup(monkeypatch):
    monkeypatch.delenv("CHORDSYNC_VAMP_SIMPLE_HOST", raising=False)
    monkeypatch.setattr(
        "analysis.chords.chordino.chordino_runner.shutil.which",
        lambda command: "/portable/bin/vamp-simple-host",
    )

    assert get_vamp_simple_host_path() == Path("/portable/bin/vamp-simple-host")


def test_parse_chordino_csv():
    csv_data = """test.wav,0.000000000,N
test.wav,1.500000000,C
test.wav,3.000000000,G
"""

    events = parse_chordino_csv(csv_data)

    assert len(events) == 3
    assert events[0]["label"] == "N"
    assert events[1]["label"] == "C"
    assert events[2]["time"] == 3.0


def test_events_to_segments():
    events = [
        {"time": 0.0, "label": "N"},
        {"time": 1.5, "label": "C"},
        {"time": 3.0, "label": "G"},
    ]

    segments = events_to_segments(
        events,
        duration=5.0,
    )

    assert len(segments) == 3

    assert segments[0].start == 0.0
    assert segments[0].end == 1.5
    assert segments[0].raw_label == "N"
    assert segments[0].normalized_label == "N"
    assert segments[0].source == "chordino"

    assert segments[1].start == 1.5
    assert segments[1].end == 3.0
    assert segments[1].raw_label == "C"
    assert segments[1].normalized_label == "C"
    assert segments[1].source == "chordino"

    assert segments[2].start == 3.0
    assert segments[2].end == 5.0
    assert segments[2].raw_label == "G"
    assert segments[2].normalized_label == "G"
    assert segments[2].source == "chordino"

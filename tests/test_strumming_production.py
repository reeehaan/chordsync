import subprocess
import wave

from analysis.beats.models import BeatEvent, BeatGrid
from analysis.chords.chordino.vamp_simple_host_runner import (
    run_chordino_diagnostic,
)
from analysis.chords.models import ChordSegment
from analysis.evaluation.btc_uncertainty import BtcFrameUncertainty
from analysis.fusion.models import PracticeMode
from analysis.fusion.timeline_fusion import build_shared_timeline
from analysis.lyrics.models import LyricTranscript
from analysis.strumming.suitability import detect_music_only_regions


def _beat_grid(count: int) -> BeatGrid:
    return BeatGrid(
        bpm=60.0,
        beats_per_bar=4,
        source="fixture",
        beats=[
            BeatEvent(
                time=float(index),
                beat_number=index % 4 + 1,
                is_downbeat=index % 4 == 0,
                source="fixture",
            )
            for index in range(count)
        ],
    )


def _chords(count: int, *, inverted: bool = False) -> list[ChordSegment]:
    return [
        ChordSegment(
            start=float(index),
            end=float(index + 1),
            raw_label=("G" if (index % 2 == 0) == inverted else "C"),
            normalized_label=("G" if (index % 2 == 0) == inverted else "C"),
            source="fixture",
        )
        for index in range(count - 1)
    ]


def _uncertain_frames(count: int) -> list[BtcFrameUncertainty]:
    return [
        BtcFrameUncertainty(
            time=index / 4,
            predicted_index=index % 2,
            predicted_label="C" if index % 2 == 0 else "G",
            top1_score=0.11,
            top2_score=0.10,
            margin=0.01,
            normalized_entropy=0.9,
        )
        for index in range((count - 1) * 4)
    ]


def test_frozen_production_path_exports_only_confirmed_music_only():
    beat_grid = _beat_grid(33)
    regions = detect_music_only_regions(
        _chords(33),
        _chords(33, inverted=True),
        beat_grid,
        _uncertain_frames(33),
    )

    timeline = build_shared_timeline(
        beat_grid,
        [],
        LyricTranscript(source="fixture", language="en", segments=[]),
        practice_regions=regions,
    )

    assert timeline.practice_regions
    assert all(
        region.mode is PracticeMode.MUSIC_ONLY
        for region in timeline.practice_regions
    )
    assert timeline.practice_regions[0].start == 0.0
    assert timeline.practice_regions[0].end == 32.0


def test_single_uncertain_window_is_not_exported():
    beat_grid = _beat_grid(9)

    regions = detect_music_only_regions(
        _chords(9),
        _chords(9, inverted=True),
        beat_grid,
        _uncertain_frames(9),
    )

    assert regions == []


def test_vamp_simple_host_diagnostic_normalizes_events(monkeypatch, tmp_path):
    audio = tmp_path / "normalized.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\0\0" * 16_000)
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        return subprocess.CompletedProcess(
            argv,
            0,
            "0.000: C:maj\n1.000: A:min7\n",
            "",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    chords = run_chordino_diagnostic(
        audio,
        executable=tmp_path / "vamp-simple-host",
    )

    assert observed["argv"] == [
        str(tmp_path / "vamp-simple-host"),
        "nnls-chroma:chordino:simplechord",
        str(audio),
    ]
    assert observed["shell"] is False
    assert [chord.normalized_label for chord in chords] == ["C", "Am"]
    assert [(chord.start, chord.end) for chord in chords] == [
        (0.0, 1.0),
        (1.0, 2.0),
    ]

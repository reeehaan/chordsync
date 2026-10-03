from pathlib import Path
import subprocess

import pytest

from analysis.preprocessing.audio_preprocessor import (
    get_audio_metadata,
    preprocess_audio,
)


def create_test_audio(path: Path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ac",
            "2",
            "-ar",
            "48000",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def create_tagged_test_audio(path: Path):
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=1",
            "-metadata", "title=Tagged Song",
            "-metadata", "artist=Tagged Artist",
            "-metadata", "album=Tagged Album",
            "-metadata", "version=Acoustic Version",
            "-metadata", "comment=Local test fixture",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_preprocess_audio(tmp_path):
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "output.wav"

    create_test_audio(input_path)

    preprocess_audio(
        input_path=input_path,
        output_path=output_path,
    )

    metadata = get_audio_metadata(output_path)

    assert output_path.exists()
    assert metadata["sample_rate"] == 44100
    assert metadata["channels"] == 1
    assert metadata["codec"] == "pcm_s16le"
    assert metadata["title"] is None
    assert metadata["artist"] is None
    assert metadata["album"] is None
    assert metadata["version"] is None
    assert metadata["comment"] is None


def test_get_audio_metadata_extracts_embedded_tags(tmp_path):
    input_path = tmp_path / "tagged.flac"
    create_tagged_test_audio(input_path)

    metadata = get_audio_metadata(input_path)

    assert metadata["title"] == "Tagged Song"
    assert metadata["artist"] == "Tagged Artist"
    assert metadata["album"] == "Tagged Album"
    assert metadata["version"] == "Acoustic Version"
    assert metadata["comment"] == "Local test fixture"
    assert metadata["duration"] == pytest.approx(1.0, abs=0.1)


def test_get_audio_metadata_represents_missing_artist_as_absent(tmp_path):
    input_path = tmp_path / "title-only.flac"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=1",
            "-metadata", "title=Title Only",
            str(input_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    metadata = get_audio_metadata(input_path)

    assert metadata["title"] == "Title Only"
    assert metadata["artist"] is None

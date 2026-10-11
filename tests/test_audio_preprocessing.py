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


def test_preprocess_audio_accepts_relative_local_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    input_path = Path("input.wav")
    output_path = Path("nested/output.wav")
    create_test_audio(input_path)

    assert preprocess_audio(input_path, output_path) == output_path
    assert output_path.exists()


@pytest.mark.parametrize(
    "remote_path",
    [
        "http://example.com/audio.wav",
        "HTTP://example.com/audio.wav",
        "https://example.com/audio.wav",
        "HtTpS://example.com/audio.wav",
        "s3://bucket/audio.wav",
        "https:example.com/audio.wav",
        "https:%2f%2fexample.com/audio.wav",
        r"https:\\example.com\audio.wav",
        "file:///tmp/audio.wav",
        "ftp://example.com/audio.wav",
        "tcp://example.com:443",
        "tls://example.com:443",
        "concat:https://example.com/audio.wav",
        "pipe:0",
        "crypto:https://example.com/audio.wav",
        "subfile,,start,0,:https://example.com/audio.wav",
        "data:audio/wav;base64,AA",
        "lavfi:sine=frequency=440",
        " https://example.com/audio.wav",
        "https://example.com/audio.wav\nnext.wav",
    ],
)
def test_preprocess_audio_rejects_remote_input(remote_path, tmp_path):
    with pytest.raises(ValueError, match="local filesystem path"):
        preprocess_audio(Path(remote_path), tmp_path / "output.wav")


@pytest.mark.parametrize(
    "remote_path",
    [
        "https://example.com/output.wav",
        "file:///tmp/output.wav",
        "concat:https://example.com/output.wav",
        "subfile,,start,0,:https://example.com/output.wav",
        "pipe:1",
    ],
)
def test_preprocess_audio_rejects_remote_output(remote_path, tmp_path):
    input_path = tmp_path / "input.wav"
    create_test_audio(input_path)

    with pytest.raises(ValueError, match="local filesystem path"):
        preprocess_audio(input_path, Path(remote_path))


@pytest.mark.parametrize(
    "remote_path",
    [
        "http://example.com/audio.wav",
        "HTTP://example.com/audio.wav",
        "https://example.com/audio.wav",
        "HtTpS://example.com/audio.wav",
        "s3://bucket/audio.wav",
        "https:example.com/audio.wav",
        "https:%2f%2fexample.com/audio.wav",
        r"https:\\example.com\audio.wav",
        "file:///tmp/audio.wav",
        "ftp://example.com/audio.wav",
        "tcp://example.com:443",
        "tls://example.com:443",
        "concat:https://example.com/audio.wav",
        "pipe:0",
        "crypto:https://example.com/audio.wav",
        "subfile,,start,0,:https://example.com/audio.wav",
        "data:audio/wav;base64,AA",
        "lavfi:sine=frequency=440",
        " https://example.com/audio.wav",
        "https://example.com/audio.wav\nnext.wav",
    ],
)
def test_get_audio_metadata_rejects_remote_input(remote_path):
    with pytest.raises(ValueError, match="local filesystem path"):
        get_audio_metadata(Path(remote_path))


def test_uri_rejection_happens_before_subprocess(monkeypatch, tmp_path):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"not used")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("subprocess must not run for URI-style paths")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    with pytest.raises(ValueError, match="local filesystem path"):
        preprocess_audio(
            Path("subfile,,start,0,:https://example.com/audio.wav"),
            tmp_path / "output.wav",
        )
    with pytest.raises(ValueError, match="local filesystem path"):
        preprocess_audio(input_path, Path("pipe:1"))
    with pytest.raises(ValueError, match="local filesystem path"):
        get_audio_metadata(Path("HtTpS://example.com/audio.wav"))


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

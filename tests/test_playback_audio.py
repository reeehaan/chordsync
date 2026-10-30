import shutil
import struct
import wave
from pathlib import Path

import pytest

from analysis.preprocessing.playback_encoder import prepare_playback


def _wav_bytes(tmp_path: Path, seconds: float = 2.0) -> bytes:
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44100)
        frames = int(44100 * seconds)
        out.writeframes(struct.pack("<hh", 1000, -1000) * frames)
    return path.read_bytes()


def test_a_small_mp3_is_published_unchanged(tmp_path):
    result = prepare_playback(Path("song.mp3"), b"ID3 not really")

    assert result.extension == ".mp3"
    assert result.content == b"ID3 not really"


def test_a_file_that_cannot_be_encoded_keeps_the_original(tmp_path):
    result = prepare_playback(Path("song.wav"), b"this is not audio")

    assert result.extension == ".wav"
    assert result.content == b"this is not audio"
    assert result.content_type == "audio/wav"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_wav_becomes_a_much_smaller_mp3(tmp_path):
    wav = _wav_bytes(tmp_path)

    result = prepare_playback(Path("song.wav"), wav)

    assert result.extension == ".mp3"
    assert result.content_type == "audio/mpeg"
    assert len(result.content) < len(wav) / 4

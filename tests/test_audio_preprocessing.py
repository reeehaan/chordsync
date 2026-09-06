from pathlib import Path
import subprocess

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

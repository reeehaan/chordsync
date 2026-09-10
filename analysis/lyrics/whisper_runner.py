from pathlib import Path

import whisper


def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    word_timestamps: bool = False,
) -> dict:
    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    model = whisper.load_model(model_name)

    result = model.transcribe(
        str(audio_path),
        language="en",
        verbose=False,
        word_timestamps=word_timestamps,
    )

    return result

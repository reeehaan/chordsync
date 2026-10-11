import json
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

TARGET_SAMPLE_RATE = 44100


def preprocess_audio(input_path: Path, output_path: Path) -> Path:
    """
    Convert an audio file into a standard analysis format:
    - WAV
    - mono
    - 44.1 kHz
    - PCM 16-bit
    """

    input_path = _require_local_path(input_path, "Input audio")
    output_path = _require_local_path(output_path, "Output audio")

    if not input_path.exists():
        raise FileNotFoundError(f"Input audio not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    except subprocess.CalledProcessError as error:
        message = error.stderr.decode("utf-8", errors="ignore")

        raise RuntimeError(
            f"FFmpeg preprocessing failed:\n{message}"
        ) from error

    return output_path


def get_audio_metadata(audio_path: Path) -> dict[str, object]:
    """
    Extract technical audio metadata using ffprobe.
    """

    audio_path = _require_local_path(audio_path, "Audio")

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels",
        "-show_entries",
        "format=duration:format_tags=title,artist,album,version,comment",
        "-of",
        "json",
        str(audio_path),
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"ffprobe failed:\n{error.stderr}"
        ) from error

    data = json.loads(result.stdout)

    stream = data["streams"][0]
    format_data = data["format"]

    tags = format_data.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}

    return {
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 0)),
        "duration": float(format_data.get("duration", 0)),
        "title": _optional_tag(tags.get("title")),
        "artist": _optional_tag(tags.get("artist")),
        "album": _optional_tag(tags.get("album")),
        "version": _optional_tag(tags.get("version")),
        "comment": _optional_tag(tags.get("comment")),
    }


def _require_local_path(path: Path, label: str) -> Path:
    candidate = Path(path)
    candidate_text = str(candidate)
    if (
        urlsplit(candidate_text).scheme
        or candidate_text.casefold().startswith("subfile,,")
    ):
        raise ValueError(f"{label} must be a local filesystem path: {candidate}")
    return candidate


def _optional_tag(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None

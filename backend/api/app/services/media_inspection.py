"""Deterministic audio inspection for the hosted API (no ffmpeg or ffprobe).

The API only has to decide three things about an upload: which supported
format it really is, how long it is, and how big it is. Detection uses the
file's own signature, never its extension or the client's Content-Type, and
the caller then requires the detected format to match the extension.

- WAV: a small RIFF chunk reader. The standard library ``wave`` module is not
  used because it rejects 24-bit WAVE_FORMAT_EXTENSIBLE and 32-bit float files
  that ffprobe (and therefore the worker pipeline) accept.
- MP3: ``mpeg_audio``, an MPEG frame-header reader that skips ID3 tags
  (including cover art) by their declared size and requires a run of
  consistent frames.
- M4A: ``mp4_audio``, an ISO base media box reader that requires every
  top-level box to fit in the file and an AAC or Apple Lossless audio track.

All three parsers are small, dependency-free, and read only headers.

Durations come from container headers, as they do with ffprobe. A hostile file
can understate its length; the 25 MB size cap and the worker's per-stage
timeouts bound the consequence.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Mapping

from backend.api.app.services import mp4_audio, mpeg_audio
from backend.api.app.services.media_errors import MediaInspectionError


class AudioFormat(str, Enum):
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"


EXTENSION_FORMATS: Mapping[str, AudioFormat] = {
    ".mp3": AudioFormat.MP3,
    ".m4a": AudioFormat.M4A,
    ".wav": AudioFormat.WAV,
}

# What the server stores for a validated upload, regardless of what the client
# declared.
CANONICAL_CONTENT_TYPES: Mapping[AudioFormat, str] = {
    AudioFormat.MP3: "audio/mpeg",
    AudioFormat.M4A: "audio/mp4",
    AudioFormat.WAV: "audio/wav",
}

_WAVE_FORMAT_PCM = 1
_WAVE_FORMAT_IEEE_FLOAT = 3
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE
_UNCOMPRESSED_WAVE_FORMATS = frozenset({_WAVE_FORMAT_PCM, _WAVE_FORMAT_IEEE_FLOAT})
_UNKNOWN_DATA_SIZE = 0xFFFFFFFF
_MAX_WAV_CHUNKS = 1000

__all__ = [
    "CANONICAL_CONTENT_TYPES",
    "EXTENSION_FORMATS",
    "AudioFormat",
    "MediaInfo",
    "MediaInspectionError",
    "inspect_audio",
]


@dataclass(frozen=True)
class MediaInfo:
    format: AudioFormat
    duration_seconds: float
    file_size_bytes: int


def inspect_audio(path: Path) -> MediaInfo:
    """Detect the real format of ``path`` and measure its duration."""
    try:
        file_size = path.stat().st_size
        if file_size == 0:
            raise MediaInspectionError("empty file")
        with path.open("rb") as handle:
            head = handle.read(12)
            if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
                detected, duration = AudioFormat.WAV, _wav_duration(handle, file_size)
            elif head[4:8] == b"ftyp":
                detected = AudioFormat.M4A
                duration = mp4_audio.audio_duration_seconds(handle, file_size)
            else:
                detected = AudioFormat.MP3
                duration = mpeg_audio.stream_duration_seconds(handle, file_size)
    except MediaInspectionError:
        raise
    except Exception as error:
        # Parsers raise many exception types; none of them may reach a client.
        raise MediaInspectionError("unreadable or unsupported audio") from error
    if not math.isfinite(duration) or duration <= 0:
        raise MediaInspectionError("non-positive duration")
    return MediaInfo(detected, duration, file_size)


def _wav_duration(handle: BinaryIO, file_size: int) -> float:
    """Duration of an uncompressed (PCM, float, or extensible) WAV file."""
    handle.seek(12)
    sample_rate = block_align = 0
    for _ in range(_MAX_WAV_CHUNKS):
        header = handle.read(8)
        if len(header) < 8:
            raise MediaInspectionError("WAV has no data chunk")
        chunk_id = header[:4]
        (chunk_size,) = struct.unpack("<I", header[4:])
        body_start = handle.tell()

        if chunk_id == b"fmt ":
            sample_rate, block_align = _parse_wav_format(handle, chunk_size)
        elif chunk_id == b"data":
            if not sample_rate:
                raise MediaInspectionError("WAV data precedes its format chunk")
            available = file_size - body_start
            declared = chunk_size
            if declared > available:
                if declared != _UNKNOWN_DATA_SIZE:
                    raise MediaInspectionError("WAV data is truncated")
                declared = available  # streamed WAV with an unknown length
            return (declared // block_align) / sample_rate

        # Chunks are padded to an even size.
        handle.seek(body_start + chunk_size + (chunk_size & 1))
    raise MediaInspectionError("WAV has too many chunks")


def _parse_wav_format(handle: BinaryIO, chunk_size: int) -> tuple[int, int]:
    if chunk_size < 16:
        raise MediaInspectionError("WAV format chunk is too short")
    raw = handle.read(min(chunk_size, 40))
    if len(raw) < 16:
        raise MediaInspectionError("WAV format chunk is truncated")
    tag, channels, sample_rate, _byte_rate, block_align, _bits = struct.unpack(
        "<HHIIHH", raw[:16]
    )
    if tag == _WAVE_FORMAT_EXTENSIBLE:
        if chunk_size < 40 or len(raw) < 26:
            raise MediaInspectionError("WAV extensible format chunk is too short")
        (tag,) = struct.unpack("<H", raw[24:26])
    if tag not in _UNCOMPRESSED_WAVE_FORMATS:
        raise MediaInspectionError("WAV is not uncompressed PCM or float")
    if channels < 1 or sample_rate < 1 or block_align < 1:
        raise MediaInspectionError("WAV format fields are invalid")
    return sample_rate, block_align

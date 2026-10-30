"""The audio a phone downloads to practise with.

Analysis reads the uploaded file, but the phone only has to play it, so a WAV
(tens of megabytes) is published as an MP3 of a tenth the size, and a large
MP3 is brought down to the same bitrate. If the file is already small, or
encoding is not possible, the original is kept: a song is never lost over its
playback copy.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from backend.api.app.services.playback_audio import PlaybackAudio, original_playback

logger = logging.getLogger(__name__)

PLAYBACK_BITRATE = "160k"
ENCODE_TIMEOUT_SECONDS = 300

# An MP3 up to this size is kept as uploaded. A bigger one (a 320 kbps rip) is
# re-encoded, and the smaller result is used.
SMALL_MP3_BYTES = 5 * 1024 * 1024


def prepare_playback(path: Path, content: bytes) -> PlaybackAudio:
    """An MP3 copy of the song for the phone, or the original if that fails."""
    original = original_playback(path, content)
    if original.extension == ".mp3" and len(content) <= SMALL_MP3_BYTES:
        return original  # already small; re-encoding would only cost quality
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        logger.warning("ffmpeg is not available; publishing the original audio")
        return original
    try:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / f"source{original.extension}"
            target = Path(folder) / "playback.mp3"
            source.write_bytes(content)
            completed = subprocess.run(
                [
                    ffmpeg, "-nostdin", "-loglevel", "error", "-y",
                    "-i", str(source),
                    "-vn", "-map_metadata", "-1",
                    "-codec:a", "libmp3lame", "-b:a", PLAYBACK_BITRATE,
                    str(target),
                ],
                capture_output=True,
                shell=False,
                check=False,
                timeout=ENCODE_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or not target.is_file():
                logger.warning("mp3 encoding failed; publishing the original audio")
                return original
            encoded = target.read_bytes()
    except (OSError, subprocess.SubprocessError):
        logger.warning("mp3 encoding failed; publishing the original audio")
        return original
    if not encoded or len(encoded) >= len(content):
        return original  # nothing gained
    return PlaybackAudio(encoded, ".mp3", "audio/mpeg")

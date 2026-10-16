"""MPEG audio (MP3) stream inspection, written from the public frame format.

Only headers are read; no audio is decoded. A file is accepted as MPEG audio
only when it contains a run of consecutive, mutually consistent frame headers
(``_REQUIRED_FRAMES`` of them), found by scanning the first megabyte after any
ID3v2 tags. Random data, text, other media, and streams cut inside their first
frames fail that test, so a lone frame-sync-looking byte pair is never enough.

Duration comes from a Xing/Info or VBRI frame count when the first frame
carries one, and otherwise from the audio byte count divided by the bitrate
(exact for constant bitrate). ID3v2 tags are skipped by their declared size,
so embedded cover art is never read or parsed.

Layout reference: the MPEG-1/2/2.5 audio frame header (ISO/IEC 11172-3 and
13818-3) and the widely documented Xing/Info and VBRI header fields.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO

from backend.api.app.services.media_errors import MediaInspectionError

_ID3V2_HEADER_BYTES = 10
_ID3V2_FOOTER_BYTES = 10
_ID3V1_BYTES = 128
_MAX_STACKED_ID3V2_TAGS = 16
_SCAN_BYTES = 1024 * 1024
# The largest real frame is under 2 KB; the slack lets a run that starts near
# the end of the scan window be verified in full.
_FRAME_SLACK_BYTES = 8 * 1024
_MAX_SYNC_CANDIDATES = 1500
_REQUIRED_FRAMES = 4

# Bitrates in kbit/s by header index, keyed by (is MPEG-1, layer). Index 0 is
# "free format" and index 15 is invalid; neither is supported.
_BITRATES_KBPS: dict[tuple[bool, int], tuple[int | None, ...]] = {
    (True, 1): (None, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, None),
    (True, 2): (None, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, None),
    (True, 3): (None, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, None),
    (False, 1): (None, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, None),
    (False, 2): (None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, None),
    (False, 3): (None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, None),
}
# Sample rates by header index, keyed by version.
_SAMPLE_RATES: dict[int, tuple[int, int, int]] = {
    1: (44100, 48000, 32000),
    2: (22050, 24000, 16000),
    25: (11025, 12000, 8000),
}
# Header version bits -> version (01 is reserved) and layer bits -> layer (00 is reserved).
_VERSIONS = {0b11: 1, 0b10: 2, 0b00: 25}
_LAYERS = {0b11: 1, 0b10: 2, 0b01: 3}


@dataclass(frozen=True)
class _FrameHeader:
    version: int
    layer: int
    crc_follows: bool
    bitrate: int  # bits per second
    sample_rate: int
    channels: int
    samples_per_frame: int
    size: int  # bytes, including the header

    def same_stream_as(self, other: _FrameHeader) -> bool:
        return (self.version, self.layer, self.sample_rate) == (
            other.version,
            other.layer,
            other.sample_rate,
        )


def stream_duration_seconds(handle: BinaryIO, file_size: int) -> float:
    """Duration of the MPEG audio stream in ``handle`` (a file of ``file_size``)."""
    audio_start = _skip_id3v2_tags(handle, file_size)
    handle.seek(audio_start)
    window = handle.read(_SCAN_BYTES + _FRAME_SLACK_BYTES)
    found = _find_frame_run(window)
    if found is None:
        raise MediaInspectionError("no consistent MPEG audio frames")
    offset, header = found

    declared_frames = _declared_frame_count(window, offset, header)
    if declared_frames is not None:
        return declared_frames * header.samples_per_frame / header.sample_rate

    audio_bytes = file_size - (audio_start + offset) - _id3v1_tag_bytes(handle, file_size)
    return audio_bytes * 8 / header.bitrate


def _skip_id3v2_tags(handle: BinaryIO, file_size: int) -> int:
    """Offset of the first byte after any (possibly stacked) ID3v2 tags."""
    position = 0
    for _ in range(_MAX_STACKED_ID3V2_TAGS):
        handle.seek(position)
        head = handle.read(_ID3V2_HEADER_BYTES)
        if len(head) < _ID3V2_HEADER_BYTES or head[:3] != b"ID3":
            return position
        size_bytes = head[6:10]
        if any(byte & 0x80 for byte in size_bytes):
            raise MediaInspectionError("ID3v2 size is not synchsafe")
        size = (size_bytes[0] << 21) | (size_bytes[1] << 14) | (size_bytes[2] << 7) | size_bytes[3]
        footer = _ID3V2_FOOTER_BYTES if head[5] & 0x10 else 0
        end = position + _ID3V2_HEADER_BYTES + size + footer
        if end > file_size:
            raise MediaInspectionError("ID3v2 tag extends past the end of the file")
        position = end
    raise MediaInspectionError("too many stacked ID3v2 tags")


def _id3v1_tag_bytes(handle: BinaryIO, file_size: int) -> int:
    if file_size < _ID3V1_BYTES:
        return 0
    handle.seek(file_size - _ID3V1_BYTES)
    return _ID3V1_BYTES if handle.read(3) == b"TAG" else 0


def _parse_header(data: bytes, offset: int) -> _FrameHeader | None:
    if offset + 4 > len(data):
        return None
    (word,) = struct.unpack_from(">I", data, offset)
    if word >> 21 != 0x7FF:
        return None
    version = _VERSIONS.get((word >> 19) & 0b11)
    layer = _LAYERS.get((word >> 17) & 0b11)
    rate_index = (word >> 10) & 0b11
    if version is None or layer is None or rate_index == 3:
        return None
    kbps = _BITRATES_KBPS[(version == 1, layer)][(word >> 12) & 0b1111]
    if kbps is None:
        return None

    sample_rate = _SAMPLE_RATES[version][rate_index]
    bitrate = kbps * 1000
    padding = (word >> 9) & 1
    if layer == 1:
        samples_per_frame = 384
        size = (12 * bitrate // sample_rate + padding) * 4
    elif layer == 3 and version != 1:
        samples_per_frame = 576
        size = 72 * bitrate // sample_rate + padding
    else:
        samples_per_frame = 1152
        size = 144 * bitrate // sample_rate + padding
    if size < 4:
        return None
    return _FrameHeader(
        version=version,
        layer=layer,
        crc_follows=not (word >> 16) & 1,
        bitrate=bitrate,
        sample_rate=sample_rate,
        channels=1 if (word >> 6) & 0b11 == 0b11 else 2,
        samples_per_frame=samples_per_frame,
        size=size,
    )


def _find_frame_run(window: bytes) -> tuple[int, _FrameHeader] | None:
    """First offset that starts ``_REQUIRED_FRAMES`` consistent, complete frames."""
    limit = min(len(window), _SCAN_BYTES)
    position = 0
    candidates = 0
    while candidates < _MAX_SYNC_CANDIDATES:
        position = window.find(b"\xff", position, limit)
        if position < 0 or position + 1 >= len(window):
            return None
        if window[position + 1] & 0xE0 == 0xE0:
            candidates += 1
            first = _parse_header(window, position)
            if first is not None and _is_frame_run(window, position, first):
                return position, first
        position += 1
    return None


def _is_frame_run(window: bytes, start: int, first: _FrameHeader) -> bool:
    position = start
    for _ in range(_REQUIRED_FRAMES):
        header = first if position == start else _parse_header(window, position)
        if header is None or not header.same_stream_as(first):
            return False
        position += header.size
        if position > len(window):
            return False  # the frame is cut off by the end of the file
    return True


def _declared_frame_count(window: bytes, start: int, header: _FrameHeader) -> int | None:
    """Frame count from a Xing/Info or VBRI tag in the first frame, if present."""
    if header.layer != 3:
        return None
    frame = window[start : start + header.size]
    side_info = (17 if header.channels == 1 else 32) if header.version == 1 else (
        9 if header.channels == 1 else 17
    )
    xing_at = 4 + (2 if header.crc_follows else 0) + side_info
    if frame[xing_at : xing_at + 4] in (b"Xing", b"Info"):
        fields = frame[xing_at + 4 : xing_at + 12]
        if len(fields) == 8:
            flags, frames = struct.unpack(">II", fields)
            return frames if flags & 1 else None
        return None
    if frame[36:40] == b"VBRI" and len(frame) >= 54:
        return struct.unpack(">I", frame[50:54])[0]
    return None

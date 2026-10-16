"""M4A (MP4 audio) inspection from the box structure.

Only box headers and a few small fields are read. A file is accepted when:

- every top-level box fits inside the file (so a truncated file is rejected);
- moov has an audio track (handler soun) with a positive timescale and duration;
- that track's first sample entry is mp4a (AAC) or alac (Apple Lossless).

Fragmented MP4 has a zero duration in mdhd, so it is rejected.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from typing import BinaryIO

from backend.api.app.services.media_errors import MediaInspectionError

_MAX_BOXES_PER_LEVEL = 10_000
_ACCEPTED_AUDIO_ENTRIES = frozenset({b"mp4a", b"alac"})
_BOX_HEADER_BYTES = 8
_LARGE_BOX_HEADER_BYTES = 16


def audio_duration_seconds(handle: BinaryIO, file_size: int) -> float:
    """Duration of the first audio track in an M4A file of ``file_size`` bytes."""
    moov: tuple[int, int] | None = None
    for kind, start, end in _boxes(handle, 0, file_size):
        if kind == b"moov" and moov is None:
            moov = (start, end)
    if moov is None:
        raise MediaInspectionError("MP4 has no moov box")

    for kind, start, end in _boxes(handle, *moov):
        if kind == b"trak":
            mdia = _child(handle, start, end, b"mdia")
            if mdia is not None and _handler_type(handle, mdia) == b"soun":
                return _audio_track_duration(handle, mdia)
    raise MediaInspectionError("MP4 has no audio track")


def _boxes(handle: BinaryIO, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Child boxes in [start, end) as (type, payload_start, payload_end).

    Every box must fit inside its parent. Stray bytes shorter than a box header
    after the last box are ignored.
    """
    position = start
    for _ in range(_MAX_BOXES_PER_LEVEL):
        if position + _BOX_HEADER_BYTES > end:
            return
        handle.seek(position)
        size, kind = struct.unpack(">I4s", handle.read(_BOX_HEADER_BYTES))
        header = _BOX_HEADER_BYTES
        if size == 1:  # a 64-bit size follows the type
            (size,) = struct.unpack(">Q", handle.read(8))
            header = _LARGE_BOX_HEADER_BYTES
        elif size == 0:  # the box runs to the end of its parent
            size = end - position
        if size < header or position + size > end:
            raise MediaInspectionError("MP4 box is truncated or malformed")
        yield kind, position + header, position + size
        position += size
    raise MediaInspectionError("MP4 has too many boxes")


def _child(handle: BinaryIO, start: int, end: int, kind: bytes) -> tuple[int, int] | None:
    for box_kind, box_start, box_end in _boxes(handle, start, end):
        if box_kind == kind:
            return box_start, box_end
    return None


def _read(handle: BinaryIO, start: int, end: int, count: int) -> bytes:
    handle.seek(start)
    data = handle.read(min(count, end - start))
    if len(data) < count:
        raise MediaInspectionError("MP4 box is too short")
    return data


def _handler_type(handle: BinaryIO, mdia: tuple[int, int]) -> bytes | None:
    hdlr = _child(handle, *mdia, b"hdlr")
    if hdlr is None:
        return None
    # version/flags (4), pre_defined (4), handler_type (4)
    return _read(handle, *hdlr, 12)[8:12]


def _audio_track_duration(handle: BinaryIO, mdia: tuple[int, int]) -> float:
    entry = _first_sample_entry_type(handle, mdia)
    if entry not in _ACCEPTED_AUDIO_ENTRIES:
        raise MediaInspectionError("audio track is not AAC or Apple Lossless")

    mdhd = _child(handle, *mdia, b"mdhd")
    if mdhd is None:
        raise MediaInspectionError("audio track has no media header")
    version = _read(handle, *mdhd, 1)[0]
    if version == 0:  # creation, modification, timescale, duration (32-bit each)
        timescale, duration = struct.unpack(">II", _read(handle, *mdhd, 20)[12:20])
    elif version == 1:  # 64-bit times, 32-bit timescale, 64-bit duration
        data = _read(handle, *mdhd, 32)
        (timescale,) = struct.unpack(">I", data[20:24])
        (duration,) = struct.unpack(">Q", data[24:32])
    else:
        raise MediaInspectionError("unknown media header version")
    if timescale == 0 or duration == 0:
        raise MediaInspectionError("audio track reports no duration")
    return duration / timescale


def _first_sample_entry_type(handle: BinaryIO, mdia: tuple[int, int]) -> bytes | None:
    box = mdia
    for kind in (b"minf", b"stbl", b"stsd"):
        child = _child(handle, *box, kind)
        if child is None:
            return None
        box = child
    # version/flags (4), entry_count (4), then the first entry: size (4), type (4)
    data = _read(handle, *box, 16)
    (entry_count,) = struct.unpack(">I", data[4:8])
    return data[12:16] if entry_count >= 1 else None

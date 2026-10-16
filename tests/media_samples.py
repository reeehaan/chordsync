"""Synthetic audio containers for validator tests. No real recordings.

Each builder produces a small, structurally valid file of its format, so tests
can check durations exactly without ffmpeg, committed binaries, or any media
library. The MPEG tables below are written independently of the parser's, so a
mistake in either shows up as a failing comparison.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from pathlib import Path

# --- WAV ----------------------------------------------------------------------


def wav_bytes(
    seconds: float,
    *,
    sample_rate: int = 8000,
    channels: int = 1,
    bits: int = 16,
    float_samples: bool = False,
    extensible: bool = False,
) -> bytes:
    block_align = channels * bits // 8
    data = bytes(int(seconds * sample_rate) * block_align)
    tag = 3 if float_samples else 1
    if extensible:
        guid = struct.pack("<H", tag) + bytes.fromhex("000000001000800000AA00389B71")
        fmt = struct.pack(
            "<HHIIHHHHI",
            0xFFFE, channels, sample_rate, sample_rate * block_align, block_align,
            bits, 22, bits, 3,
        ) + guid
    else:
        fmt = struct.pack(
            "<HHIIHH", tag, channels, sample_rate, sample_rate * block_align,
            block_align, bits,
        )
    return _riff(fmt, data)


def _riff(fmt: bytes, data: bytes, *, data_size: int | None = None) -> bytes:
    declared = len(data) if data_size is None else data_size
    body = (
        b"WAVE"
        + b"fmt " + struct.pack("<I", len(fmt)) + fmt
        + b"data" + struct.pack("<I", declared) + data
    )
    return b"RIFF" + struct.pack("<I", len(body)) + body


def wav_with_declared_size(seconds: float, declared_size: int) -> bytes:
    """A WAV whose data chunk header claims ``declared_size`` bytes."""
    fmt = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
    return _riff(fmt, bytes(int(seconds * 8000) * 2), data_size=declared_size)


# --- MPEG audio (MP3) ----------------------------------------------------------

_VERSION_BITS = {1: 0b11, 2: 0b10, 25: 0b00}
_LAYER_BITS = {1: 0b11, 2: 0b10, 3: 0b01}
_SAMPLE_RATES = {
    1: {44100: 0, 48000: 1, 32000: 2},
    2: {22050: 0, 24000: 1, 16000: 2},
    25: {11025: 0, 12000: 1, 8000: 2},
}
# kbit/s -> header index, per (MPEG-1?, layer)
_BITRATE_INDEX = {
    (True, 1): {k: i for i, k in enumerate(
        (32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448), 1)},
    (True, 2): {k: i for i, k in enumerate(
        (32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384), 1)},
    (True, 3): {k: i for i, k in enumerate(
        (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320), 1)},
    (False, 1): {k: i for i, k in enumerate(
        (32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256), 1)},
    (False, 2): {k: i for i, k in enumerate(
        (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160), 1)},
}
_BITRATE_INDEX[(False, 3)] = _BITRATE_INDEX[(False, 2)]


def mpeg_samples_per_frame(version: int, layer: int) -> int:
    if layer == 1:
        return 384
    return 1152 if (layer == 2 or version == 1) else 576


def mpeg_bitrates(version: int, layer: int) -> list[int]:
    return sorted(_BITRATE_INDEX[(version == 1, layer)])


def mpeg_sample_rates(version: int) -> list[int]:
    return sorted(_SAMPLE_RATES[version])


def _frame_bytes(version: int, layer: int, kbps: int, rate: int, padding: int) -> int:
    bits = kbps * 1000
    if layer == 1:
        return (12 * bits // rate + padding) * 4
    if layer == 3 and version != 1:
        return 72 * bits // rate + padding
    return 144 * bits // rate + padding


def _auto_padding(version: int, layer: int, kbps: int, rate: int) -> Callable[[int], int]:
    """Padding bits that make the average frame size exact, like a CBR encoder."""
    bits = kbps * 1000
    if layer == 1:
        exact_numerator, scale = 12 * bits, rate
    elif layer == 3 and version != 1:
        exact_numerator, scale = 72 * bits, rate
    else:
        exact_numerator, scale = 144 * bits, rate

    def padding(index: int) -> int:
        return ((index + 1) * exact_numerator) // scale - (index * exact_numerator) // scale - (
            exact_numerator // scale
        )

    return padding


def _side_info_bytes(version: int, channels: int) -> int:
    if version == 1:
        return 17 if channels == 1 else 32
    return 9 if channels == 1 else 17


def mpeg_frame(
    *,
    version: int = 1,
    layer: int = 3,
    bitrate_kbps: int = 32,
    sample_rate: int = 32000,
    channels: int = 1,
    crc: bool = False,
    padding: int = 0,
    payload: bytes = b"",
    tag_offset: int | None = None,
) -> bytes:
    """One MPEG audio frame: a real header followed by silence (zero bytes).

    ``payload`` is written at ``tag_offset`` (default: right after the header
    and optional CRC) so tests can place Xing/Info/VBRI tags.
    """
    index = _BITRATE_INDEX[(version == 1, layer)][bitrate_kbps]
    header = (
        0xFFE00000
        | (_VERSION_BITS[version] << 19)
        | (_LAYER_BITS[layer] << 17)
        | ((0 if crc else 1) << 16)
        | (index << 12)
        | (_SAMPLE_RATES[version][sample_rate] << 10)
        | (padding << 9)
        | ((3 if channels == 1 else 0) << 6)
    )
    size = _frame_bytes(version, layer, bitrate_kbps, sample_rate, padding)
    frame = bytearray(struct.pack(">I", header) + bytes(size - 4))
    if payload:
        start = tag_offset if tag_offset is not None else 4 + (2 if crc else 0)
        frame[start:start + len(payload)] = payload
    return bytes(frame)


def mpeg_stream(
    frames: int,
    *,
    version: int = 1,
    layer: int = 3,
    bitrate_kbps: int = 32,
    sample_rate: int = 32000,
    channels: int = 1,
    crc: bool = False,
    padding: Callable[[int], int] | str | None = "auto",
    xing: bytes | None = None,
    xing_frames: int | None = None,
    xing_omit_frames: bool = False,
    vbri_frames: int | None = None,
) -> bytes:
    """``frames`` audio frames, optionally preceded by a Xing/Info or VBRI frame."""
    common = dict(version=version, layer=layer, bitrate_kbps=bitrate_kbps,
                  sample_rate=sample_rate, channels=channels, crc=crc)
    if padding == "auto":
        padding = _auto_padding(version, layer, bitrate_kbps, sample_rate)
    elif isinstance(padding, str):
        raise ValueError(padding)
    out = bytearray()
    if xing is not None:
        claimed = frames if xing_frames is None else xing_frames
        flags = 0 if xing_omit_frames else 1
        body = xing + struct.pack(">I", flags)
        body += b"" if xing_omit_frames else struct.pack(">I", claimed)
        offset = 4 + (2 if crc else 0) + _side_info_bytes(version, channels)
        out += mpeg_frame(**common, payload=body, tag_offset=offset)
    elif vbri_frames is not None:
        body = b"VBRI" + struct.pack(">HHHII", 1, 0, 0, 0, vbri_frames)
        out += mpeg_frame(**common, payload=body, tag_offset=36)
    for index in range(frames):
        out += mpeg_frame(**common, padding=padding(index) if padding else 0)  # type: ignore[operator]
    return bytes(out)


# MPEG-1 Layer III, 32 kbit/s, 32 kHz, mono: 144-byte frames of 36 ms each.
MP3_FRAME_SECONDS = 1152 / 32000


def mp3_bytes(seconds: float) -> bytes:
    """Whole MPEG-1 Layer III frames; exact duration at 36 ms per frame."""
    return mpeg_stream(max(1, round(seconds / MP3_FRAME_SECONDS)))


def _syncsafe(value: int) -> bytes:
    return bytes(((value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F))


def id3v2_tag(
    *,
    version: int = 3,
    cover_art_bytes: int = 0,
    padding: int = 0,
    footer: bool = False,
) -> bytes:
    """An ID3v2.3/2.4 tag with title, artist, and an optional cover image."""

    def frame(frame_id: bytes, body: bytes) -> bytes:
        size = _syncsafe(len(body)) if version == 4 else struct.pack(">I", len(body))
        return frame_id + size + b"\x00\x00" + body

    frames = frame(b"TIT2", b"\x03Synthetic title") + frame(b"TPE1", b"\x03Synthetic artist")
    if cover_art_bytes:
        picture = b"\x03image/jpeg\x00\x03Cover\x00" + b"\xff\xd8\xff\xe0" + bytes(cover_art_bytes)
        frames += frame(b"APIC", picture)
    frames += bytes(padding)
    flags = 0x10 if footer else 0
    header = b"ID3" + bytes((version, 0, flags)) + _syncsafe(len(frames))
    trailer = b"3DI" + bytes((version, 0, flags)) + _syncsafe(len(frames)) if footer else b""
    return header + frames + trailer


def id3v1_tag() -> bytes:
    return b"TAG" + bytes(125)


def write_mp3_with_tags(path: Path, seconds: float, *, cover_art_bytes: int) -> None:
    """An MP3 with an ID3v2.3 tag carrying title, artist and a large cover image."""
    path.write_bytes(id3v2_tag(cover_art_bytes=cover_art_bytes) + mp3_bytes(seconds))


# --- MP4 / M4A ------------------------------------------------------------------


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _full_box(kind: bytes, payload: bytes, *, flags: int = 0) -> bytes:
    return _box(kind, struct.pack(">I", flags) + payload)


_AAC_SAMPLE_RATE_INDEX = {48000: 3, 44100: 4, 32000: 5, 22050: 7, 16000: 8, 8000: 11}


def _esds(sample_rate: int, channels: int) -> bytes:
    """Elementary-stream descriptor for AAC-LC, as real encoders write it."""
    config = ((2 << 11) | (_AAC_SAMPLE_RATE_INDEX[sample_rate] << 7) | (channels << 3))
    specific = b"\x05\x02" + config.to_bytes(2, "big")
    decoder = (
        b"\x04" + bytes([13 + len(specific)]) + b"\x40\x15" + bytes(3)
        + struct.pack(">II", 128000, 128000) + specific
    )
    sync_layer = b"\x06\x01\x02"
    descriptor = (
        b"\x03" + bytes([3 + len(decoder) + len(sync_layer)])
        + struct.pack(">HB", 1, 0) + decoder + sync_layer
    )
    return _full_box(b"esds", descriptor)


def _cover_metadata(cover_art_bytes: int) -> bytes:
    """``udta/meta/ilst`` carrying a title and a JPEG ``covr`` item."""
    title = _box(b"\xa9nam", _full_box(b"data", struct.pack(">I", 0) + b"Synthetic title", flags=1))
    cover = _box(
        b"covr",
        _full_box(
            b"data",
            struct.pack(">I", 0) + b"\xff\xd8\xff\xe0" + bytes(cover_art_bytes),
            flags=13,
        ),
    )
    handler = _full_box(b"hdlr", struct.pack(">I4s12x", 0, b"mdir") + b"\x00")
    return _box(b"udta", _full_box(b"meta", handler + _box(b"ilst", title + cover)))


def m4a_bytes(
    seconds: float,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
    moov_first: bool = True,
    sample_entry: bytes = b"mp4a",
    handler: bytes = b"soun",
    cover_art_bytes: int = 0,
    brand: bytes = b"M4A ",
) -> bytes:
    """A structurally valid MP4 audio file (AAC sample entry, silent payload)."""
    samples = int(seconds * sample_rate)
    frames = -(-samples // 1024)
    matrix = struct.pack(">9I", 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
    mvhd = _full_box(
        b"mvhd",
        struct.pack(">IIII", 0, 0, sample_rate, samples)
        + struct.pack(">IH10x", 0x10000, 0x100) + matrix + bytes(24)
        + struct.pack(">I", 2),
    )
    tkhd = _full_box(
        b"tkhd",
        struct.pack(">IIIII8xHHHH", 0, 0, 1, 0, samples, 0, 0, 0x100, 0)
        + matrix + struct.pack(">II", 0, 0),
        flags=7,
    )
    mdhd = _full_box(
        b"mdhd", struct.pack(">IIIIHH", 0, 0, sample_rate, samples, 0x55C4, 0)
    )
    hdlr = _full_box(b"hdlr", struct.pack(">I4s12x", 0, handler) + b"SoundHandler\x00")
    smhd = _full_box(b"smhd", struct.pack(">HH", 0, 0))
    dref = _full_box(b"dref", struct.pack(">I", 1) + _full_box(b"url ", b"", flags=1))
    dinf = _box(b"dinf", dref)
    entry = _box(
        sample_entry,
        bytes(6) + struct.pack(">H", 1) + bytes(8)
        + struct.pack(">HHHH", channels, 16, 0, 0) + struct.pack(">I", sample_rate << 16)
        + _esds(sample_rate, channels),
    )
    stsd = _full_box(b"stsd", struct.pack(">I", 1) + entry)
    stts = _full_box(b"stts", struct.pack(">III", 1, frames, 1024))
    stsc = _full_box(b"stsc", struct.pack(">IIII", 1, 1, frames, 1))
    stsz = _full_box(b"stsz", struct.pack(">II", 8, frames))
    ftyp = _box(b"ftyp", brand + struct.pack(">I", 0) + b"M4A mp42isom")
    mdat_payload = bytes(frames * 8)
    metadata = _cover_metadata(cover_art_bytes) if cover_art_bytes else b""

    def build(chunk_offset: int) -> tuple[bytes, bytes]:
        stco = _full_box(b"stco", struct.pack(">II", 1, chunk_offset))
        stbl = _box(b"stbl", stsd + stts + stsc + stsz + stco)
        minf = _box(b"minf", smhd + dinf + stbl)
        trak = _box(b"trak", tkhd + _box(b"mdia", mdhd + hdlr + minf))
        return _box(b"moov", mvhd + trak + metadata), _box(b"mdat", mdat_payload)

    moov, mdat = build(0)
    offset = len(ftyp) + len(moov) + 8 if moov_first else len(ftyp) + 8
    moov, mdat = build(offset)
    return ftyp + moov + mdat if moov_first else ftyp + mdat + moov


def write_m4a_with_cover(path: Path, seconds: float, *, cover_art_bytes: int) -> None:
    path.write_bytes(m4a_bytes(seconds, cover_art_bytes=cover_art_bytes))

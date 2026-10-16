"""M4A (ISO base media) parser behaviour on constructed box trees."""

from __future__ import annotations

import struct

import pytest

from backend.api.app.services.media_errors import MediaInspectionError
from backend.api.app.services.media_inspection import AudioFormat, inspect_audio
from tests import media_samples as ms
from tests.media_samples import _box, _full_box


def _inspect(tmp_path, data: bytes):
    path = tmp_path / "a.m4a"
    path.write_bytes(data)
    return inspect_audio(path)


def _rejected(tmp_path, data: bytes) -> bool:
    try:
        _inspect(tmp_path, data)
    except MediaInspectionError:
        return True
    return False


FTYP = _box(b"ftyp", b"M4A " + struct.pack(">I", 0) + b"M4A mp42isom")


def _track(*, handler=b"soun", entry=b"mp4a", mdhd=None, entries=1, timescale=44100, duration=441000):
    if mdhd is None:
        mdhd = _full_box(b"mdhd", struct.pack(">IIIIHH", 0, 0, timescale, duration, 0x55C4, 0))
    hdlr = _full_box(b"hdlr", struct.pack(">I4s12x", 0, handler) + b"H\x00")
    sample = _box(entry, bytes(28))
    stsd = _full_box(b"stsd", struct.pack(">I", entries) + (sample if entries else b""))
    minf = _box(b"minf", _box(b"stbl", stsd))
    return _box(b"trak", _box(b"mdia", mdhd + hdlr + minf))


def _file(*tracks: bytes, tail: bytes = b"") -> bytes:
    return FTYP + _box(b"moov", b"".join(tracks)) + _box(b"mdat", bytes(64)) + tail


def test_a_plain_aac_track_gives_timescale_duration(tmp_path):
    info = _inspect(tmp_path, _file(_track()))
    assert info.format is AudioFormat.M4A
    assert info.duration_seconds == pytest.approx(10.0)


def test_apple_lossless_is_accepted(tmp_path):
    assert _inspect(tmp_path, _file(_track(entry=b"alac"))).duration_seconds == pytest.approx(10.0)


@pytest.mark.parametrize("entry", [b"avc1", b"ac-3", b"samr", b"twos", b"lpcm"])
def test_other_sample_entries_are_not_m4a_audio(tmp_path, entry):
    assert _rejected(tmp_path, _file(_track(entry=entry)))


def test_a_video_only_file_is_rejected(tmp_path):
    assert _rejected(tmp_path, _file(_track(handler=b"vide", entry=b"avc1")))


def test_the_audio_track_is_found_after_a_video_track(tmp_path):
    video = _track(handler=b"vide", entry=b"avc1")
    assert _inspect(tmp_path, _file(video, _track())).duration_seconds == pytest.approx(10.0)


def test_version_1_media_header_with_64_bit_duration(tmp_path):
    mdhd = _full_box(
        b"mdhd", struct.pack(">QQIQHH", 0, 0, 48000, 48000 * 7, 0x55C4, 0)
    )
    mdhd = mdhd[:8] + b"\x01" + mdhd[9:]  # version byte
    assert _inspect(tmp_path, _file(_track(mdhd=mdhd))).duration_seconds == pytest.approx(7.0)


def test_unknown_media_header_version_is_rejected(tmp_path):
    mdhd = _full_box(b"mdhd", struct.pack(">IIIIHH", 0, 0, 44100, 441000, 0, 0))
    mdhd = mdhd[:8] + b"\x02" + mdhd[9:]
    assert _rejected(tmp_path, _file(_track(mdhd=mdhd)))


@pytest.mark.parametrize("timescale,duration", [(0, 100), (44100, 0)])
def test_zero_timescale_or_duration_is_rejected(tmp_path, timescale, duration):
    assert _rejected(tmp_path, _file(_track(timescale=timescale, duration=duration)))


def test_fragmented_mp4_with_empty_media_header_is_rejected(tmp_path):
    assert _rejected(tmp_path, _file(_track(duration=0)))


def test_track_without_sample_entries_is_rejected(tmp_path):
    assert _rejected(tmp_path, _file(_track(entries=0)))


def test_file_without_moov_is_rejected(tmp_path):
    assert _rejected(tmp_path, FTYP + _box(b"mdat", bytes(64)))


def test_moov_after_mdat_is_found(tmp_path):
    data = FTYP + _box(b"mdat", bytes(5000)) + _box(b"moov", _track())
    assert _inspect(tmp_path, data).duration_seconds == pytest.approx(10.0)


def test_64_bit_box_sizes_are_understood(tmp_path):
    payload = b"M4A " + struct.pack(">I", 0) + b"M4A mp42isom"
    big_ftyp = struct.pack(">I4sQ", 1, b"ftyp", 16 + len(payload)) + payload
    data = big_ftyp + _box(b"moov", _track())
    assert _inspect(tmp_path, data).duration_seconds == pytest.approx(10.0)


def test_a_last_box_of_size_zero_runs_to_the_end_of_the_file(tmp_path):
    data = FTYP + _box(b"moov", _track()) + struct.pack(">I4s", 0, b"mdat") + bytes(100)
    assert _inspect(tmp_path, data).duration_seconds == pytest.approx(10.0)


def test_fewer_stray_bytes_than_a_box_header_after_the_last_box_are_ignored(tmp_path):
    assert _inspect(tmp_path, _file(_track(), tail=b"\x00\x00\x00\x00")).duration_seconds == (
        pytest.approx(10.0)
    )


def test_a_box_header_sized_tail_must_be_a_real_box(tmp_path):
    assert _rejected(tmp_path, _file(_track(), tail=b"\x00\x00\x01\x00junk"))


def test_a_child_box_that_overflows_its_parent_is_rejected(tmp_path):
    trak = _track()
    broken = bytearray(_file(trak))
    # Inflate the size of the 'mdia' box inside trak beyond trak.
    at = bytes(broken).index(b"mdia") - 4
    broken[at : at + 4] = struct.pack(">I", 10_000)
    assert _rejected(tmp_path, bytes(broken))


def test_a_box_smaller_than_its_own_header_is_rejected(tmp_path):
    assert _rejected(tmp_path, FTYP + struct.pack(">I4s", 4, b"free") + _box(b"moov", _track()))


@pytest.mark.parametrize("trim", [1, 2, 7, 8, 9, 40])
def test_a_file_cut_at_the_end_is_rejected(tmp_path, trim):
    assert _rejected(tmp_path, _file(_track())[:-trim])


def test_box_nesting_cannot_loop_forever(tmp_path):
    # Thousands of empty boxes at one level hit the per-level cap instead of hanging.
    data = FTYP + _box(b"free", b"") * 20_000 + _box(b"moov", _track())
    assert _rejected(tmp_path, data)


def test_builder_output_with_cover_art_and_late_moov_is_accepted(tmp_path):
    data = ms.m4a_bytes(5.0, cover_art_bytes=300_000, moov_first=False)
    assert _inspect(tmp_path, data).duration_seconds == pytest.approx(5.0, abs=0.05)

"""MPEG audio (MP3) parser behaviour, checked against independently built streams."""

from __future__ import annotations

import random
import struct

import pytest

from backend.api.app.services.media_errors import MediaInspectionError
from backend.api.app.services.media_inspection import AudioFormat, inspect_audio
from tests import media_samples as ms


def _inspect(tmp_path, data: bytes, name: str = "a.mp3"):
    path = tmp_path / name
    path.write_bytes(data)
    return inspect_audio(path)


def _duration(tmp_path, data: bytes) -> float:
    return _inspect(tmp_path, data).duration_seconds


def _rejected(tmp_path, data: bytes) -> bool:
    try:
        _inspect(tmp_path, data)
    except MediaInspectionError:
        return True
    return False


@pytest.mark.parametrize("version", [1, 2, 25])
@pytest.mark.parametrize("layer", [1, 2, 3])
def test_every_version_and_layer_gives_the_exact_duration(tmp_path, version, layer):
    rate = ms.mpeg_sample_rates(version)[0]
    kbps = ms.mpeg_bitrates(version, layer)[3]
    frames = 50
    data = ms.mpeg_stream(frames, version=version, layer=layer, bitrate_kbps=kbps, sample_rate=rate)

    info = _inspect(tmp_path, data)

    assert info.format is AudioFormat.MP3
    expected = frames * ms.mpeg_samples_per_frame(version, layer) / rate
    assert info.duration_seconds == pytest.approx(expected, rel=0.01)


@pytest.mark.parametrize("crc", [False, True])
@pytest.mark.parametrize("channels", [1, 2])
def test_crc_protection_and_channel_mode_do_not_change_the_duration(tmp_path, crc, channels):
    data = ms.mpeg_stream(40, crc=crc, channels=channels, bitrate_kbps=64, sample_rate=44100)
    assert _duration(tmp_path, data) == pytest.approx(40 * 1152 / 44100, rel=0.01)


def test_xing_frame_count_wins_over_the_byte_count(tmp_path):
    # 60 real frames but the header says 100: the declared count is used.
    data = ms.mpeg_stream(60, xing=b"Xing", xing_frames=100)
    assert _duration(tmp_path, data) == pytest.approx(100 * ms.MP3_FRAME_SECONDS)


def test_info_header_is_read_like_xing(tmp_path):
    data = ms.mpeg_stream(60, xing=b"Info", xing_frames=60)
    assert _duration(tmp_path, data) == pytest.approx(60 * ms.MP3_FRAME_SECONDS)


def test_xing_header_without_a_frame_count_falls_back_to_bytes(tmp_path):
    data = ms.mpeg_stream(60, xing=b"Xing", xing_omit_frames=True)
    # The tag frame is audio-sized too, so 61 frames of bytes.
    assert _duration(tmp_path, data) == pytest.approx(61 * ms.MP3_FRAME_SECONDS, rel=0.01)


def test_vbri_frame_count_is_used(tmp_path):
    data = ms.mpeg_stream(60, vbri_frames=200)
    assert _duration(tmp_path, data) == pytest.approx(200 * ms.MP3_FRAME_SECONDS)


def test_id3v2_tag_with_large_cover_art_is_skipped_by_size(tmp_path):
    plain = _duration(tmp_path, ms.mp3_bytes(3.0))
    tagged = _duration(tmp_path, ms.id3v2_tag(cover_art_bytes=2_000_000) + ms.mp3_bytes(3.0))
    assert tagged == pytest.approx(plain)


def test_audio_frames_hidden_inside_a_tag_are_never_scanned(tmp_path):
    # The tag's declared size covers real-looking frames; with no audio after it,
    # the file must be rejected rather than the tag body being scanned.
    body = ms.mp3_bytes(3.0)
    size = len(body)
    synchsafe = bytes(((size >> 21) & 127, (size >> 14) & 127, (size >> 7) & 127, size & 127))
    assert _rejected(tmp_path, b"ID3\x03\x00\x00" + synchsafe + body)


def test_id3v2_footer_and_stacked_tags_are_skipped(tmp_path):
    audio = ms.mp3_bytes(3.0)
    expected = _duration(tmp_path, audio)
    data = ms.id3v2_tag(footer=True) + ms.id3v2_tag(version=4, padding=300) + audio
    assert _duration(tmp_path, data) == pytest.approx(expected)


def test_id3v1_tag_at_the_end_is_not_counted_as_audio(tmp_path):
    audio = ms.mp3_bytes(3.0)
    assert _duration(tmp_path, audio + ms.id3v1_tag()) == pytest.approx(_duration(tmp_path, audio))


def test_id3v2_tag_longer_than_the_file_is_rejected(tmp_path):
    tag = ms.id3v2_tag(cover_art_bytes=5000)
    assert _rejected(tmp_path, tag[:2000])


def test_id3v2_size_with_high_bits_set_is_rejected(tmp_path):
    assert _rejected(tmp_path, b"ID3\x03\x00\x00\xff\xff\xff\xff" + ms.mp3_bytes(3.0))


def test_a_tag_stack_deeper_than_the_limit_is_rejected(tmp_path):
    assert _rejected(tmp_path, ms.id3v2_tag() * 40 + ms.mp3_bytes(3.0))


def test_junk_before_the_first_frame_is_tolerated(tmp_path):
    data = random.Random(1).randbytes(500).replace(b"\xff", b"\x00") + ms.mp3_bytes(3.0)
    assert _duration(tmp_path, data) == pytest.approx(3.0, abs=0.05)


@pytest.mark.parametrize("frames", [1, 2, 3])
def test_fewer_than_four_frames_is_not_enough_to_call_it_audio(tmp_path, frames):
    assert _rejected(tmp_path, ms.mpeg_stream(frames))


def test_four_frames_is_enough(tmp_path):
    assert not _rejected(tmp_path, ms.mpeg_stream(4))


def test_a_stream_cut_inside_the_fourth_frame_is_rejected(tmp_path):
    data = ms.mpeg_stream(4)
    assert _rejected(tmp_path, data[:-1])


def test_frames_that_change_sample_rate_do_not_form_a_run(tmp_path):
    a = ms.mpeg_stream(2, sample_rate=32000)
    b = ms.mpeg_stream(2, sample_rate=48000)
    assert _rejected(tmp_path, a + b)


def test_a_valid_stream_after_one_stray_frame_is_still_found(tmp_path):
    stray = ms.mpeg_stream(1, sample_rate=48000)
    assert not _rejected(tmp_path, stray + ms.mp3_bytes(3.0))


@pytest.mark.parametrize(
    "header",
    [
        b"\xff\xfb\x00\x00",  # free-format bitrate
        b"\xff\xfb\xf0\x00",  # bad bitrate index 15
        b"\xff\xfb\x9c\x00",  # reserved sample rate
        b"\xff\xe9\x90\x00",  # reserved version (01)
        b"\xff\xf9\x90\x00",  # reserved layer (00)
    ],
)
def test_reserved_header_values_never_start_a_run(tmp_path, header):
    assert _rejected(tmp_path, (header + bytes(200)) * 50)


def test_repeated_sync_bytes_do_not_cause_unbounded_work(tmp_path):
    assert _rejected(tmp_path, b"\xff\xfb" * 300_000)


def test_random_data_with_sync_looking_prefixes_is_never_accepted(tmp_path):
    rng = random.Random(7)
    for _ in range(300):
        data = b"\xff\xfb\x90\x00" + rng.randbytes(rng.choice([10, 500, 5000]))
        assert _rejected(tmp_path, data)


def test_xing_frame_count_of_zero_is_rejected_as_non_positive(tmp_path):
    assert _rejected(tmp_path, ms.mpeg_stream(60, xing=b"Xing", xing_frames=0))


def test_header_constants_match_the_independent_tables():
    assert struct.calcsize(">I") == 4
    assert ms.mpeg_samples_per_frame(1, 3) == 1152
    assert ms.mpeg_samples_per_frame(2, 3) == 576
    assert ms.mpeg_samples_per_frame(1, 1) == 384


def test_id3v2_size_that_is_not_synchsafe_is_rejected_even_when_it_fits(tmp_path):
    # Size bytes 00 00 00 80 are not synchsafe; read as plain binary they would
    # say "skip 128 bytes" and land exactly on the audio.
    data = b"ID3\x03\x00\x00\x00\x00\x00\x80" + bytes(128) + ms.mp3_bytes(3.0)
    assert _rejected(tmp_path, data)


def test_scanning_gives_up_after_a_bounded_number_of_sync_candidates(tmp_path):
    # 2,000 sync-looking but invalid headers, then real audio: the scan stops
    # at its candidate cap instead of working through arbitrary junk.
    junk = b"\xff\xe0\x00\x00" * 2000
    assert _rejected(tmp_path, junk + ms.mp3_bytes(3.0))
    assert not _rejected(tmp_path, junk[: 4 * 100] + ms.mp3_bytes(3.0))

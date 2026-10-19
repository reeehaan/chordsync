from __future__ import annotations

import math
import struct
import wave

import pytest

from analysis.lyrics.synced_reference import (
    MINIMUM_TIMED_LINES,
    SyncedLine,
    build_transcript,
    estimate_offset,
    line_spans,
    parse_synced_lyrics,
    timed_line_count,
    vocal_activity,
)

HOP = 0.05
LRC = """[ar:Someone]
[ti:A Song]
[00:10.50] first line here
[00:15.00]
[00:20.00][00:40.25] repeated line
[01:00.00] last line
"""


def test_parses_stamps_repeats_and_markers_and_ignores_metadata():
    lines = parse_synced_lyrics(LRC)

    assert [(line.start, line.text) for line in lines] == [
        (10.5, "first line here"),
        (15.0, ""),
        (20.0, "repeated line"),
        (40.25, "repeated line"),
        (60.0, "last line"),
    ]
    assert timed_line_count(lines) == 4


def test_the_offset_tag_shifts_every_line():
    lines = parse_synced_lyrics("[offset: 500]\n[00:10.00] a line")

    assert lines[0].start == pytest.approx(9.5)


@pytest.mark.parametrize("text", [None, "", "no timestamps here\njust words"])
def test_text_without_timestamps_has_no_lines(text):
    assert parse_synced_lyrics(text) == []


def test_unicode_text_is_kept_intact():
    lines = parse_synced_lyrics("[00:05.00] මන්දාරම් හැන්දෑවේ")

    assert lines[0].text == "මන්දාරම් හැන්දෑවේ"


def test_a_line_ends_at_the_next_one_and_is_capped():
    spans = line_spans(parse_synced_lyrics(LRC))

    first, repeated_one, repeated_two, last = spans
    assert first[:2] == (10.5, pytest.approx(14.95))  # ended by the marker
    assert repeated_one[1] == pytest.approx(32.0)  # capped at 12 s
    assert repeated_two[1] == pytest.approx(52.25)
    assert last[1] > last[0]


# --- offset calibration ----------------------------------------------------------


def _singing_levels(lines, shift_seconds, total_seconds):
    """Loudness that is high while the lines are sung, `shift_seconds` later."""
    count = int(total_seconds / HOP)
    levels = [0.0] * count
    for start, end, _ in line_spans(lines):
        for index in range(
            int((start + shift_seconds) / HOP), int((end + shift_seconds) / HOP)
        ):
            if 0 <= index < count:
                levels[index] = 1000.0
    return levels


def _song_lines():
    # Uneven line lengths and gaps, so the pattern fits at one shift only.
    starts = [8, 19, 27, 41, 48, 63, 71, 90, 104, 113]
    lengths = [6, 4, 9, 5, 11, 6, 12, 8, 5, 10]
    lines = []
    for start, length in zip(starts, lengths):
        lines.append(SyncedLine(float(start), "sung line text"))
        lines.append(SyncedLine(float(start + length), ""))
    return lines


@pytest.mark.parametrize("shift", [-4.5, -1.0, 3.0, 4.4, 8.0])
def test_the_offset_recovers_a_shifted_recording(shift):
    lines = _song_lines()
    levels = _singing_levels(lines, shift, 140.0)

    assert estimate_offset(lines, levels, HOP) == pytest.approx(shift, abs=0.15)


def test_aligned_lyrics_get_no_offset():
    lines = _song_lines()

    assert estimate_offset(lines, _singing_levels(lines, 0.0, 140.0), HOP) == 0.0


def test_too_little_audio_or_too_few_lines_gives_no_offset():
    lines = _song_lines()
    assert estimate_offset(lines, [1.0] * 10, HOP) == 0.0
    assert estimate_offset(lines[: MINIMUM_TIMED_LINES - 2], [1.0] * 400, HOP) == 0.0
    assert estimate_offset(lines, [0.0] * 400, HOP) == 0.0


def test_vocal_activity_reads_a_16_bit_wav(tmp_path):
    path = tmp_path / "vocals.wav"
    rate = 8000
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        silence = struct.pack("<hh", 0, 0) * rate  # 1 s
        tone = b"".join(
            struct.pack("<hh", v, v)
            for v in (
                int(8000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate)
            )
        )  # 1 s
        audio.writeframes(silence + tone)

    levels = vocal_activity(path, HOP)

    assert len(levels) == 40
    assert max(levels[:19]) == 0
    assert min(levels[21:]) > 4000


@pytest.mark.parametrize("content", [b"", b"RIFF not really a wav"])
def test_an_unreadable_file_gives_none(tmp_path, content):
    path = tmp_path / "vocals.wav"
    path.write_bytes(content)

    assert vocal_activity(path) is None
    assert vocal_activity(tmp_path / "missing.wav") is None


# --- the transcript --------------------------------------------------------------


def test_the_transcript_has_the_shape_the_pipeline_expects():
    lines = parse_synced_lyrics(LRC)

    transcript = build_transcript(lines, offset=2.0)

    first = transcript["segments"][0]
    assert first["start"] == pytest.approx(12.5)
    assert first["text"] == " first line here"
    assert [word["word"] for word in first["words"]] == ["first", "line", "here"]
    assert first["words"][0]["start"] == pytest.approx(12.5)
    assert first["words"][-1]["end"] == pytest.approx(first["end"])
    assert transcript["word_segments"] == [
        word for segment in transcript["segments"] for word in segment["words"]
    ]
    assert transcript["language"] == "synced"


def test_word_times_are_ordered_and_split_by_length():
    transcript = build_transcript([SyncedLine(0.0, "a bbbbbbbb"), SyncedLine(9.0, "")])

    short, long = transcript["segments"][0]["words"]
    assert short["end"] == pytest.approx(long["start"])
    assert (long["end"] - long["start"]) > 7 * (short["end"] - short["start"])


def test_lines_outside_the_audio_are_dropped_and_the_end_is_clamped():
    lines = [SyncedLine(5.0, "early line"), SyncedLine(50.0, "after the end")]

    transcript = build_transcript(lines, offset=0.0, total_seconds=20.0)

    assert [s["text"] for s in transcript["segments"]] == [" early line"]
    assert transcript["segments"][0]["end"] <= 20.0


def test_a_negative_offset_never_starts_before_zero():
    transcript = build_transcript([SyncedLine(1.0, "start of song")], offset=-3.0)

    assert all(segment["start"] >= 0 for segment in transcript["segments"])

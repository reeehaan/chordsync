from __future__ import annotations

import random
import struct
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app.main import app
from backend.api.app.routers.analysis_jobs import (
    get_analysis_job_executor,
    get_analysis_job_service,
)
from backend.api.app.services.analysis_input_storage import (
    MAX_AUDIO_DURATION_SECONDS,
    MAX_AUDIO_SIZE_BYTES,
    AudioTooLargeError,
    AudioTooLongError,
    EmptyAudioError,
    InvalidAudioError,
    LocalAnalysisInputStorage,
    UnsupportedAudioFormatError,
)
from backend.api.app.services.analysis_jobs import (
    AnalysisJobService,
    InMemoryAnalysisJobRepository,
)
from backend.api.app.services.media_inspection import (
    AudioFormat,
    MediaInspectionError,
    inspect_audio,
)
from tests import media_samples as samples


def _write(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


@pytest.fixture
def storage(tmp_path) -> LocalAnalysisInputStorage:
    # The real inspector: no injected duration probe.
    return LocalAnalysisInputStorage(tmp_path / "uploads")


def _store(storage, filename: str, content: bytes, job_id: str = "job-1"):
    return storage.store(job_id, filename, "application/octet-stream", BytesIO(content))


# --- valid files --------------------------------------------------------------


def test_mp3_reports_format_duration_and_size(tmp_path):
    blob = samples.mp3_bytes(5.0)
    info = inspect_audio(_write(tmp_path, "a.mp3", blob))

    assert info.format is AudioFormat.MP3
    assert info.duration_seconds == pytest.approx(5.0, abs=0.04)
    assert info.file_size_bytes == len(blob)


def test_mp3_with_large_id3_cover_art_is_valid(tmp_path):
    path = tmp_path / "cover.mp3"
    samples.write_mp3_with_tags(path, 5.0, cover_art_bytes=400_000)
    assert path.stat().st_size > 400_000

    info = inspect_audio(path)

    assert info.format is AudioFormat.MP3
    assert info.duration_seconds == pytest.approx(5.0, abs=0.04)


def test_mp3_with_leading_junk_before_the_first_frame_is_valid(tmp_path):
    info = inspect_audio(_write(tmp_path, "junk.mp3", bytes(3000) + samples.mp3_bytes(5.0)))
    assert info.format is AudioFormat.MP3


def test_m4a_reports_format_and_duration(tmp_path):
    info = inspect_audio(_write(tmp_path, "a.m4a", samples.m4a_bytes(3.0)))
    assert info.format is AudioFormat.M4A
    assert info.duration_seconds == pytest.approx(3.0, abs=0.01)


def test_m4a_with_metadata_and_cover_art_is_valid(tmp_path):
    path = tmp_path / "cover.m4a"
    samples.write_m4a_with_cover(path, 3.0, cover_art_bytes=400_000)
    info = inspect_audio(path)
    assert info.format is AudioFormat.M4A
    assert info.duration_seconds == pytest.approx(3.0, abs=0.01)


def test_m4a_with_audio_data_before_the_metadata_box_is_valid(tmp_path):
    blob = samples.m4a_bytes(3.0, moov_first=False)
    assert inspect_audio(_write(tmp_path, "tail.m4a", blob)).format is AudioFormat.M4A


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"sample_rate": 44100, "channels": 2},
        {"sample_rate": 48000, "channels": 2, "bits": 24, "extensible": True},
        {"sample_rate": 48000, "channels": 2, "bits": 32, "float_samples": True},
    ],
    ids=["pcm16-mono", "pcm16-stereo", "pcm24-extensible", "float32"],
)
def test_wav_variants_report_exact_duration(tmp_path, options):
    info = inspect_audio(_write(tmp_path, "a.wav", samples.wav_bytes(2.0, **options)))
    assert info.format is AudioFormat.WAV
    assert info.duration_seconds == pytest.approx(2.0)


def test_streamed_wav_with_unknown_data_size_uses_the_real_length(tmp_path):
    blob = samples.wav_with_declared_size(1.0, 0xFFFFFFFF)
    assert inspect_audio(_write(tmp_path, "s.wav", blob)).duration_seconds == pytest.approx(1.0)


# --- invalid files ------------------------------------------------------------


def test_random_bytes_are_rejected(tmp_path):
    blob = random.Random(7).randbytes(500_000)
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "noise.mp3", blob))


def test_random_data_is_never_mistaken_for_mp3(tmp_path):
    rng = random.Random(2)
    accepted = 0
    for _ in range(400):
        path = _write(tmp_path, "noise.bin", rng.randbytes(100_000))
        try:
            inspect_audio(path)
            accepted += 1
        except MediaInspectionError:
            pass
    assert accepted == 0


@pytest.mark.parametrize(
    "name,content",
    [
        ("empty", b""),
        ("one-byte", b"R"),
        ("png", b"\x89PNG\r\n\x1a\n" + bytes(5000)),
        ("ogg", b"OggS" + bytes(5000)),
        ("aac-adts", bytes.fromhex("FFF15080") + bytes(5000)),
        ("id3-only", b"ID3\x03\x00\x00\x00\x00\x00\x00"),
        ("corrupt-id3-size", b"ID3\x04\x00\x00\x7f\x7f\x7f\x7f" + samples.mp3_bytes(2.0)),
    ],
)
def test_unsupported_or_malformed_content_is_rejected(tmp_path, name, content):
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, f"{name}.mp3", content))


def test_truncated_mp3_is_rejected_when_too_few_frames_remain(tmp_path):
    whole = samples.mp3_bytes(5.0)
    for cut in (100, 144, 432):  # header fragment, one frame, three frames
        with pytest.raises(MediaInspectionError):
            inspect_audio(_write(tmp_path, "cut.mp3", whole[:cut]))


def test_mp3_cut_mid_stream_is_a_valid_shorter_file(tmp_path):
    # Same as ffprobe: the remaining frames decode, so this is accepted with
    # the shorter duration. Documented limitation, not a rejection case.
    cut = samples.mp3_bytes(5.0)[: int(len(samples.mp3_bytes(5.0)) * 0.4)]
    assert inspect_audio(_write(tmp_path, "cut.mp3", cut)).duration_seconds == pytest.approx(
        2.0, abs=0.05
    )


@pytest.mark.parametrize("keep", [0.25, 0.5, 0.75, 0.99])
@pytest.mark.parametrize("moov_first", [True, False])
def test_truncated_m4a_is_rejected_wherever_it_is_cut(tmp_path, keep, moov_first):
    whole = samples.m4a_bytes(3.0, moov_first=moov_first)
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "cut.m4a", whole[: int(len(whole) * keep)]))


def test_m4a_missing_its_last_byte_is_rejected(tmp_path):
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "cut.m4a", samples.m4a_bytes(3.0)[:-1]))


def test_mp4_without_an_audio_track_is_rejected(tmp_path):
    video_only = samples._box(b"ftyp", b"isom" + bytes(4) + b"isom") + samples._box(
        b"free", bytes(64)
    )
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "novideo.m4a", video_only))


def test_truncated_wav_is_rejected(tmp_path):
    whole = samples.wav_bytes(2.0)
    for cut in (30, len(whole) // 2):
        with pytest.raises(MediaInspectionError):
            inspect_audio(_write(tmp_path, "cut.wav", whole[:cut]))


def test_wav_claiming_more_data_than_the_file_holds_is_rejected(tmp_path):
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "lie.wav", samples.wav_with_declared_size(1.0, 160_000)))


def test_compressed_wav_and_zero_length_wav_are_rejected(tmp_path):
    adpcm = samples._riff(struct.pack("<HHIIHH", 2, 1, 8000, 4000, 256, 4), bytes(4000))
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "adpcm.wav", adpcm))
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "zero.wav", samples.wav_bytes(0.0)))


def test_wav_with_endless_chunks_is_bounded(tmp_path):
    chunks = b"".join(b"junk" + struct.pack("<I", 0) for _ in range(5000))
    blob = b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks
    with pytest.raises(MediaInspectionError):
        inspect_audio(_write(tmp_path, "chunks.wav", blob))


def test_parser_internals_never_leak_in_the_error(tmp_path):
    with pytest.raises(MediaInspectionError) as raised:
        inspect_audio(_write(tmp_path, "noise.mp3", random.Random(1).randbytes(50_000)))
    assert "mutagen" not in str(raised.value).casefold()
    assert str(tmp_path) not in str(raised.value)


# --- storage: extension must agree with the real format ----------------------


def test_storage_accepts_each_supported_format_and_records_the_detected_one(storage):
    mp3 = _store(storage, "song.mp3", samples.mp3_bytes(4.0), "j-mp3")
    m4a = _store(storage, "song.m4a", samples.m4a_bytes(4.0), "j-m4a")
    wav = _store(storage, "song.wav", samples.wav_bytes(4.0), "j-wav")

    assert [m.detected_format for m in (mp3, m4a, wav)] == [
        AudioFormat.MP3,
        AudioFormat.M4A,
        AudioFormat.WAV,
    ]
    assert wav.duration_seconds == pytest.approx(4.0)


@pytest.mark.parametrize(
    "filename,content",
    [
        ("song.wav", samples.mp3_bytes(3.0)),
        ("song.mp3", samples.wav_bytes(3.0)),
        ("song.m4a", samples.wav_bytes(3.0)),
        ("song.mp3", samples.m4a_bytes(3.0)),
        ("song.wav", samples.m4a_bytes(3.0)),
        ("song.m4a", samples.mp3_bytes(3.0)),
    ],
    ids=["mp3-as-wav", "wav-as-mp3", "wav-as-m4a", "m4a-as-mp3", "m4a-as-wav", "mp3-as-m4a"],
)
def test_storage_rejects_extension_and_content_mismatch(storage, filename, content):
    with pytest.raises(InvalidAudioError):
        _store(storage, filename, content)
    assert not (storage.root / "job-1").exists(), "rejected upload left files behind"


def test_storage_rejects_random_bytes_named_as_audio(storage):
    with pytest.raises(InvalidAudioError):
        _store(storage, "song.mp3", random.Random(3).randbytes(200_000))


@pytest.mark.parametrize("filename", ["song.ogg", "song.flac", "song.aac", "song", "song.mp3.exe"])
def test_storage_rejects_unsupported_extensions(storage, filename):
    with pytest.raises(UnsupportedAudioFormatError):
        _store(storage, filename, samples.mp3_bytes(3.0))


def test_storage_rejects_zero_byte_files(storage):
    with pytest.raises(EmptyAudioError):
        _store(storage, "song.mp3", b"")


def test_invalid_audio_error_carries_no_parser_detail(storage):
    with pytest.raises(InvalidAudioError) as raised:
        _store(storage, "song.mp3", random.Random(4).randbytes(10_000))
    assert str(raised.value) == ""
    assert isinstance(raised.value.__cause__, MediaInspectionError)


# --- limits -------------------------------------------------------------------


def test_exactly_360_seconds_is_accepted(storage):
    assert MAX_AUDIO_DURATION_SECONDS == 360.0
    metadata = _store(storage, "limit.mp3", samples.mp3_bytes(360.0))
    assert metadata.duration_seconds == pytest.approx(360.0, abs=0.05)


@pytest.mark.parametrize(
    "filename,content",
    [
        ("long.mp3", samples.mp3_bytes(361.0)),
        ("long.wav", samples.wav_bytes(361.0, sample_rate=8000, bits=8)),
        ("long.m4a", samples.m4a_bytes(361.0)),
    ],
    ids=["mp3", "wav", "m4a"],
)
def test_over_360_seconds_is_rejected(storage, filename, content):
    with pytest.raises(AudioTooLongError):
        _store(storage, filename, content)
    assert not (storage.root / "job-1").exists()


class _ZeroStream:
    """A file-like source that yields zero bytes without allocating them."""

    def __init__(self, size: int) -> None:
        self._remaining = size

    def read(self, count: int = -1) -> bytes:
        count = self._remaining if count < 0 else min(count, self._remaining)
        self._remaining -= count
        return bytes(count)


def test_the_25_mb_limit_applies_to_the_real_constant(storage):
    assert MAX_AUDIO_SIZE_BYTES == 25 * 1024 * 1024
    with pytest.raises(AudioTooLargeError):
        storage.store("big", "song.wav", None, _ZeroStream(MAX_AUDIO_SIZE_BYTES + 1))  # type: ignore[arg-type]
    assert not (storage.root / "big").exists()


# --- HTTP surface: controlled errors, real validator -------------------------


@pytest.fixture
def client(tmp_path):
    input_storage = LocalAnalysisInputStorage(tmp_path / "uploads")
    service = AnalysisJobService(InMemoryAnalysisJobRepository(), input_storage)

    class Deferred:
        def submit(self, job_id: str) -> None:
            pass

    app.dependency_overrides[get_analysis_job_service] = lambda: service
    app.dependency_overrides[get_analysis_job_executor] = lambda: Deferred()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client, filename: str, content: bytes, content_type: str = "application/octet-stream"):
    return client.post(
        "/analysis/jobs",
        data={"title": "Synthetic"},
        files={"audio": (filename, content, content_type)},
    )


def test_a_valid_synthetic_wav_is_accepted_through_the_api(client):
    assert _post(client, "tone.wav", samples.wav_bytes(2.0), "audio/wav").status_code == 202


def test_a_valid_mp3_with_cover_art_is_accepted_through_the_api(client, tmp_path):
    path = tmp_path / "cover.mp3"
    samples.write_mp3_with_tags(path, 4.0, cover_art_bytes=300_000)
    assert _post(client, "cover.mp3", path.read_bytes(), "audio/mpeg").status_code == 202


def test_client_content_type_does_not_decide_acceptance(client):
    assert _post(client, "tone.wav", samples.wav_bytes(2.0), "text/plain").status_code == 202
    assert _post(client, "noise.wav", random.Random(5).randbytes(5000), "audio/wav").status_code == 400


def test_validation_failures_return_controlled_json_without_parser_detail(client):
    response = _post(client, "song.mp3", random.Random(6).randbytes(50_000), "audio/mpeg")

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_audio", "message": "Audio could not be decoded."}
    }
    body = response.text.casefold()
    assert "mutagen" not in body and "traceback" not in body and "sync" not in body


def test_mismatched_extension_returns_the_same_controlled_error(client):
    response = _post(client, "song.wav", samples.mp3_bytes(3.0), "audio/wav")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_audio"


def test_over_long_audio_returns_413_audio_too_long(client):
    response = _post(client, "long.mp3", samples.mp3_bytes(361.0), "audio/mpeg")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "audio_too_long"


from backend.api.app.services.audio_ingestion import calculate_sha256


def test_calculate_sha256(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("ChordSync")

    digest = calculate_sha256(test_file)

    assert len(digest) == 64

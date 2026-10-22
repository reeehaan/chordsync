from pathlib import Path

from analysis.lyrics import production_reference
from analysis.lyrics.filename_identity import identities_from_filename


def test_cleans_a_downloaded_file_name():
    name = "Ma Handawala _feat. Rookantha_ - Bathiya _ Santhush - Spotimate.app"
    assert identities_from_filename(name)[0] == ("Ma Handawala", "Bathiya Santhush")


def test_cleans_brackets_and_extension_and_tries_both_orders():
    guesses = identities_from_filename("Ed Sheeran - Shape of You (Official Audio).mp3")
    assert guesses == [("Ed Sheeran", "Shape of You"), ("Shape of You", "Ed Sheeran")]


def test_a_name_without_a_separator_gives_no_guess():
    assert identities_from_filename("just_a_name.mp3") == []


class _Transport:
    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def fetch(self, identity, *, duration_seconds, credential):
        self.asked.append((identity.title, identity.artist))
        return self.answers(identity)


def _answer(identity):
    return {
        "provider_track_id": "1",
        "title": "Ma Handawala",
        "artist": "Bathiya & Santhush",
        "plain_lyrics": "line one\nline two\nline three",
        "synced_lyrics": "[00:01.00] line one\n[00:02.00] line two",
        "duration_seconds": 265.0,
    }


def _patch_metadata(monkeypatch, **tags):
    metadata = {"duration": 265.0, "title": None, "artist": None, **tags}
    monkeypatch.setattr(production_reference, "get_audio_metadata", lambda path: metadata)


def test_missing_tags_fall_back_to_the_file_name(monkeypatch):
    _patch_metadata(monkeypatch)
    transport = _Transport(_answer)
    reference = production_reference.obtain_lrclib_reference(
        Path("x.mp3"),
        transport=transport,
        source_title="Ma Handawala _feat. Rookantha_ - Bathiya _ Santhush - Spotimate.app",
    )
    assert reference is not None
    assert transport.asked[0] == ("Ma Handawala", "Bathiya Santhush")


def test_a_wrong_guess_is_rejected_by_the_provider_check(monkeypatch):
    _patch_metadata(monkeypatch)
    reference = production_reference.obtain_lrclib_reference(
        Path("x.mp3"),
        transport=_Transport(_answer),
        source_title="Someone Else - Another Song",
    )
    assert reference is None


def test_a_different_length_is_rejected(monkeypatch):
    _patch_metadata(monkeypatch, duration=200.0)
    reference = production_reference.obtain_lrclib_reference(
        Path("x.mp3"),
        transport=_Transport(_answer),
        source_title="Ma Handawala - Bathiya Santhush",
    )
    assert reference is None


def test_no_file_name_and_no_tags_gives_nothing(monkeypatch):
    _patch_metadata(monkeypatch)
    assert (
        production_reference.obtain_lrclib_reference(
            Path("x.mp3"), transport=_Transport(_answer), source_title=None
        )
        is None
    )

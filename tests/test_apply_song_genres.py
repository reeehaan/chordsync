"""Writing reviewed genres: only the three fields, only on finished songs, only valid genres."""

from __future__ import annotations

import pytest

from analysis.genre.genres import GENRES
from scripts.apply_song_genres import InvalidGenres, check, write

JOB = "11111111-1111-4111-8111-111111111111"


def _group(**changes):
    return {"title": "Wonderwall", "keep": JOB, "genres": ["Rock", "Indie"], "artist": "Oasis", **changes}


class FakeTable:
    def __init__(self):
        self.calls = []

    def update_item(self, **request):
        self.calls.append(request)


def test_a_good_row_is_accepted_and_tidied():
    assert check(_group(artist="  The   Smiths ")) == (JOB, ["Rock", "Indie"], "The Smiths")
    assert check(_group(artist=None)) == (JOB, ["Rock", "Indie"], None)


@pytest.mark.parametrize(
    "change",
    [
        {"genres": []},
        {"genres": ["Rock", "Pop", "Indie", "Jazz"]},
        {"genres": ["Polka"]},
        {"genres": ["Rock", "Rock"]},
        {"genres": "Rock"},
        {"genres": None},
        {"keep": "../x"},
        {"keep": None},
        {"keep": "short"},
        {"artist": ""},
        {"artist": "x" * 101},
        {"artist": 5},
    ],
)
def test_a_bad_row_is_refused(change):
    with pytest.raises(InvalidGenres):
        check(_group(**change))


def test_every_genre_on_the_list_is_accepted():
    for genre in GENRES:
        assert check(_group(genres=[genre]))[1] == [genre]


def test_only_the_three_fields_are_set_on_a_finished_song_that_exists():
    table = FakeTable()

    write(table, JOB, ["Rock", "Indie"], "Oasis")

    request = table.calls[0]
    assert request["Key"] == {"PK": f"JOB#{JOB}"}
    assert request["UpdateExpression"] == "SET #g = :g, #src = :src, #a = :a"
    assert request["ConditionExpression"] == "attribute_exists(PK) AND #s = :completed"
    assert request["ExpressionAttributeNames"] == {"#s": "status", "#g": "genres", "#src": "genre_source", "#a": "artist"}
    assert request["ExpressionAttributeValues"] == {":completed": "completed", ":g": ["Rock", "Indie"], ":src": "review", ":a": "Oasis"}


def test_without_an_artist_the_artist_field_is_left_alone():
    table = FakeTable()

    write(table, JOB, ["Sinhala"], None)

    request = table.calls[0]
    assert "artist" not in request["UpdateExpression"] and "#a" not in request["ExpressionAttributeNames"]

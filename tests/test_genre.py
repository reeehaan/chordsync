"""Finding a song's genre: title cleaning, tag mapping, and the MusicBrainz client."""

from __future__ import annotations

import json

import pytest

from analysis.genre import musicbrainz as mb
from analysis.genre.genre_mapping import genres_for_tag, map_tags
from analysis.genre.genres import GENRES
from analysis.genre.title_parser import normalize, parse_song_name


@pytest.mark.parametrize(
    ("raw", "title", "artist"),
    [
        ("Tum Hi Ho - Arijit Singh - Spotimate.app", "Tum Hi Ho", "Arijit Singh"),
        ("Wonderwall - Oasis", "Wonderwall", "Oasis"),
        ("Duvet", "Duvet", None),
        ("Michael Jackson- Heal the World(Lyrics)", "Heal the World", "Michael Jackson"),
        ("There Is a Light That Never Goes Out - Take 1 - The Smiths - Spotimate.app",
         "There Is a Light That Never Goes Out", "The Smiths"),
        ("Love Me Not _feat. Rex Orange County_ - Ravyn Lenae - Spotimate.app", "Love Me Not", "Ravyn Lenae"),
        ("Mage Heenaye - UDAYA SHREE - Spotimate.app 2", "Mage Heenaye", "UDAYA SHREE"),
        ("Tujhe Kitna Chahne Lage _From _Kabir Singh__ - Arijit Singh - Spotimate.app",
         "Tujhe Kitna Chahne Lage", "Arijit Singh"),
        ("Pem Lowe - Gypsies", "Pem Lowe", "Gypsies"),
        ("Take Me Home, Country Roads", "Take Me Home, Country Roads", None),
        ("  Spaced   Out  ", "Spaced Out", None),
        ("Song - Artist - spotimate.app", "Song", "Artist"),
    ],
)
def test_saved_names_become_a_title_and_an_artist(raw, title, artist):
    parsed = parse_song_name(raw)

    assert (parsed.title, parsed.artist) == (title, artist)


def test_the_same_song_written_two_ways_has_one_key():
    assert parse_song_name("Mata Rawana").key == parse_song_name("Mata Rawana - La Signore - Spotimate.app").key
    assert parse_song_name("Pem Lowe").key == parse_song_name("Pem Lowe - Gypsies").key
    assert parse_song_name("Ghost").key != parse_song_name("Her").key
    assert normalize("Beyoncé — Halo!") == "beyonce halo"


def test_an_empty_or_odd_name_never_crashes():
    for raw in ("", "   ", "-", " - - ", "_", "Take 1"):
        assert parse_song_name(raw).title is not None


@pytest.mark.parametrize(
    ("tag", "genres"),
    [
        ("alternative rock", ["Indie", "Rock"]),
        ("britpop", ["Indie", "Rock"]),
        ("indie pop", ["Indie", "Pop"]),
        ("k-pop", ["K-Pop"]),
        ("hip hop", ["Hip-Hop"]),
        ("bollywood", ["Bollywood"]),
        ("sinhala pop", ["Sinhala", "Pop"]),
        ("folk rock", ["Folk", "Rock"]),
        ("heavy metal", ["Metal"]),
        ("rhythm and blues", ["R&B"]),
        ("seen live", []),
        ("", []),
    ],
)
def test_one_tag_points_at_the_right_genres(tag, genres):
    assert sorted(genres_for_tag(tag)) == sorted(genres)


def test_every_mapped_genre_is_on_the_list():
    for tag in ("pop", "rock", "jazz", "blues", "country", "folk", "soul", "punk", "reggae",
                "electronic", "latin", "gospel", "classical", "sinhala", "bollywood", "k-pop"):
        assert set(genres_for_tag(tag)) <= set(GENRES)


def test_the_strongest_genres_win_and_there_are_at_most_three():
    tags = [("rock", 10), ("pop", 8), ("indie", 6), ("jazz", 5), ("blues", 1)]

    assert map_tags(tags) == ["Rock", "Pop", "Indie"]
    assert map_tags([("rock", 10), ("jazz", 1)]) == ["Rock"]  # jazz is far weaker
    assert map_tags([]) == []
    assert map_tags([("seen live", 5)]) == []


def test_a_regional_genre_leads_on_a_tie():
    assert map_tags([("sinhala pop", 2)])[0] == "Sinhala"


# --- the MusicBrainz client ---


def _recording(title, artist, *, score=100, tags=None, artist_id="artist-1"):
    return {
        "title": title,
        "score": score,
        "artist-credit": [{"name": artist, "artist": {"id": artist_id, "name": artist}}],
        "tags": [{"name": name, "count": count} for name, count in (tags or [])],
    }


class FakeServer:
    def __init__(self, routes):
        self.routes = routes
        self.urls: list[str] = []

    def __call__(self, url):
        self.urls.append(url)
        for fragment, responses in self.routes.items():
            if fragment in url:
                response = responses.pop(0) if len(responses) > 1 else responses[0]
                status, payload = response
                return status, json.dumps(payload).encode()
        return 404, b""


def _client(routes):
    server = FakeServer(routes)
    sleeps: list[float] = []
    now = [0.0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    client = mb.MusicBrainz(server, sleep=sleep, clock=lambda: now[0])
    return client, server, sleeps


def test_a_song_with_an_artist_gets_genres_from_the_recording_and_the_artist():
    client, server, _ = _client({
        "/recording?": [(200, {"recordings": [_recording("Wonderwall", "Oasis", tags=[("britpop", 3)])]})],
        "/artist/artist-1": [(200, {"genres": [{"name": "rock", "count": 5}], "tags": [{"name": "british", "count": 2}]})],
    })

    result = client.lookup("Wonderwall", "Oasis")

    assert result.found and result.confidence == "high"
    assert result.genres[0] == "Rock" and "Indie" in result.genres
    assert result.matched_title == "Wonderwall" and result.matched_artist == "Oasis"
    assert "recording%3A%22Wonderwall%22+AND+artist%3A%22Oasis%22" in server.urls[0]
    assert all(url.startswith("https://musicbrainz.org/ws/2/") and "fmt=json" in url for url in server.urls)


def test_a_title_only_match_is_marked_low_confidence():
    client, _, _ = _client({
        "/recording?": [(200, {"recordings": [_recording("Duvet", "Stock, Hausen & Walkman")]})],
        "/artist/artist-1": [(200, {"genres": [{"name": "electronic", "count": 2}]})],
    })

    result = client.lookup("Duvet", None)

    assert result.found and result.confidence == "low"


@pytest.mark.parametrize(
    "recording",
    [
        _recording("Completely Different", "Oasis"),  # the title does not match
        _recording("Wonderwall", "Somebody Else"),  # nor the artist
        _recording("Wonderwall", "Oasis", score=40),  # a weak search hit
    ],
)
def test_wrong_or_weak_matches_are_not_used(recording):
    client, _, _ = _client({"/recording?": [(200, {"recordings": [recording]})]})

    result = client.lookup("Wonderwall", "Oasis")

    assert not result.found and result.genres == []


def test_no_results_means_not_found():
    client, _, _ = _client({"/recording?": [(200, {"recordings": []})]})

    assert not client.lookup("Nothing", "Nobody").found


def test_a_busy_server_is_retried_slowly_then_gives_up():
    client, server, sleeps = _client({"/recording?": [(503, {}), (503, {}), (200, {"recordings": []})]})

    assert not client.lookup("A", "B").found
    assert len(server.urls) == 3
    assert any(wait >= 3 for wait in sleeps) and any(wait >= 8 for wait in sleeps)

    always_busy, _, _ = _client({"/recording?": [(503, {})]})
    with pytest.raises(mb.MusicBrainzError):
        always_busy.lookup("A", "B")


def test_requests_are_spaced_at_least_a_second_apart():
    client, _, sleeps = _client({
        "/recording?": [(200, {"recordings": [_recording("Song", "Band")]})],
        "/artist/artist-1": [(200, {})],
    })

    client.lookup("Song", "Band")

    assert sum(sleeps) >= mb.MIN_SECONDS_BETWEEN_REQUESTS


@pytest.mark.parametrize("status", [400, 404, 500])
def test_other_failures_are_errors(status):
    client, _, _ = _client({"/recording?": [(status, {})]})

    with pytest.raises(mb.MusicBrainzError):
        client.lookup("A", "B")


def test_an_answer_that_is_not_json_or_not_an_object_is_an_error():
    for body in (b"not json", b"[]", b"[" * 50_000):
        client = mb.MusicBrainz(lambda url, body=body: (200, body), sleep=lambda s: None)
        with pytest.raises(mb.MusicBrainzError):
            client.lookup("A", "B")


def test_artist_tags_that_fail_to_load_do_not_lose_the_match():
    client, _, _ = _client({
        "/recording?": [(200, {"recordings": [_recording("Song", "Band", tags=[("jazz", 4)])]})],
        "/artist/artist-1": [(500, {})],
    })

    result = client.lookup("Song", "Band")

    assert result.found and result.genres == ["Jazz"] and "unavailable" in result.note


def test_quotes_in_a_title_cannot_break_out_of_the_query():
    client, server, _ = _client({"/recording?": [(200, {"recordings": []})]})

    client.lookup('Say "hi" \\ there', 'The "Band"')

    assert "%22hi%22" not in server.urls[0]


def test_only_https_is_ever_fetched():
    with pytest.raises(mb.MusicBrainzError):
        mb.fetch_https("http://musicbrainz.org/ws/2/recording")

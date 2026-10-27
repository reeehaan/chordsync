"""A signed-in user's profile: what they told us when they created an account.

It shapes which songs are suggested and nothing else. Only the birth *year* is
kept: the app checks the full birth date for the age limit, and the server has
no use for the day.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MINIMUM_AGE = 13
MAX_NAME_CHARACTERS = 60

# The same list the app offers. Anything else is refused, so the profile cannot
# be used to store free text.
# One list for people's taste and for songs' genres (analysis/genre/genres.py).
from analysis.genre.genres import GENRES  # noqa: E402

MAX_GENRES = len(GENRES)  # a person may pick every one
Experience = Literal["beginner", "little", "intermediate", "advanced"]


def current_year() -> int:
    return datetime.now(timezone.utc).year


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_CHARACTERS * 2)
    birth_year: int = Field(strict=True)  # a real number, not the text "2000"
    genres: list[str] = Field(max_length=MAX_GENRES)
    experience: Experience

    @field_validator("name")
    @classmethod
    def tidy_name(cls, value: str) -> str:
        name = " ".join(value.split())  # trims and collapses runs of spaces
        if not name or len(name) > MAX_NAME_CHARACTERS:
            raise ValueError("name must be 1 to 60 characters")
        # No control, formatting (such as right-to-left marks) or unassigned characters.
        if any(unicodedata.category(character).startswith("C") for character in name):
            raise ValueError("name has characters that are not allowed")
        return name

    @field_validator("birth_year")
    @classmethod
    def old_enough(cls, value: int) -> int:
        if not 1900 <= value <= current_year() - MINIMUM_AGE:
            raise ValueError("birth year is out of range")
        return value

    @field_validator("genres")
    @classmethod
    def known_genres(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(genre not in GENRES for genre in value):
            raise ValueError("genres must be unique and from the list")
        return value


class ProfileResponse(BaseModel):
    name: str
    birth_year: int
    genres: list[str]
    experience: Experience
    updated_at: datetime

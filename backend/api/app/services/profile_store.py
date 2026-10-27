"""Where profiles are kept: one item per signed-in user, found by the owner id."""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from backend.api.app.services.aws_errors import translate_provider_error


@dataclass(frozen=True)
class StoredProfile:
    name: str
    birth_year: int
    genres: list[str]
    experience: str
    updated_at: datetime


class ProfileStore(Protocol):
    def get(self, owner_id: str) -> StoredProfile | None: ...

    def put(self, owner_id: str, profile: StoredProfile) -> None:
        """Replace the owner's profile (create it if there is none)."""
        ...


class InMemoryProfileStore:
    def __init__(self) -> None:
        self._profiles: dict[str, StoredProfile] = {}
        self._lock = threading.Lock()

    def get(self, owner_id: str) -> StoredProfile | None:
        with self._lock:
            profile = self._profiles.get(owner_id)
            return deepcopy(profile) if profile else None

    def put(self, owner_id: str, profile: StoredProfile) -> None:
        with self._lock:
            self._profiles[owner_id] = deepcopy(profile)


class DynamoDbProfileStore:
    """A DynamoDB table with the owner id as its key (``owner_id``)."""

    def __init__(self, table: Any) -> None:
        self._table = table

    def get(self, owner_id: str) -> StoredProfile | None:
        try:
            response = self._table.get_item(Key={"owner_id": owner_id}, ConsistentRead=True)
        except Exception as error:
            raise translate_provider_error(error) from error
        item = response.get("Item")
        if not item:
            return None
        try:
            return StoredProfile(
                name=str(item["name"]),
                birth_year=int(item["birth_year"]),
                genres=[str(genre) for genre in item.get("genres", [])],
                experience=str(item["experience"]),
                updated_at=datetime.fromisoformat(str(item["updated_at"])),
            )
        except (KeyError, ValueError, TypeError):
            return None  # a damaged item reads as "no profile yet"

    def put(self, owner_id: str, profile: StoredProfile) -> None:
        try:
            self._table.update_item(
                Key={"owner_id": owner_id},
                UpdateExpression=(
                    "SET #name = :name, birth_year = :year, genres = :genres, "
                    "experience = :experience, updated_at = :updated, "
                    "created_at = if_not_exists(created_at, :updated)"
                ),
                ExpressionAttributeNames={"#name": "name"},  # "name" is a reserved word
                ExpressionAttributeValues={
                    ":name": profile.name,
                    ":year": profile.birth_year,
                    ":genres": list(profile.genres),
                    ":experience": profile.experience,
                    ":updated": profile.updated_at.astimezone(timezone.utc).isoformat(),
                },
            )
        except Exception as error:
            raise translate_provider_error(error) from error

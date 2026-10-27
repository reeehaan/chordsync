from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Protocol

from backend.api.app.services.cloud_job import CloudJobRecord, CloudJobStatus


class JobWriteConflictError(RuntimeError):
    pass


class CloudJobRepository(Protocol):
    def add(self, job: CloudJobRecord) -> None: ...

    def get(self, job_id: str) -> CloudJobRecord | None: ...

    def pending_dispatch(self, *, limit: int = 100) -> list[CloudJobRecord]: ...

    def list_completed(
        self,
        *,
        limit: int = 200,
        owner_id: str | None = None,
        catalogue_only: bool = False,
    ) -> list[CloudJobRecord]:
        """Finished jobs, newest first, at most [limit]. ``owner_id`` keeps only that
        owner's jobs; ``catalogue_only`` keeps only the shared catalogue (jobs with
        no owner or a demo-token owner). Filtering happens before ``limit``, so one
        group's jobs can never push another group's out of the list."""
        ...

    def save(
        self,
        job: CloudJobRecord,
        *,
        expected_status: CloudJobStatus,
    ) -> None: ...


DEMO_OWNER_PREFIX = "demo:"


def _check_scope(owner_id: str | None, catalogue_only: bool) -> None:
    if owner_id is not None and catalogue_only:
        raise ValueError("choose one owner or the catalogue, not both")
    if owner_id is not None and not owner_id:
        raise ValueError("owner id is empty")


def is_catalogue_owner(owner_id: str | None) -> bool:
    """Songs analysed before accounts existed (no owner, or a demo-token owner)
    form the shared catalogue. A job owned by a signed-in account is private."""
    return owner_id is None or owner_id.startswith(DEMO_OWNER_PREFIX)


def in_scope(job: CloudJobRecord, owner_id: str | None, catalogue_only: bool) -> bool:
    if owner_id is not None:
        return job.owner_id == owner_id
    if catalogue_only:
        return is_catalogue_owner(job.owner_id)
    return True


class InMemoryCloudJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, CloudJobRecord] = {}
        self._lock = Lock()

    def add(self, job: CloudJobRecord) -> None:
        with self._lock:
            if job.job_id in self._jobs:
                raise JobWriteConflictError("Job already exists")
            self._jobs[job.job_id] = deepcopy(job)

    def get(self, job_id: str) -> CloudJobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def pending_dispatch(self, *, limit: int = 100) -> list[CloudJobRecord]:
        with self._lock:
            jobs = [
                deepcopy(job)
                for job in self._jobs.values()
                if job.dispatch_pending
                and job.status is CloudJobStatus.QUEUED
            ]
        return jobs[:limit]

    def list_completed(
        self,
        *,
        limit: int = 200,
        owner_id: str | None = None,
        catalogue_only: bool = False,
    ) -> list[CloudJobRecord]:
        _check_scope(owner_id, catalogue_only)
        with self._lock:
            jobs = [
                deepcopy(job)
                for job in self._jobs.values()
                if job.status is CloudJobStatus.COMPLETED and in_scope(job, owner_id, catalogue_only)
            ]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def save(
        self,
        job: CloudJobRecord,
        *,
        expected_status: CloudJobStatus,
    ) -> None:
        with self._lock:
            stored = self._jobs.get(job.job_id)
            if (
                stored is None
                or stored.status is not expected_status
                or stored.version != job.version
            ):
                raise JobWriteConflictError("Job state changed concurrently")
            job.version += 1
            self._jobs[job.job_id] = deepcopy(job)


class SqliteCloudJobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def add(self, job: CloudJobRecord) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO analysis_jobs(job_id, status, version, payload) "
                    "VALUES (?, ?, ?, ?)",
                    (job.job_id, job.status.value, job.version, _serialize(job)),
                )
        except sqlite3.IntegrityError as error:
            raise JobWriteConflictError("Job already exists") from error

    def get(self, job_id: str) -> CloudJobRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return CloudJobRecord.from_dict(json.loads(row[0])) if row else None

    def pending_dispatch(self, *, limit: int = 100) -> list[CloudJobRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM analysis_jobs WHERE status = ?",
                (CloudJobStatus.QUEUED.value,),
            ).fetchall()
        jobs = [CloudJobRecord.from_dict(json.loads(row[0])) for row in rows]
        return [job for job in jobs if job.dispatch_pending][:limit]

    def list_completed(
        self,
        *,
        limit: int = 200,
        owner_id: str | None = None,
        catalogue_only: bool = False,
    ) -> list[CloudJobRecord]:
        _check_scope(owner_id, catalogue_only)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM analysis_jobs WHERE status = ?",
                (CloudJobStatus.COMPLETED.value,),
            ).fetchall()
        jobs = [
            job
            for job in (CloudJobRecord.from_dict(json.loads(row[0])) for row in rows)
            if in_scope(job, owner_id, catalogue_only)
        ]
        jobs.sort(key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def save(
        self,
        job: CloudJobRecord,
        *,
        expected_status: CloudJobStatus,
    ) -> None:
        next_version = job.version + 1
        payload = job.to_dict()
        payload["version"] = next_version
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, version = ?, payload = ?
                WHERE job_id = ? AND status = ? AND version = ?
                """,
                (
                    job.status.value,
                    next_version,
                    json.dumps(payload, separators=(",", ":")),
                    job.job_id,
                    expected_status.value,
                    job.version,
                ),
            )
            if cursor.rowcount != 1:
                raise JobWriteConflictError("Job state changed concurrently")
        job.version = next_version

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path, timeout=5)


def _serialize(job: CloudJobRecord) -> str:
    return json.dumps(job.to_dict(), separators=(",", ":"))

"""Dispatcher configuration, read from the Lambda environment.

Everything that decides *what* gets started (cluster, task definition,
network, queue) comes from here and nowhere else: the invocation event can
never override it. No credentials are read; the Lambda role supplies them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

LOCK_KEY = "LOCK#worker-dispatch"
DEFAULT_LEASE_SECONDS = 60
MIN_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 300
MAX_WORKER_TASKS_LIMIT = 5

_REGION = re.compile(r"^[a-z]{2}(-[a-z]+)+-\d$")
_CLUSTER = re.compile(r"^[A-Za-z0-9_-]{1,255}$")
# A family name or a task-definition ARN without a revision. A pinned
# ``family:revision`` is refused so a stale revision cannot be started by habit.
_TASK_DEFINITION = re.compile(
    r"^([A-Za-z0-9_-]{1,255}|arn:aws:ecs:[a-z0-9-]+:\d{12}:task-definition/[A-Za-z0-9_-]{1,255})$"
)
_SUBNET = re.compile(r"^subnet-[0-9a-f]{8,17}$")
_SECURITY_GROUP = re.compile(r"^sg-[0-9a-f]{8,17}$")
_QUEUE_URL = re.compile(r"^https://sqs\.[a-z0-9-]+\.amazonaws\.com/\d{12}/[A-Za-z0-9_-]{1,80}$")
_TABLE = re.compile(r"^[A-Za-z0-9_.-]{3,255}$")


class DispatcherConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DispatcherConfig:
    region: str
    cluster: str
    task_definition: str
    subnet_ids: tuple[str, ...]
    security_group_id: str
    queue_url: str
    lock_table: str
    max_worker_tasks: int = 1
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    # SQS counters lag; after an API-triggered call that sees an empty queue,
    # look again this many times, this many seconds apart.
    recheck_attempts: int = 2
    recheck_delay_seconds: float = 3.0

    @property
    def task_family(self) -> str:
        """Family name, whether the config holds a bare family or an ARN."""
        return self.task_definition.rsplit("/", 1)[-1]

    @classmethod
    def from_env(cls, environment: Mapping[str, str]) -> DispatcherConfig:
        def value(name: str) -> str:
            raw = environment.get(name, "").strip()
            if not raw:
                raise DispatcherConfigurationError(f"{name} is required")
            return raw

        def checked(name: str, pattern: re.Pattern[str]) -> str:
            raw = value(name)
            if not pattern.fullmatch(raw):
                raise DispatcherConfigurationError(f"{name} is not valid")
            return raw

        subnets = tuple(
            part.strip() for part in value("CHORDSYNC_WORKER_SUBNET_IDS").split(",") if part.strip()
        )
        if not subnets or not all(_SUBNET.fullmatch(item) for item in subnets):
            raise DispatcherConfigurationError("CHORDSYNC_WORKER_SUBNET_IDS is not valid")
        return cls(
            region=checked("AWS_REGION", _REGION),
            cluster=checked("CHORDSYNC_ECS_CLUSTER", _CLUSTER),
            task_definition=checked("CHORDSYNC_WORKER_TASK_DEFINITION", _TASK_DEFINITION),
            subnet_ids=subnets,
            security_group_id=checked("CHORDSYNC_WORKER_SECURITY_GROUP_ID", _SECURITY_GROUP),
            queue_url=checked("CHORDSYNC_SQS_ANALYSIS_QUEUE_URL", _QUEUE_URL),
            lock_table=checked("CHORDSYNC_DYNAMODB_JOB_TABLE", _TABLE),
            max_worker_tasks=_bounded_int(
                environment, "CHORDSYNC_MAX_WORKER_TASKS", 1, 1, MAX_WORKER_TASKS_LIMIT
            ),
            lease_seconds=_bounded_int(
                environment,
                "CHORDSYNC_DISPATCH_LEASE_SECONDS",
                DEFAULT_LEASE_SECONDS,
                MIN_LEASE_SECONDS,
                MAX_LEASE_SECONDS,
            ),
        )


def _bounded_int(
    environment: Mapping[str, str], name: str, default: int, low: int, high: int
) -> int:
    raw = environment.get(name, "").strip()
    if not raw:
        return default
    try:
        number = int(raw)
    except ValueError as error:
        raise DispatcherConfigurationError(f"{name} must be a whole number") from error
    if not low <= number <= high:
        raise DispatcherConfigurationError(f"{name} must be between {low} and {high}")
    return number

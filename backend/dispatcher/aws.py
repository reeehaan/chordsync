"""boto3 adapters for the dispatcher. Each call is the narrowest one that works.

SQS:      GetQueueAttributes (never Receive/Delete/ChangeMessageVisibility)
ECS:      ListTasks, DescribeTasks, RunTask
DynamoDB: conditional PutItem and DeleteItem on one lock item
"""

from __future__ import annotations

import time
from typing import Any, Callable

from backend.dispatcher.config import LOCK_KEY, DispatcherConfig
from backend.dispatcher.dispatcher import (
    ActiveTask,
    DependencyError,
    QueueDepth,
    RunTaskRejected,
)

# lastStatus values for a task that is, or is about to be, using the slot.
# PENDING counts as active so two dispatchers never start duplicates.
ACTIVE_TASK_STATUSES = frozenset({"PROVISIONING", "PENDING", "ACTIVATING", "RUNNING"})
_LIST_PAGE_LIMIT = 10
_QUEUE_ATTRIBUTES = [
    "ApproximateNumberOfMessages",
    "ApproximateNumberOfMessagesNotVisible",
    "ApproximateNumberOfMessagesDelayed",
]
STARTED_BY = "chordsync-dispatcher"


def _code(error: BaseException) -> str:
    """A safe label for an AWS error: its code, else its class name."""
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if isinstance(code, str) and code:
            return code[:64]
    return type(error).__name__[:64]


class SqsQueueDepth:
    def __init__(self, client: Any, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url

    def depth(self) -> QueueDepth:
        try:
            response = self._client.get_queue_attributes(
                QueueUrl=self._queue_url, AttributeNames=_QUEUE_ATTRIBUTES
            )
            attributes = response["Attributes"]
            return QueueDepth(
                visible=int(attributes["ApproximateNumberOfMessages"]),
                in_flight=int(attributes["ApproximateNumberOfMessagesNotVisible"]),
                delayed=int(attributes.get("ApproximateNumberOfMessagesDelayed", 0)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DependencyError("MalformedQueueAttributes") from error
        except Exception as error:
            raise DependencyError(_code(error)) from error


class EcsWorkerTasks:
    def __init__(self, client: Any, config: DispatcherConfig) -> None:
        self._client = client
        self._config = config

    def active(self) -> list[ActiveTask]:
        family = self._config.task_family
        arns: list[str] = []
        try:
            token = None
            for _ in range(_LIST_PAGE_LIMIT):
                request: dict[str, Any] = {
                    "cluster": self._config.cluster,
                    "family": family,
                    "desiredStatus": "RUNNING",
                }
                if token:
                    request["nextToken"] = token
                page = self._client.list_tasks(**request)
                arns.extend(page.get("taskArns", []))
                token = page.get("nextToken")
                if not token:
                    break
            if not arns:
                return []
            described: list[ActiveTask] = []
            for start in range(0, len(arns), 100):
                response = self._client.describe_tasks(
                    cluster=self._config.cluster, tasks=arns[start : start + 100]
                )
                for task in response.get("tasks", []):
                    # Only this worker family counts; unrelated tasks are ignored.
                    definition = str(task.get("taskDefinitionArn", ""))
                    if definition.rsplit("/", 1)[-1].rsplit(":", 1)[0] != family:
                        continue
                    status = str(task.get("lastStatus", ""))
                    if status in ACTIVE_TASK_STATUSES:
                        described.append(ActiveTask(str(task["taskArn"]), status))
            return described
        except Exception as error:
            raise DependencyError(_code(error)) from error

    def start(self) -> str:
        config = self._config
        try:
            response = self._client.run_task(
                cluster=config.cluster,
                taskDefinition=config.task_definition,
                launchType="FARGATE",
                count=1,
                startedBy=STARTED_BY,
                networkConfiguration={
                    "awsvpcConfiguration": {
                        "subnets": list(config.subnet_ids),
                        "securityGroups": [config.security_group_id],
                        "assignPublicIp": "ENABLED",
                    }
                },
            )
        except Exception as error:
            raise RunTaskRejected(_code(error)) from error
        failures = response.get("failures") or []
        tasks = response.get("tasks") or []
        if failures or not tasks:
            # ``reason`` is ECS's short code, e.g. "RESOURCE:FARGATE" or
            # "Capacity is unavailable at this time".
            reason = str((failures[0] or {}).get("reason", "NoTaskStarted")) if failures else "NoTaskStarted"
            raise RunTaskRejected(reason[:120])
        return str(tasks[0]["taskArn"])


class DynamoDbLease:
    """A short lease on one item in the jobs table (key ``LOCK#worker-dispatch``).

    Acquired by a conditional PutItem that succeeds only if the item is absent
    or its ``expires_at`` has passed, so a crashed holder blocks nobody beyond
    the lease.
    """

    def __init__(
        self,
        table: Any,
        *,
        key: str = LOCK_KEY,
        clock: Callable[[], float] = time.time,
        conflict_codes: frozenset[str] = frozenset({"ConditionalCheckFailedException"}),
    ) -> None:
        self._table = table
        self._key = key
        self._clock = clock
        self._conflict_codes = conflict_codes

    def acquire(self, owner: str, ttl_seconds: int) -> bool:
        now = int(self._clock())
        try:
            self._table.put_item(
                Item={"PK": self._key, "owner": owner, "expires_at": now + ttl_seconds},
                ConditionExpression="attribute_not_exists(PK) OR expires_at < :now",
                ExpressionAttributeValues={":now": now},
            )
        except Exception as error:
            if _code(error) in self._conflict_codes:
                return False
            raise DependencyError(_code(error)) from error
        return True

    def release(self, owner: str) -> None:
        try:
            self._table.delete_item(
                Key={"PK": self._key},
                ConditionExpression="#owner = :owner",
                ExpressionAttributeNames={"#owner": "owner"},
                ExpressionAttributeValues={":owner": owner},
            )
        except Exception as error:
            if _code(error) in self._conflict_codes:
                return  # the lease already expired and someone else holds it
            raise DependencyError(_code(error)) from error

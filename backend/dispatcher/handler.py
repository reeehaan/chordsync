"""Lambda entry point: backend.dispatcher.handler.lambda_handler.

Only "reason" is read from the event. Nothing in it can choose the task,
command, image, role, network or queue.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any, Mapping

from backend.dispatcher.aws import DynamoDbLease, EcsWorkerTasks, SqsQueueDepth
from backend.dispatcher.config import DispatcherConfig
from backend.dispatcher.dispatcher import WorkerDispatcher


def build_dispatcher(
    config: DispatcherConfig,
    *,
    sqs_client: Any,
    ecs_client: Any,
    dynamodb_table: Any,
    sleep=time.sleep,
) -> WorkerDispatcher:
    return WorkerDispatcher(
        SqsQueueDepth(sqs_client, config.queue_url),
        EcsWorkerTasks(ecs_client, config),
        DynamoDbLease(dynamodb_table),
        max_active_workers=config.max_worker_tasks,
        lease_seconds=config.lease_seconds,
        recheck_attempts=config.recheck_attempts,
        recheck_delay_seconds=config.recheck_delay_seconds,
        sleep=sleep,
    )


@lru_cache(maxsize=1)
def _default_dispatcher() -> WorkerDispatcher:
    import boto3  # supplied by the Lambda Python runtime

    config = DispatcherConfig.from_env(os.environ)
    session = boto3.session.Session(region_name=config.region)
    return build_dispatcher(
        config,
        sqs_client=session.client("sqs"),
        ecs_client=session.client("ecs"),
        dynamodb_table=session.resource("dynamodb").Table(config.lock_table),
    )


def handle(event: Mapping[str, Any] | None, dispatcher: WorkerDispatcher) -> dict[str, Any]:
    reason = event.get("reason") if isinstance(event, Mapping) else None
    result = dispatcher.dispatch(reason if isinstance(reason, str) else "unknown")
    return result.as_dict()


def lambda_handler(event: Mapping[str, Any] | None, _context: Any = None) -> dict[str, Any]:
    # A bad configuration raises here and fails the invocation.
    return handle(event, _default_dispatcher())

from __future__ import annotations

from typing import Any

from backend.api.app.services.analysis_job_queue import (
    AnalysisJobDescriptor,
    QueueDelivery,
    QueueMessageError,
)
from backend.api.app.services.aws_errors import translate_provider_error
from backend.api.app.services.visibility_heartbeat import (
    DEFAULT_VISIBILITY_POLICY,
)


class SqsAnalysisJobQueue:
    def __init__(
        self,
        client: Any,
        queue_url: str,
        *,
        wait_time_seconds: int = 20,
        visibility_timeout_seconds: int = (
            DEFAULT_VISIBILITY_POLICY.initial_timeout_seconds
        ),
    ) -> None:
        if not queue_url.strip():
            raise ValueError("SQS analysis queue URL is required")
        self._client = client
        self._queue_url = queue_url
        self._wait_time = wait_time_seconds
        self._visibility_timeout = visibility_timeout_seconds

    def enqueue(self, descriptor: AnalysisJobDescriptor) -> None:
        try:
            self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=descriptor.to_json(),
            )
        except Exception as error:
            raise translate_provider_error(error) from error

    def receive(self) -> QueueDelivery | None:
        try:
            response = self._client.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=self._wait_time,
                VisibilityTimeout=self._visibility_timeout,
                AttributeNames=["ApproximateReceiveCount"],
            )
        except Exception as error:
            raise translate_provider_error(error) from error
        messages = response.get("Messages", [])
        if not messages:
            return None
        message = messages[0]
        try:
            receipt = str(message["ReceiptHandle"])
            count = int(message.get("Attributes", {}).get(
                "ApproximateReceiveCount", "1"
            ))
            descriptor = AnalysisJobDescriptor.from_json(str(message["Body"]))
        except (KeyError, TypeError, ValueError) as error:
            raise QueueMessageError("Malformed queue delivery") from error
        return QueueDelivery(descriptor, receipt, count)

    def acknowledge(self, delivery: QueueDelivery) -> None:
        try:
            self._client.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=delivery.receipt_handle,
            )
        except Exception as error:
            raise translate_provider_error(error) from error

    def release(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int = 0,
    ) -> None:
        self._change_visibility(delivery, visibility_timeout_seconds)

    def extend_visibility(
        self,
        delivery: QueueDelivery,
        *,
        visibility_timeout_seconds: int,
    ) -> None:
        self._change_visibility(delivery, visibility_timeout_seconds)

    def _change_visibility(
        self,
        delivery: QueueDelivery,
        visibility_timeout_seconds: int,
    ) -> None:
        try:
            self._client.change_message_visibility(
                QueueUrl=self._queue_url,
                ReceiptHandle=delivery.receipt_handle,
                VisibilityTimeout=visibility_timeout_seconds,
            )
        except Exception as error:
            raise translate_provider_error(error) from error

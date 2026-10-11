from __future__ import annotations

import json

import pytest

from backend.api.app.services.analysis_job_queue import (
    AnalysisJobDescriptor,
    InMemoryAnalysisJobQueue,
    QueueMessageError,
)
from backend.api.app.services.aws_errors import (
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.sqs_analysis_job_queue import SqsAnalysisJobQueue
from backend.api.app.services.visibility_heartbeat import (
    DEFAULT_VISIBILITY_POLICY,
)
from tests.test_aws_cloud_adapters import FakeAwsError


def _descriptor() -> AnalysisJobDescriptor:
    return AnalysisJobDescriptor(
        job_id="job-one",
        source_artifact_key="jobs/job-one/source/input.mp3",
        title="Tagged song",
    )


def test_queue_message_serialization_is_versioned_small_and_deterministic():
    encoded = _descriptor().to_json()

    assert AnalysisJobDescriptor.from_json(encoded) == _descriptor()
    assert json.loads(encoded) == {
        "schema_version": 1,
        "job_id": "job-one",
        "source_artifact_key": "jobs/job-one/source/input.mp3",
        "title": "Tagged song",
    }
    assert len(encoded) < 1024
    assert "audio" not in encoded
    assert "/Users/" not in encoded


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"schema_version":1}',
        '{"schema_version":1,"job_id":"job","source_artifact_key":"/tmp/input.mp3","title":"Song"}',
    ],
)
def test_queue_message_rejects_malformed_or_unsafe_payload(payload):
    with pytest.raises(QueueMessageError):
        AnalysisJobDescriptor.from_json(payload)


def test_queue_message_rejects_unsupported_schema():
    payload = json.loads(_descriptor().to_json())
    payload["schema_version"] = 2

    with pytest.raises(QueueMessageError, match="Unsupported"):
        AnalysisJobDescriptor.from_json(json.dumps(payload))


def test_local_queue_ack_and_retry_make_delivery_explicit():
    queue = InMemoryAnalysisJobQueue()
    queue.enqueue(_descriptor())
    first = queue.receive()
    assert first.receive_count == 1

    queue.extend_visibility(first, visibility_timeout_seconds=120)
    queue.release(first)
    duplicate = queue.receive()

    assert duplicate.descriptor == first.descriptor
    assert duplicate.receive_count == 2
    assert duplicate.receipt_handle != first.receipt_handle
    queue.acknowledge(duplicate)
    assert queue.receive() is None


class FakeSqsClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.calls: list[tuple[str, dict]] = []
        self.fail: tuple[str, str] | None = None
        self.receive_count = 0

    def _call(self, operation, values):
        self.calls.append((operation, values))
        if self.fail and self.fail[0] == operation:
            raise FakeAwsError(self.fail[1])

    def send_message(self, **values):
        self._call("send", values)
        self.messages.append(
            {
                "Body": values["MessageBody"],
                "ReceiptHandle": f"receipt-{len(self.messages) + 1}",
                "Attributes": {"ApproximateReceiveCount": "1"},
            }
        )
        return {"MessageId": "safe-id"}

    def receive_message(self, **values):
        self._call("receive", values)
        if not self.messages:
            return {}
        self.receive_count += 1
        message = dict(self.messages[0])
        message["Attributes"] = {
            "ApproximateReceiveCount": str(self.receive_count)
        }
        return {"Messages": [message]}

    def delete_message(self, **values):
        self._call("delete", values)
        if self.messages:
            self.messages.pop(0)
        return {}

    def change_message_visibility(self, **values):
        self._call("visibility", values)
        return {}


def test_sqs_enqueue_receive_ack_and_long_poll_shape():
    client = FakeSqsClient()
    queue = SqsAnalysisJobQueue(client, "https://sqs.invalid/private")

    queue.enqueue(_descriptor())
    delivery = queue.receive()
    queue.extend_visibility(delivery, visibility_timeout_seconds=300)
    queue.acknowledge(delivery)

    assert json.loads(client.calls[0][1]["MessageBody"])["schema_version"] == 1
    receive = client.calls[1][1]
    assert receive["WaitTimeSeconds"] == 20
    assert receive["VisibilityTimeout"] == (
        DEFAULT_VISIBILITY_POLICY.initial_timeout_seconds
    )
    assert receive["VisibilityTimeout"] == 1800
    assert delivery.descriptor == _descriptor()
    assert queue.receive() is None


def test_sqs_duplicate_delivery_is_represented_by_receive_count():
    client = FakeSqsClient()
    queue = SqsAnalysisJobQueue(client, "https://sqs.invalid/private")
    queue.enqueue(_descriptor())

    first = queue.receive()
    second = queue.receive()

    assert first.receive_count == 1
    assert second.receive_count == 2


def test_sqs_malformed_message_fails_closed():
    client = FakeSqsClient()
    client.messages.append({"Body": "{}", "ReceiptHandle": "receipt"})

    with pytest.raises(QueueMessageError):
        SqsAnalysisJobQueue(client, "https://sqs.invalid/private").receive()


@pytest.mark.parametrize("operation", ["send", "receive", "delete"])
def test_sqs_translates_temporary_provider_failures(operation):
    client = FakeSqsClient()
    queue = SqsAnalysisJobQueue(client, "https://sqs.invalid/private")
    if operation == "delete":
        queue.enqueue(_descriptor())
        delivery = queue.receive()
    else:
        delivery = None
    client.fail = (operation, "ServiceUnavailable")

    with pytest.raises(CloudProviderError) as captured:
        if operation == "send":
            queue.enqueue(_descriptor())
        elif operation == "receive":
            queue.receive()
        else:
            queue.acknowledge(delivery)
    assert captured.value.kind is CloudProviderErrorKind.TEMPORARY_UNAVAILABLE

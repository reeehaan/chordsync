"""Worker dispatcher (S7-T04): fakes only, no AWS."""

from __future__ import annotations

import ast
import json
import threading
import time
from pathlib import Path

import pytest

from backend.dispatcher import handler
from backend.dispatcher.aws import DynamoDbLease, EcsWorkerTasks, SqsQueueDepth
from backend.dispatcher.config import (
    LOCK_KEY,
    DispatcherConfig,
    DispatcherConfigurationError,
)
from backend.dispatcher.dispatcher import (
    DependencyError,
    Outcome,
    QueueDepth,
    WorkerDispatcher,
)

ROOT = Path(__file__).resolve().parents[1]
ENV = {
    "AWS_REGION": "ap-southeast-1",
    "CHORDSYNC_ECS_CLUSTER": "chordsync-student-demo-analysis",
    "CHORDSYNC_WORKER_TASK_DEFINITION": "chordsync-student-demo-worker",
    "CHORDSYNC_WORKER_SUBNET_IDS": "subnet-0a1b2c3d4e5f60718,subnet-1a1b2c3d4e5f60718",
    "CHORDSYNC_WORKER_SECURITY_GROUP_ID": "sg-0a1b2c3d4e5f60718",
    "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL": "https://sqs.ap-southeast-1.amazonaws.com/123456789012/chordsync-student-demo-analysis",
    "CHORDSYNC_DYNAMODB_JOB_TABLE": "chordsync-student-demo-jobs",
}
CONFIG = DispatcherConfig.from_env(ENV)
FAMILY = "chordsync-student-demo-worker"
TASK_DEF_ARN = f"arn:aws:ecs:ap-southeast-1:123456789012:task-definition/{FAMILY}:7"


class AwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__("private provider text /account/123")
        self.response = {"Error": {"Code": code, "Message": "private provider text"}}


class FakeSqs:
    """Only GetQueueAttributes exists; any other call is an AttributeError."""

    def __init__(self, visible=0, in_flight=0, delayed=0) -> None:
        self.attributes = [(visible, in_flight, delayed)]
        self.calls: list[str] = []
        self.error: Exception | None = None

    def get_queue_attributes(self, **values):
        self.calls.append("get_queue_attributes")
        assert values["QueueUrl"] == CONFIG.queue_url
        if self.error:
            raise self.error
        visible, in_flight, delayed = self.attributes[0]
        if len(self.attributes) > 1:
            self.attributes.pop(0)
        return {
            "Attributes": {
                "ApproximateNumberOfMessages": str(visible),
                "ApproximateNumberOfMessagesNotVisible": str(in_flight),
                "ApproximateNumberOfMessagesDelayed": str(delayed),
            }
        }


class FakeEcs:
    def __init__(self, *, latency=0.0, listing_lag=0.0) -> None:
        self.tasks: dict[str, dict] = {}
        self.run_calls: list[dict] = []
        self.latency = latency
        self.listing_lag = listing_lag
        self.run_error: Exception | None = None
        self.run_response: dict | None = None
        self.list_error: Exception | None = None
        self._lock = threading.Lock()
        self._counter = 0

    def add_task(self, status, family=FAMILY, desired="RUNNING"):
        with self._lock:
            self._counter += 1
            arn = f"arn:aws:ecs:ap-southeast-1:123456789012:task/{CONFIG.cluster}/t{self._counter}"
            self.tasks[arn] = {
                "taskArn": arn,
                "lastStatus": status,
                "desiredStatus": desired,
                "taskDefinitionArn": f"arn:aws:ecs:ap-southeast-1:123456789012:task-definition/{family}:7",
                "visible_at": 0.0,
            }
            return arn

    def list_tasks(self, **values):
        if self.list_error:
            raise self.list_error
        assert values["cluster"] == CONFIG.cluster
        assert values["family"] == FAMILY
        assert values["desiredStatus"] == "RUNNING"
        now = time.monotonic()
        with self._lock:
            arns = [
                arn
                for arn, task in self.tasks.items()
                if task["desiredStatus"] == "RUNNING" and task["visible_at"] <= now
            ]
        return {"taskArns": arns}

    def describe_tasks(self, **values):
        assert values["cluster"] == CONFIG.cluster
        with self._lock:
            return {"tasks": [dict(self.tasks[arn]) for arn in values["tasks"]], "failures": []}

    def run_task(self, **values):
        time.sleep(self.latency)
        with self._lock:
            self.run_calls.append(values)
        if self.run_error:
            raise self.run_error
        if self.run_response is not None:
            return self.run_response
        arn = self.add_task("PENDING")
        self.tasks[arn]["visible_at"] = time.monotonic() + self.listing_lag
        return {"tasks": [{"taskArn": arn}], "failures": []}


class FakeTable:
    """DynamoDB conditional semantics for the two lock expressions."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}
        self.error: Exception | None = None
        self.puts = 0
        self._lock = threading.Lock()

    def put_item(self, *, Item, ConditionExpression, ExpressionAttributeValues):
        if self.error:
            raise self.error
        assert ConditionExpression == "attribute_not_exists(PK) OR expires_at < :now"
        with self._lock:
            self.puts += 1
            current = self.items.get(Item["PK"])
            if current is not None and not current["expires_at"] < ExpressionAttributeValues[":now"]:
                raise AwsError("ConditionalCheckFailedException")
            self.items[Item["PK"]] = dict(Item)

    def delete_item(self, *, Key, ConditionExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        assert ConditionExpression == "#owner = :owner"
        with self._lock:
            current = self.items.get(Key["PK"])
            if current is None or current["owner"] != ExpressionAttributeValues[":owner"]:
                raise AwsError("ConditionalCheckFailedException")
            del self.items[Key["PK"]]


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


class World:
    def __init__(self, visible=1, in_flight=0, **ecs_options) -> None:
        self.sqs = FakeSqs(visible, in_flight)
        self.ecs = FakeEcs(**ecs_options)
        self.table = FakeTable()
        self.clock = Clock()
        self.sleeps: list[float] = []

    def dispatcher(self, **overrides) -> WorkerDispatcher:
        options = {
            "max_active_workers": 1,
            "lease_seconds": 60,
            "recheck_attempts": 2,
            "recheck_delay_seconds": 3.0,
            "sleep": self.sleeps.append,
        }
        options.update(overrides)
        return WorkerDispatcher(
            SqsQueueDepth(self.sqs, CONFIG.queue_url),
            EcsWorkerTasks(self.ecs, CONFIG),
            DynamoDbLease(self.table, clock=self.clock),
            **options,
        )


# --- work detection --------------------------------------------------------------


def test_no_visible_messages_starts_nothing_and_takes_no_lock():
    world = World(visible=0)

    result = world.dispatcher().dispatch("scheduled_reconcile")

    assert result.outcome is Outcome.NO_WORK
    assert world.ecs.run_calls == []
    assert world.table.puts == 0


def test_in_flight_work_without_visible_work_starts_nothing():
    # A live worker holds it, or it returns by itself when its timeout ends.
    world = World(visible=0, in_flight=2)
    assert world.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.NO_WORK
    assert world.ecs.run_calls == []


def test_one_visible_message_starts_exactly_one_worker():
    world = World(visible=1)

    result = world.dispatcher().dispatch("scheduled_reconcile")

    assert result.outcome is Outcome.WORKER_STARTED
    assert result.task_arn and result.task_arn in world.ecs.tasks
    assert len(world.ecs.run_calls) == 1


def test_many_messages_still_start_only_one_worker():
    world = World(visible=40)
    dispatcher = world.dispatcher()
    first = dispatcher.dispatch("scheduled_reconcile")
    second = dispatcher.dispatch("scheduled_reconcile")
    assert first.outcome is Outcome.WORKER_STARTED
    assert second.outcome is Outcome.WORKER_ALREADY_ACTIVE
    assert len(world.ecs.run_calls) == 1


def test_the_queue_is_read_with_attributes_only():
    world = World(visible=1)
    world.dispatcher().dispatch("job_dispatched")
    assert set(world.sqs.calls) == {"get_queue_attributes"}
    for forbidden in ("receive_message", "delete_message", "change_message_visibility", "send_message", "purge_queue"):
        assert not hasattr(world.sqs, forbidden)


# --- worker detection -------------------------------------------------------------


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "PROVISIONING", "ACTIVATING"])
def test_an_active_worker_blocks_a_second_one(status):
    world = World(visible=3)
    world.ecs.add_task(status)

    result = world.dispatcher().dispatch("scheduled_reconcile")

    assert result.outcome is Outcome.WORKER_ALREADY_ACTIVE
    assert world.ecs.run_calls == []
    assert world.table.puts == 0  # decided before touching the lock


def test_a_stopping_or_stopped_worker_does_not_block():
    world = World(visible=1)
    world.ecs.add_task("DEACTIVATING", desired="STOPPED")
    world.ecs.add_task("STOPPED", desired="STOPPED")
    assert world.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.WORKER_STARTED


def test_tasks_of_other_families_are_ignored():
    world = World(visible=1)
    world.ecs.add_task("RUNNING", family="some-other-service")
    assert world.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.WORKER_STARTED


# --- RunTask configuration --------------------------------------------------------


def test_run_task_uses_only_configured_values():
    world = World(visible=1)
    world.dispatcher().dispatch("job_dispatched")

    (call,) = world.ecs.run_calls
    assert call == {
        "cluster": "chordsync-student-demo-analysis",
        "taskDefinition": "chordsync-student-demo-worker",
        "launchType": "FARGATE",
        "count": 1,
        "startedBy": "chordsync-dispatcher",
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": ["subnet-0a1b2c3d4e5f60718", "subnet-1a1b2c3d4e5f60718"],
                "securityGroups": ["sg-0a1b2c3d4e5f60718"],
                "assignPublicIp": "ENABLED",
            }
        },
    }
    assert "overrides" not in call and "tags" not in call


def test_the_invocation_event_cannot_override_anything():
    world = World(visible=1)
    hostile = {
        "reason": "job_dispatched",
        "cluster": "other",
        "taskDefinition": "evil:1",
        "overrides": {"containerOverrides": [{"name": "analysis-worker", "command": ["sh"]}]},
        "networkConfiguration": {"awsvpcConfiguration": {"subnets": ["subnet-ffffffff"]}},
        "securityGroups": ["sg-ffffffff"],
        "image": "evil/image",
        "count": 50,
        "launchType": "EC2",
        "environment": {"X": "1"},
        "role": "arn:aws:iam::1:role/x",
    }

    result = handler.handle(hostile, world.dispatcher())

    assert result["outcome"] == "worker_started"
    (call,) = world.ecs.run_calls
    assert call["cluster"] == CONFIG.cluster and call["taskDefinition"] == CONFIG.task_definition
    assert call["count"] == 1 and call["launchType"] == "FARGATE"
    assert "overrides" not in call
    assert "subnet-ffffffff" not in json.dumps(call)


@pytest.mark.parametrize("event", [None, {}, "text", 5, {"reason": 5}, {"reason": "who-knows"}])
def test_odd_events_are_handled_like_any_other_trigger(event):
    world = World(visible=1)
    assert handler.handle(event, world.dispatcher())["outcome"] == "worker_started"


# --- races -----------------------------------------------------------------------


def test_eight_simultaneous_dispatchers_start_one_task():
    # run_task is slow and the new task is not listed for a while, exactly the
    # window where list-then-start alone would start several workers.
    world = World(visible=1, latency=0.05, listing_lag=0.3)
    dispatchers = [world.dispatcher() for _ in range(8)]
    barrier = threading.Barrier(8)
    outcomes: list[Outcome] = []

    def run(dispatcher):
        barrier.wait()
        outcomes.append(dispatcher.dispatch("job_dispatched").outcome)

    threads = [threading.Thread(target=run, args=(d,)) for d in dispatchers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(world.ecs.run_calls) == 1
    assert outcomes.count(Outcome.WORKER_STARTED) == 1
    assert set(outcomes) <= {
        Outcome.WORKER_STARTED,
        Outcome.LOCK_NOT_ACQUIRED,
        Outcome.WORKER_ALREADY_ACTIVE,
    }


def test_a_started_worker_keeps_the_lease_as_a_cool_down():
    world = World(visible=1, listing_lag=3600)  # ECS never lists the new task
    dispatcher = world.dispatcher()
    assert dispatcher.dispatch("job_dispatched").outcome is Outcome.WORKER_STARTED

    again = dispatcher.dispatch("scheduled_reconcile")

    assert again.outcome is Outcome.LOCK_NOT_ACQUIRED
    assert len(world.ecs.run_calls) == 1


def test_an_expired_lease_is_recoverable():
    world = World(visible=1, listing_lag=3600)
    dispatcher = world.dispatcher()
    dispatcher.dispatch("job_dispatched")
    world.clock.now += 61  # the holder is gone and the lease has run out
    world.ecs.tasks.clear()  # and its worker finished

    assert dispatcher.dispatch("scheduled_reconcile").outcome is Outcome.WORKER_STARTED
    assert len(world.ecs.run_calls) == 2


def test_a_crashed_holders_lease_blocks_only_until_it_expires():
    world = World(visible=1)
    world.table.items[LOCK_KEY] = {
        "PK": LOCK_KEY,
        "owner": "dead-lambda",
        "expires_at": int(world.clock.now) + 30,
    }
    dispatcher = world.dispatcher()
    assert dispatcher.dispatch("scheduled_reconcile").outcome is Outcome.LOCK_NOT_ACQUIRED
    world.clock.now += 31
    assert dispatcher.dispatch("scheduled_reconcile").outcome is Outcome.WORKER_STARTED


def test_the_lease_is_released_when_a_worker_turns_up_under_the_lock():
    world = World(visible=1)
    dispatcher = world.dispatcher()
    original = world.ecs.list_tasks
    calls = {"n": 0}

    def late(**values):
        calls["n"] += 1
        if calls["n"] == 2:  # between the first look and the re-check
            world.ecs.add_task("PENDING")
        return original(**values)

    world.ecs.list_tasks = late

    assert dispatcher.dispatch("job_dispatched").outcome is Outcome.WORKER_ALREADY_ACTIVE
    assert world.ecs.run_calls == []
    assert LOCK_KEY not in world.table.items  # released, not held for 60 s


# --- failures -------------------------------------------------------------------


def test_a_run_task_exception_is_controlled_and_releases_the_lease():
    world = World(visible=1)
    world.ecs.run_error = AwsError("ThrottlingException")

    result = world.dispatcher().dispatch("job_dispatched")

    assert result.outcome is Outcome.RUN_TASK_FAILED
    assert result.detail == "ThrottlingException"
    assert "account/123" not in json.dumps(result.as_dict())
    assert world.sqs.calls == ["get_queue_attributes"]  # the queue was only read
    assert LOCK_KEY not in world.table.items
    world.ecs.run_error = None
    assert world.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.WORKER_STARTED


@pytest.mark.parametrize(
    "reason",
    ["Capacity is unavailable at this time", "RESOURCE:FARGATE", "ACCESS_DENIED"],
)
def test_ecs_failures_in_the_response_are_handled(reason):
    world = World(visible=1)
    world.ecs.run_response = {"tasks": [], "failures": [{"arn": "x", "reason": reason}]}

    result = world.dispatcher().dispatch("scheduled_reconcile")

    assert result.outcome is Outcome.RUN_TASK_FAILED
    assert result.detail == reason
    assert world.sqs.calls == ["get_queue_attributes"]
    assert LOCK_KEY not in world.table.items


def test_an_empty_run_task_response_is_a_failure_not_a_start():
    world = World(visible=1)
    world.ecs.run_response = {"tasks": [], "failures": []}
    assert world.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.RUN_TASK_FAILED


def test_a_queue_attribute_error_is_a_safe_failure():
    world = World(visible=1)
    world.sqs.error = AwsError("AccessDenied")
    result = world.dispatcher().dispatch("scheduled_reconcile")
    assert result.outcome is Outcome.DEPENDENCY_UNAVAILABLE
    assert world.ecs.run_calls == [] and world.table.puts == 0


def test_an_ecs_listing_error_starts_nothing():
    world = World(visible=1)
    world.ecs.list_error = AwsError("ServiceUnavailable")
    result = world.dispatcher().dispatch("scheduled_reconcile")
    assert result.outcome is Outcome.DEPENDENCY_UNAVAILABLE
    assert world.ecs.run_calls == []


def test_a_lock_table_error_starts_nothing():
    world = World(visible=1)
    world.table.error = AwsError("ProvisionedThroughputExceededException")
    result = world.dispatcher().dispatch("scheduled_reconcile")
    assert result.outcome is Outcome.DEPENDENCY_UNAVAILABLE
    assert world.ecs.run_calls == []


def test_a_malformed_queue_response_is_a_safe_failure():
    class Broken:
        def get_queue_attributes(self, **_):
            return {"Attributes": {"ApproximateNumberOfMessages": "many"}}

    with pytest.raises(DependencyError):
        SqsQueueDepth(Broken(), CONFIG.queue_url).depth()


# --- triggers ---------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["job_dispatched", "scheduled_reconcile"])
def test_both_trigger_paths_behave_the_same(reason):
    started = World(visible=2).dispatcher().dispatch(reason)
    idle = World(visible=0).dispatcher().dispatch(reason)
    busy_world = World(visible=2)
    busy_world.ecs.add_task("RUNNING")
    busy = busy_world.dispatcher().dispatch(reason)
    assert (started.outcome, idle.outcome, busy.outcome) == (
        Outcome.WORKER_STARTED,
        Outcome.NO_WORK,
        Outcome.WORKER_ALREADY_ACTIVE,
    )


def test_an_api_trigger_rereads_lagging_counters_but_a_schedule_does_not():
    api = World(visible=0)
    api.sqs.attributes = [(0, 0, 0), (0, 0, 0), (1, 0, 0)]  # the message shows up late
    assert api.dispatcher().dispatch("job_dispatched").outcome is Outcome.WORKER_STARTED
    assert api.sleeps == [3.0, 3.0]

    scheduled = World(visible=0)
    scheduled.sqs.attributes = [(0, 0, 0), (1, 0, 0)]
    assert scheduled.dispatcher().dispatch("scheduled_reconcile").outcome is Outcome.NO_WORK
    assert scheduled.sleeps == []


def test_an_api_trigger_gives_up_after_its_bounded_rereads():
    world = World(visible=0)
    assert world.dispatcher().dispatch("job_dispatched").outcome is Outcome.NO_WORK
    assert world.sleeps == [3.0, 3.0] and len(world.sqs.calls) == 3


# --- adapter request shapes (validated against the real service models) -----------


def _stubbed(service):
    boto3 = pytest.importorskip("boto3")
    from botocore.stub import Stubber

    client = boto3.session.Session(
        aws_access_key_id="x", aws_secret_access_key="x", region_name="ap-southeast-1"
    ).client(service)
    return client, Stubber(client)


def test_the_sqs_request_matches_the_service_model():
    client, stubber = _stubbed("sqs")
    stubber.add_response(
        "get_queue_attributes",
        {"Attributes": {
            "ApproximateNumberOfMessages": "2",
            "ApproximateNumberOfMessagesNotVisible": "1",
            "ApproximateNumberOfMessagesDelayed": "0",
        }},
        {"QueueUrl": CONFIG.queue_url, "AttributeNames": [
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
        ]},
    )
    with stubber:
        assert SqsQueueDepth(client, CONFIG.queue_url).depth() == QueueDepth(2, 1, 0)
        stubber.assert_no_pending_responses()


def test_the_ecs_requests_match_the_service_model():
    client, stubber = _stubbed("ecs")
    task_arn = f"arn:aws:ecs:ap-southeast-1:123456789012:task/{CONFIG.cluster}/abc"
    stubber.add_response(
        "list_tasks",
        {"taskArns": [task_arn]},
        {"cluster": CONFIG.cluster, "family": FAMILY, "desiredStatus": "RUNNING"},
    )
    stubber.add_response(
        "describe_tasks",
        {"tasks": [{"taskArn": task_arn, "lastStatus": "PENDING", "taskDefinitionArn": TASK_DEF_ARN}], "failures": []},
        {"cluster": CONFIG.cluster, "tasks": [task_arn]},
    )
    stubber.add_response(
        "run_task",
        {"tasks": [{"taskArn": task_arn}], "failures": []},
        {
            "cluster": CONFIG.cluster,
            "taskDefinition": FAMILY,
            "launchType": "FARGATE",
            "count": 1,
            "startedBy": "chordsync-dispatcher",
            "networkConfiguration": {"awsvpcConfiguration": {
                "subnets": list(CONFIG.subnet_ids),
                "securityGroups": [CONFIG.security_group_id],
                "assignPublicIp": "ENABLED",
            }},
        },
    )
    tasks = EcsWorkerTasks(client, CONFIG)
    with stubber:
        assert [t.status for t in tasks.active()] == ["PENDING"]
        assert tasks.start() == task_arn
        stubber.assert_no_pending_responses()


# --- configuration ----------------------------------------------------------------


def test_configuration_reads_the_expected_values():
    assert CONFIG.cluster == "chordsync-student-demo-analysis"
    assert CONFIG.task_family == FAMILY
    assert CONFIG.max_worker_tasks == 1 and CONFIG.lease_seconds == 60
    assert DispatcherConfig.from_env(
        {**ENV, "CHORDSYNC_WORKER_TASK_DEFINITION": "arn:aws:ecs:ap-southeast-1:123456789012:task-definition/" + FAMILY}
    ).task_family == FAMILY


@pytest.mark.parametrize(
    "name,value",
    [
        ("AWS_REGION", "mars"),
        ("CHORDSYNC_ECS_CLUSTER", "bad name!"),
        ("CHORDSYNC_WORKER_TASK_DEFINITION", f"{FAMILY}:7"),
        ("CHORDSYNC_WORKER_SUBNET_IDS", "subnet-ok1234567,not-a-subnet"),
        ("CHORDSYNC_WORKER_SUBNET_IDS", ","),
        ("CHORDSYNC_WORKER_SECURITY_GROUP_ID", "sg-"),
        ("CHORDSYNC_SQS_ANALYSIS_QUEUE_URL", "http://localhost:4566/000000000000/q"),
        ("CHORDSYNC_MAX_WORKER_TASKS", "0"),
        ("CHORDSYNC_MAX_WORKER_TASKS", "99"),
        ("CHORDSYNC_DISPATCH_LEASE_SECONDS", "5"),
        ("CHORDSYNC_DISPATCH_LEASE_SECONDS", "abc"),
    ],
)
def test_invalid_configuration_is_refused(name, value):
    with pytest.raises(DispatcherConfigurationError):
        DispatcherConfig.from_env({**ENV, name: value})


@pytest.mark.parametrize("name", sorted(ENV))
def test_every_required_setting_is_required(name):
    environment = dict(ENV)
    del environment[name]
    with pytest.raises(DispatcherConfigurationError):
        DispatcherConfig.from_env(environment)


def test_no_credentials_are_read_from_the_environment():
    source = (ROOT / "backend/dispatcher/config.py").read_text()
    for name in ("ACCESS_KEY", "SECRET", "SESSION_TOKEN"):
        assert name not in source


def test_a_missing_configuration_fails_the_invocation(monkeypatch):
    handler._default_dispatcher.cache_clear()
    monkeypatch.delenv("CHORDSYNC_ECS_CLUSTER", raising=False)
    with pytest.raises(DispatcherConfigurationError):
        handler.lambda_handler({"reason": "scheduled_reconcile"})
    handler._default_dispatcher.cache_clear()


# --- packaging and IAM -------------------------------------------------------------


def test_the_dispatcher_package_is_self_contained():
    allowed = {"boto3", "backend"}
    stdlib = set(__import__("sys").stdlib_module_names)
    for path in (ROOT / "backend/dispatcher").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                assert top in stdlib or top in allowed, f"{path.name}: {module}"
                if top == "backend":
                    assert module.startswith("backend.dispatcher"), f"{path.name}: {module}"


def test_the_dispatcher_code_never_calls_message_or_storage_apis():
    source = "".join(p.read_text() for p in (ROOT / "backend/dispatcher").glob("*.py"))
    for forbidden in (
        "receive_message", "delete_message", "change_message_visibility",
        "send_message", "purge_queue", "get_object", "put_object", "client(\"s3\")",
    ):
        assert forbidden not in source, forbidden


def _dispatcher_policy() -> str:
    return (ROOT / "infrastructure/aws/dispatcher.tf").read_text()


def test_the_dispatcher_iam_policy_is_narrow():
    text = _dispatcher_policy()
    for forbidden in (
        "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility",
        "sqs:SendMessage", "sqs:*", "ecs:*", "s3:", "iam:*", "dynamodb:*",
        "dynamodb:Scan", "dynamodb:GetItem", "dynamodb:UpdateItem",
    ):
        assert forbidden not in text, forbidden
    for required in (
        "sqs:GetQueueAttributes", "ecs:ListTasks", "ecs:DescribeTasks", "ecs:RunTask",
        "iam:PassRole", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:LeadingKeys",
    ):
        assert required in text, required
    assert "iam:PassedToService" in text
    assert "ecs:cluster" in text  # ListTasks/RunTask are limited to the one cluster


def test_terraform_creates_nothing_until_enabled():
    text = _dispatcher_policy()
    assert 'variable "dispatcher_enabled"' in text
    blocks = text.split('\nresource "')[1:]
    assert len(blocks) == 7
    for block in blocks:
        header = block.split("\n}\n")[0]
        assert "count" in header and ("local.dispatcher_on" in header or "local.dispatcher_schedule_on" in header), block[:60]


def test_the_lambda_zip_is_tiny_reproducible_and_imports_on_its_own(tmp_path):
    import subprocess
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_dispatcher_package as packager
    finally:
        sys.path.pop(0)

    first = packager.build(tmp_path / "a.zip")
    second = packager.build(tmp_path / "b.zip")

    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_size < 50_000
    import zipfile

    names = sorted(zipfile.ZipFile(first).namelist())
    assert names == [
        "backend/__init__.py",
        "backend/dispatcher/__init__.py",
        "backend/dispatcher/aws.py",
        "backend/dispatcher/config.py",
        "backend/dispatcher/dispatcher.py",
        "backend/dispatcher/handler.py",
    ]
    # Only the zip is on the path: nothing from the API package, no boto3 needed to import.
    code = (
        f"import sys; sys.path.insert(0, {str(first)!r})\n"
        "import backend.dispatcher.handler as h\n"
        "assert 'backend.api' not in sys.modules and 'boto3' not in sys.modules\n"
        "print(h.lambda_handler.__name__)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lambda_handler"


# --- API seam and reconciler boundary ---------------------------------------------


from backend.api.app.services.analysis_job_dispatcher import (  # noqa: E402
    DispatchReconciler,
    QueueBackedDispatcher,
)
from backend.api.app.services.analysis_job_queue import InMemoryAnalysisJobQueue  # noqa: E402
from backend.api.app.services.artifact_storage import (  # noqa: E402
    ArtifactKey,
    ArtifactRole,
    LocalArtifactStorage,
)
from backend.api.app.services.aws_errors import (  # noqa: E402
    CloudProviderError,
    CloudProviderErrorKind,
)
from backend.api.app.services.cloud_job import CloudJobStatus, new_cloud_job  # noqa: E402
from backend.api.app.services.cloud_job_repository import InMemoryCloudJobRepository  # noqa: E402
from backend.api.app.services.worker_dispatch_trigger import (  # noqa: E402
    LambdaWorkerDispatchTrigger,
    NoopWorkerDispatchTrigger,
)


class RecordingTrigger:
    def __init__(self, fail=False) -> None:
        self.reasons: list[str] = []
        self.fail = fail

    def notify(self, reason="job_dispatched"):
        self.reasons.append(reason)
        if self.fail:
            raise RuntimeError("lambda unreachable")


def _awaiting_job(tmp_path, repository, storage, job_id="00000000-0000-4000-8000-000000000001"):
    key = f"jobs/{job_id}/source/input.wav"
    storage.put_bytes(ArtifactKey(ArtifactRole.SOURCE_UPLOAD, key), b"x", content_type="audio/wav")
    job = new_cloud_job(job_id, "Song")
    job.source_object_key = key
    job.file_type = ".wav"
    job.transition_to(CloudJobStatus.AWAITING_UPLOAD)
    repository.add(job)
    return job_id


def test_dispatch_nudges_the_worker_dispatcher_once_after_the_message_is_queued(tmp_path):
    repository, storage = InMemoryCloudJobRepository(), LocalArtifactStorage(tmp_path / "o")
    queue, trigger = InMemoryAnalysisJobQueue(), RecordingTrigger()
    job_id = _awaiting_job(tmp_path, repository, storage)

    QueueBackedDispatcher(repository, storage, queue, trigger).dispatch(job_id)

    assert trigger.reasons == ["job_dispatched"]
    assert queue.receive() is not None


def test_a_failing_nudge_never_fails_or_undoes_the_dispatch(tmp_path):
    repository, storage = InMemoryCloudJobRepository(), LocalArtifactStorage(tmp_path / "o")
    queue, trigger = InMemoryAnalysisJobQueue(), RecordingTrigger(fail=True)
    job_id = _awaiting_job(tmp_path, repository, storage)

    QueueBackedDispatcher(repository, storage, queue, trigger).dispatch(job_id)  # no raise

    job = repository.get(job_id)
    assert job.status is CloudJobStatus.QUEUED and not job.dispatch_pending
    assert queue.receive() is not None


def test_no_nudge_when_the_message_could_not_be_queued(tmp_path):
    class DownQueue(InMemoryAnalysisJobQueue):
        def enqueue(self, descriptor):
            raise CloudProviderError(CloudProviderErrorKind.TEMPORARY_UNAVAILABLE, "down")

    repository, storage = InMemoryCloudJobRepository(), LocalArtifactStorage(tmp_path / "o")
    trigger = RecordingTrigger()
    job_id = _awaiting_job(tmp_path, repository, storage)

    with pytest.raises(CloudProviderError):
        QueueBackedDispatcher(repository, storage, DownQueue(), trigger).dispatch(job_id)

    assert trigger.reasons == []
    assert repository.get(job_id).dispatch_pending  # durable; the reconciler resends


def test_the_reconciler_resends_messages_and_nudges_only_when_it_sent_something(tmp_path):
    repository, storage = InMemoryCloudJobRepository(), LocalArtifactStorage(tmp_path / "o")
    queue, trigger = InMemoryAnalysisJobQueue(), RecordingTrigger()
    reconciler = DispatchReconciler(repository, queue, trigger)
    assert reconciler.reconcile() == 0 and trigger.reasons == []

    job_id = _awaiting_job(tmp_path, repository, storage)
    job = repository.get(job_id)
    job.transition_to(CloudJobStatus.QUEUED)
    job.dispatch_pending = True
    repository.save(job, expected_status=CloudJobStatus.AWAITING_UPLOAD)

    assert reconciler.reconcile() == 1
    assert trigger.reasons == ["job_dispatched"]


def test_the_default_trigger_does_nothing():
    NoopWorkerDispatchTrigger().notify()


def test_the_lambda_trigger_invokes_asynchronously_with_only_a_reason():
    class Client:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def invoke(self, **values):
            self.calls.append(values)

    client = Client()
    LambdaWorkerDispatchTrigger(client, "dispatcher-fn").notify()

    (call,) = client.calls
    assert call["FunctionName"] == "dispatcher-fn"
    assert call["InvocationType"] == "Event"  # does not wait for ECS
    assert json.loads(call["Payload"]) == {"reason": "job_dispatched"}


def test_the_lambda_trigger_swallows_every_error():
    class Broken:
        def invoke(self, **_values):
            raise AwsError("ResourceNotFoundException")

    LambdaWorkerDispatchTrigger(Broken(), "dispatcher-fn").notify()
    with pytest.raises(ValueError):
        LambdaWorkerDispatchTrigger(Broken(), " ")


# --- local Lambda invocation (the real entry point, fake clients) ------------------


@pytest.fixture
def invoke(monkeypatch):
    def run(world, event):
        dispatcher = handler.build_dispatcher(
            CONFIG,
            sqs_client=world.sqs,
            ecs_client=world.ecs,
            dynamodb_table=world.table,
            sleep=world.sleeps.append,
        )
        monkeypatch.setattr(handler, "_default_dispatcher", lambda: dispatcher)
        return handler.lambda_handler(event, object())

    return run


def test_lambda_invocation_with_no_work_is_a_successful_no_op(invoke):
    world = World(visible=0)
    assert invoke(world, {"reason": "scheduled_reconcile"})["outcome"] == "no_work"
    assert world.ecs.run_calls == []


def test_lambda_invocation_with_work_starts_exactly_one_task(invoke):
    world = World(visible=1)
    result = invoke(world, {"reason": "job_dispatched"})
    assert result["outcome"] == "worker_started" and result["task_arn"] in world.ecs.tasks
    assert len(world.ecs.run_calls) == 1
    again = invoke(world, {"reason": "job_dispatched"})
    assert again["outcome"] == "worker_already_active" and len(world.ecs.run_calls) == 1


def test_lambda_invocation_with_an_active_worker_is_a_no_op(invoke):
    world = World(visible=5)
    world.ecs.add_task("RUNNING")
    assert invoke(world, {"reason": "scheduled_reconcile"})["outcome"] == "worker_already_active"
    assert world.ecs.run_calls == []


def test_log_events_carry_no_secrets_or_message_data(invoke, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="chordsync.dispatcher")
    world = World(visible=1)
    invoke(world, {"reason": "job_dispatched", "receipt_handle": "SECRET-RECEIPT", "body": "SECRET-BODY"})
    text = caplog.text
    assert "worker_started" in text and "task_arn" in text
    for leaked in ("SECRET", "receipt", "ReceiptHandle", "AKIA", "aws_secret"):
        assert leaked not in text


# --- API configuration wiring ----------------------------------------------------


def test_the_dispatcher_function_name_reaches_the_api_dispatcher():
    from backend.api.app.services.cloud_runtime import (
        CloudRuntimeConfig,
        compose_analysis_dispatcher,
        compose_cloud_runtime,
    )

    class Lambda:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def invoke(self, **values):
            self.calls.append(values)

    class Table:
        def put_item(self, **_values):
            return {}

        def get_item(self, **_values):
            return {}

    class Dynamo:
        def Table(self, _name):  # noqa: N802 - boto3 resource API
            return Table()

    environment = {
        "CHORDSYNC_RUNTIME_MODE": "aws",
        "AWS_REGION": "ap-southeast-1",
        "CHORDSYNC_S3_BUCKET": "bucket",
        "CHORDSYNC_DYNAMODB_JOB_TABLE": "jobs",
        "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL": "https://sqs.example/q",
        "CHORDSYNC_WORKER_DISPATCHER_FUNCTION": "chordsync-student-demo-worker-dispatcher",
    }
    config = CloudRuntimeConfig.from_env(environment)
    lambda_client = Lambda()

    runtime = compose_cloud_runtime(
        config,
        s3_client=object(),
        dynamodb_resource=Dynamo(),
        sqs_client=object(),
        lambda_client=lambda_client,
    )
    dispatcher = compose_analysis_dispatcher(config, runtime)

    assert config.worker_dispatcher_function == "chordsync-student-demo-worker-dispatcher"
    assert dispatcher._worker_trigger is runtime.worker_trigger
    runtime.worker_trigger.notify()
    assert lambda_client.calls[0]["FunctionName"] == config.worker_dispatcher_function
    assert lambda_client.calls[0]["InvocationType"] == "Event"


def test_without_a_dispatcher_function_name_there_is_no_trigger():
    from backend.api.app.services.cloud_runtime import CloudRuntimeConfig, compose_cloud_runtime

    config = CloudRuntimeConfig.from_env(
        {
            "CHORDSYNC_RUNTIME_MODE": "aws",
            "AWS_REGION": "ap-southeast-1",
            "CHORDSYNC_S3_BUCKET": "bucket",
            "CHORDSYNC_DYNAMODB_JOB_TABLE": "jobs",
            "CHORDSYNC_SQS_ANALYSIS_QUEUE_URL": "https://sqs.example/q",
        }
    )

    class Dynamo:
        def Table(self, _name):  # noqa: N802
            return object()

    runtime = compose_cloud_runtime(
        config, s3_client=object(), dynamodb_resource=Dynamo(), sqs_client=object()
    )
    assert runtime.worker_trigger is None


# --- structured logging (S7-T09) ----------------------------------------------------


def _lambda_like_logging():
    """What the Lambda Python runtime sets up: one root handler, root level WARNING."""
    import logging

    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    root = logging.getLogger()
    previous = (root.level, list(root.handlers))
    handler = Capture()
    root.handlers = [handler]
    root.setLevel(logging.WARNING)
    return records, lambda: (setattr(root, "level", previous[0]), setattr(root, "handlers", previous[1]))


def test_the_dispatcher_logger_permits_info_even_when_the_root_logger_is_at_warning():
    import logging

    records, restore = _lambda_like_logging()
    try:
        assert logging.getLogger().level == logging.WARNING  # the runtime's default
        assert logging.getLogger("chordsync.dispatcher").getEffectiveLevel() == logging.INFO
        World(visible=0).dispatcher().dispatch("scheduled_reconcile")
    finally:
        restore()
    events = [json.loads(r.getMessage()) for r in records if r.name == "chordsync.dispatcher"]
    assert [e["event"] for e in events] == ["no_work"]
    assert events[0]["reason"] == "scheduled_reconcile"
    assert records[0].levelname == "INFO"


def test_worker_started_is_emitted_at_info_with_the_task_arn():
    records, restore = _lambda_like_logging()
    try:
        result = World(visible=1).dispatcher().dispatch("job_dispatched")
    finally:
        restore()
    events = [json.loads(r.getMessage()) for r in records if r.name == "chordsync.dispatcher"]
    started = [e for e in events if e["event"] == "worker_started"]
    assert len(started) == 1 and started[0]["task_arn"] == result.task_arn
    assert started[0]["visible"] == 1 and all(r.levelname == "INFO" for r in records)


@pytest.mark.parametrize(
    "scenario,expected",
    [("no_work", "no_work"), ("active", "worker_already_active"), ("lock", "lock_not_acquired")],
)
def test_the_other_info_events_are_emitted_too(scenario, expected):
    records, restore = _lambda_like_logging()
    try:
        world = World(visible=0 if scenario == "no_work" else 1)
        if scenario == "active":
            world.ecs.add_task("RUNNING")
        if scenario == "lock":
            world.table.items[LOCK_KEY] = {
                "PK": LOCK_KEY, "owner": "other", "expires_at": int(world.clock.now) + 30,
            }
        world.dispatcher().dispatch("scheduled_reconcile")
    finally:
        restore()
    assert [json.loads(r.getMessage())["event"] for r in records] == [expected]


def test_failures_still_log_at_error_not_info():
    records, restore = _lambda_like_logging()
    try:
        world = World(visible=1)
        world.ecs.run_error = AwsError("ThrottlingException")
        world.dispatcher().dispatch("job_dispatched")
    finally:
        restore()
    assert [r.levelname for r in records] == ["ERROR"]
    assert json.loads(records[0].getMessage())["event"] == "run_task_failed"


def test_logged_events_carry_only_the_allowed_fields_and_no_secrets():
    records, restore = _lambda_like_logging()
    try:
        world = World(visible=1)
        hostile = {"reason": "job_dispatched", "receipt_handle": "SECRET-RECEIPT",
                   "body": "SECRET-BODY", "Authorization": "Bearer SECRET-TOKEN"}
        handler.handle(hostile, world.dispatcher())
        world.sqs.error = AwsError("AccessDenied")
        world.dispatcher().dispatch("scheduled_reconcile")
    finally:
        restore()
    allowed = {"event", "reason", "task_arn", "detail", "visible", "in_flight", "delayed"}
    text = "".join(r.getMessage() for r in records)
    for r in records:
        assert set(json.loads(r.getMessage())) <= allowed
    for leaked in ("SECRET", "receipt", "ReceiptHandle", "Bearer", "private provider text", "AKIA"):
        assert leaked not in text


def test_only_the_dispatcher_logger_changed_not_boto_or_the_root_logger():
    import logging

    import backend.dispatcher.dispatcher  # noqa: F401 - imported for its side effect

    assert logging.getLogger("chordsync.dispatcher").level == logging.INFO
    assert logging.getLogger("boto3").level != logging.DEBUG
    assert logging.getLogger("botocore").level != logging.DEBUG
    assert logging.getLogger("urllib3").level != logging.DEBUG
    source = (ROOT / "backend/dispatcher/dispatcher.py").read_text()
    assert "basicConfig" not in source and "DEBUG" not in source
    assert "getLogger()" not in source  # never touches the root logger

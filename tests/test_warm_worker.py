"""The worker's wait-and-linger loop, and the API's early warm-up request."""

from __future__ import annotations

import pytest

from backend.api.app.analysis_worker_consumer import WarmWorkerSettings, run_worker
from backend.api.app.services.analysis_job_dispatcher import QueueBackedDispatcher
from backend.api.app.services.analysis_worker_consumer import WorkerOutcome

EMPTY = WorkerOutcome.EMPTY
DONE = WorkerOutcome.COMPLETED


class Consumer:
    """Plays back scripted outcomes; each call advances the fake clock."""

    def __init__(self, outcomes, clock, step=20.0):
        self.outcomes = list(outcomes)
        self.clock = clock
        self.step = step
        self.calls = 0

    def process_once(self):
        self.calls += 1
        self.clock.now += self.step  # an empty poll waits about 20 s
        return self.outcomes.pop(0) if self.outcomes else EMPTY


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _run(outcomes, settings, step=20.0):
    clock = Clock()
    pauses = []
    consumer = Consumer(outcomes, clock, step)
    handled = run_worker(consumer, settings, clock=clock, sleep=pauses.append)
    return handled, consumer, clock, pauses


def test_with_both_waits_at_zero_it_is_the_original_one_pass():
    handled, consumer, _, pauses = _run([DONE, DONE], WarmWorkerSettings())

    assert consumer.calls == 1 and pauses == []
    assert handled == 0


def test_with_both_waits_at_zero_an_empty_queue_exits_at_once():
    _, consumer, _, _ = _run([EMPTY], WarmWorkerSettings())

    assert consumer.calls == 1


def test_a_warm_start_waits_for_the_song_then_leaves_when_there_is_no_linger():
    settings = WarmWorkerSettings(initial_wait_seconds=120, linger_seconds=0)

    handled, consumer, clock, _ = _run([EMPTY, EMPTY, DONE, DONE], settings)

    assert handled == 1
    assert consumer.calls == 3  # waited twice, did the song, left


def test_a_warm_start_gives_up_if_the_song_never_arrives():
    settings = WarmWorkerSettings(initial_wait_seconds=60)

    handled, consumer, clock, pauses = _run([], settings)

    assert handled == 0
    assert 60 <= clock.now <= 60 + 20  # about the initial wait, no more
    assert len(pauses) == consumer.calls - 1


def test_after_a_song_it_stays_for_the_next_one():
    settings = WarmWorkerSettings(initial_wait_seconds=30, linger_seconds=100)

    handled, _, _, _ = _run([DONE, EMPTY, EMPTY, DONE], settings)

    assert handled == 2  # both songs, the second with no cold start


def test_the_linger_clock_restarts_after_every_song():
    settings = WarmWorkerSettings(linger_seconds=45)
    # song, 2 empty polls (40 s, still inside 45 s), song, then it runs out
    handled, consumer, _, _ = _run([DONE, EMPTY, EMPTY, DONE], settings)

    assert handled == 2
    assert consumer.calls == 4 + 3  # then 3 empty polls (60 s) before leaving


def test_the_linger_ends_the_worker_when_nothing_arrives():
    settings = WarmWorkerSettings(linger_seconds=40)

    handled, consumer, clock, _ = _run([DONE], settings)

    assert handled == 1
    assert consumer.calls == 3  # the song, then two empty polls reaching 40 s


def test_a_failed_or_stale_delivery_still_counts_as_activity():
    settings = WarmWorkerSettings(linger_seconds=30)

    handled, _, _, _ = _run(
        [WorkerOutcome.FAILED_PERMANENTLY, WorkerOutcome.ACKNOWLEDGED_STALE], settings
    )

    assert handled == 2


def test_a_worker_never_outlives_its_maximum_lifetime():
    settings = WarmWorkerSettings(linger_seconds=3600, max_lifetime_seconds=600)

    handled, _, clock, _ = _run([DONE] * 100, settings, step=100.0)

    assert clock.now < 600 + 200
    assert handled <= 7


@pytest.mark.parametrize(
    "environment, expected",
    [
        ({}, (0, 0, 7200)),
        (
            {
                "CHORDSYNC_WORKER_INITIAL_WAIT_SECONDS": "120",
                "CHORDSYNC_WORKER_LINGER_SECONDS": "600",
                "CHORDSYNC_WORKER_MAX_LIFETIME_SECONDS": "3600",
            },
            (120, 600, 3600),
        ),
        # nonsense and out-of-range values fall back to the safe defaults
        (
            {
                "CHORDSYNC_WORKER_INITIAL_WAIT_SECONDS": "soon",
                "CHORDSYNC_WORKER_LINGER_SECONDS": "-5",
                "CHORDSYNC_WORKER_MAX_LIFETIME_SECONDS": "99999999",
            },
            (0, 0, 7200),
        ),
    ],
)
def test_settings_come_from_the_environment(environment, expected):
    settings = WarmWorkerSettings.from_env(environment)

    assert (
        settings.initial_wait_seconds,
        settings.linger_seconds,
        settings.max_lifetime_seconds,
    ) == expected
    assert settings.enabled is (expected[0] > 0 or expected[1] > 0)


class Trigger:
    def __init__(self, fail=False):
        self.reasons, self.fail = [], fail

    def notify(self, reason="job_dispatched"):
        self.reasons.append(reason)
        if self.fail:
            raise RuntimeError("lambda unreachable")


def _dispatcher(trigger):
    return QueueBackedDispatcher(None, None, None, worker_trigger=trigger)


def test_warm_asks_the_dispatcher_to_start_a_worker_early():
    trigger = Trigger()

    _dispatcher(trigger).warm()

    assert trigger.reasons == ["upload_started"]


def test_warm_never_raises_even_if_the_dispatcher_is_unreachable():
    _dispatcher(Trigger(fail=True)).warm()  # must not raise


def test_warm_without_a_trigger_does_nothing():
    _dispatcher(None).warm()

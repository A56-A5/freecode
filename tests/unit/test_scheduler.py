"""
Phase 4 (Scheduler + cooldown) unit tests.

FakeClock keeps every test under a few milliseconds — no real 20s waits.
"""
from __future__ import annotations

import asyncio
import random

import pytest

from freecode.config.settings import SchedulerSettings
from freecode.llm.queue import RequestPriority, RequestQueue
from freecode.llm.scheduler import FakeClock, Scheduler, TimerMode


def _sched(
    clock: FakeClock | None = None,
    *,
    floor: float = 20.0,
    cap: float = 120.0,
    seed: int = 0,
    initial_backoff: float = 5.0,
) -> tuple[Scheduler, FakeClock]:
    clock = clock or FakeClock()
    settings = SchedulerSettings(
        cooldown_floor_seconds=floor,
        backoff_cap_seconds=cap,
    )
    sched = Scheduler(
        settings,
        clock=clock,
        rng=random.Random(seed),
        initial_backoff_seconds=initial_backoff,
    )
    return sched, clock


class TestRequestQueue:
    def test_empty(self):
        q: RequestQueue[str] = RequestQueue()
        assert len(q) == 0
        assert not q
        assert q.pop() is None
        assert q.peek() is None

    def test_priority_order(self):
        q: RequestQueue[str] = RequestQueue()
        q.push("bg", RequestPriority.BACKGROUND)
        q.push("user", RequestPriority.USER)
        q.push("tool", RequestPriority.TOOL_RESULT)
        q.push("cont", RequestPriority.CONTINUATION)
        assert q.pop() == "user"
        assert q.pop() == "tool"
        assert q.pop() == "cont"
        assert q.pop() == "bg"
        assert q.pop() is None

    def test_fifo_within_same_priority(self):
        q: RequestQueue[str] = RequestQueue()
        q.push("a", RequestPriority.CONTINUATION)
        q.push("b", RequestPriority.CONTINUATION)
        q.push("c", RequestPriority.CONTINUATION)
        assert [q.pop(), q.pop(), q.pop()] == ["a", "b", "c"]

    def test_peek_does_not_remove(self):
        q: RequestQueue[str] = RequestQueue()
        q.push("x", RequestPriority.USER)
        assert q.peek() == "x"
        assert len(q) == 1
        assert q.peek_priority() is RequestPriority.USER

    def test_clear(self):
        q: RequestQueue[str] = RequestQueue()
        q.push("a", RequestPriority.USER)
        q.clear()
        assert len(q) == 0


class TestSchedulerCooldown:
    def test_starts_ready(self):
        sched, _ = _sched()
        assert sched.is_ready
        assert sched.mode is TimerMode.IDLE
        assert sched.remaining_seconds == 0.0

    def test_record_success_uses_live_delay(self):
        sched, clock = _sched(floor=20.0)
        sched.record_success(25.0)
        assert sched.mode is TimerMode.COOLDOWN
        assert sched.total_seconds == 25.0
        assert sched.remaining_seconds == pytest.approx(25.0)
        assert not sched.is_ready

        clock.advance(25.0)
        assert sched.is_ready
        assert sched.mode is TimerMode.IDLE

    def test_record_success_respects_floor(self):
        sched, _ = _sched(floor=20.0)
        sched.record_success(10.0)  # below floor
        assert sched.total_seconds == 20.0

    def test_record_success_none_uses_floor(self):
        sched, _ = _sched(floor=20.0)
        sched.record_success(None)
        assert sched.total_seconds == 20.0
        assert sched.mode is TimerMode.COOLDOWN

    def test_success_clears_failure_streak(self):
        sched, clock = _sched(floor=1.0, initial_backoff=5.0, seed=1)
        sched.record_server_error()
        assert sched.consecutive_failures == 1
        clock.advance(sched.remaining_seconds + 0.01)
        sched.record_success(1.0)
        assert sched.consecutive_failures == 0
        assert sched.mode is TimerMode.COOLDOWN


class TestSchedulerBackoff:
    def test_rate_limit_uses_retry_after(self):
        sched, clock = _sched(cap=120.0, seed=0)
        # seed=0 → jitter factor deterministic; still <= retry_after
        sched.record_rate_limit(30.0)
        assert sched.mode is TimerMode.BACKOFF
        assert sched.consecutive_failures == 1
        assert 0 < sched.total_seconds <= 30.0

        clock.advance(sched.total_seconds)
        assert sched.is_ready

    def test_rate_limit_without_retry_after_uses_exponential(self):
        sched, _ = _sched(cap=120.0, initial_backoff=5.0, seed=42)
        sched.record_rate_limit(None)
        first = sched.total_seconds
        # With jitter in [85%,100%] of 5s
        assert 5.0 * 0.85 <= first <= 5.0

    def test_consecutive_server_errors_increase_backoff(self):
        # Disable jitter variance by checking structure with fixed seed
        # and comparing that second failure arms longer than first base.
        clock = FakeClock()
        settings = SchedulerSettings(cooldown_floor_seconds=20.0, backoff_cap_seconds=120.0)
        # rng that always returns 1.0 → factor = 0.85+0.15=1.0 (no reduction)
        class _One:
            def random(self) -> float:
                return 1.0

        sched = Scheduler(
            settings,
            clock=clock,
            rng=_One(),  # type: ignore[arg-type]
            initial_backoff_seconds=5.0,
        )
        sched.record_server_error()
        first = sched.total_seconds
        clock.advance(first + 0.01)
        sched.record_server_error()
        second = sched.total_seconds
        assert first == pytest.approx(5.0)
        assert second == pytest.approx(10.0)

    def test_backoff_capped(self):
        class _One:
            def random(self) -> float:
                return 1.0

        clock = FakeClock()
        settings = SchedulerSettings(cooldown_floor_seconds=20.0, backoff_cap_seconds=40.0)
        sched = Scheduler(
            settings,
            clock=clock,
            rng=_One(),  # type: ignore[arg-type]
            initial_backoff_seconds=30.0,
        )
        # failure 1 → 30, failure 2 → 60 → cap 40
        sched.record_server_error()
        clock.advance(sched.total_seconds + 0.01)
        sched.record_server_error()
        assert sched.total_seconds == pytest.approx(40.0)

    def test_retry_after_also_capped(self):
        class _One:
            def random(self) -> float:
                return 1.0

        clock = FakeClock()
        settings = SchedulerSettings(cooldown_floor_seconds=20.0, backoff_cap_seconds=50.0)
        sched = Scheduler(settings, clock=clock, rng=_One())  # type: ignore[arg-type]
        sched.record_rate_limit(999.0)
        assert sched.total_seconds == pytest.approx(50.0)


class TestSchedulerWait:
    @pytest.mark.asyncio
    async def test_wait_until_ready_with_fake_clock(self):
        # floor below live delay so cooldown total == 5.0
        sched, clock = _sched(floor=1.0)
        sched.record_success(5.0)
        assert not sched.is_ready
        assert sched.total_seconds == pytest.approx(5.0)

        async def waiter() -> None:
            await sched.wait_until_ready()

        task = asyncio.create_task(waiter())
        await asyncio.sleep(0)  # let waiter park on FakeClock.sleep
        assert not task.done()
        clock.advance(5.0)
        await asyncio.wait_for(task, timeout=1.0)
        assert sched.is_ready

    @pytest.mark.asyncio
    async def test_wait_when_already_ready_returns_immediately(self):
        sched, _ = _sched()
        await asyncio.wait_for(sched.wait_until_ready(), timeout=0.5)
        assert sched.is_ready


class TestSchedulerSnapshot:
    def test_snapshot_matches_state(self):
        sched, clock = _sched(floor=20.0)
        sched.record_success(25.0)
        snap = sched.snapshot()
        assert snap.mode is TimerMode.COOLDOWN
        assert snap.total_seconds == 25.0
        assert snap.remaining_seconds == pytest.approx(25.0)
        assert snap.is_ready is False

        clock.advance(10.0)
        snap2 = sched.snapshot()
        assert snap2.remaining_seconds == pytest.approx(15.0)

    def test_reset(self):
        sched, _ = _sched()
        sched.record_success(20.0)
        sched.reset()
        assert sched.is_ready
        assert sched.mode is TimerMode.IDLE
        assert sched.consecutive_failures == 0


class TestFakeClock:
    def test_cannot_advance_backwards(self):
        clock = FakeClock(10.0)
        with pytest.raises(ValueError):
            clock.advance(-1.0)

    @pytest.mark.asyncio
    async def test_multiple_sleepers(self):
        clock = FakeClock()
        done: list[int] = []

        async def sleeper(n: int, secs: float) -> None:
            await clock.sleep(secs)
            done.append(n)

        t1 = asyncio.create_task(sleeper(1, 3.0))
        t2 = asyncio.create_task(sleeper(2, 1.0))
        await asyncio.sleep(0)
        clock.advance(1.0)
        await asyncio.wait_for(t2, timeout=1.0)
        assert done == [2]
        clock.advance(2.0)
        await asyncio.wait_for(t1, timeout=1.0)
        assert done == [2, 1]

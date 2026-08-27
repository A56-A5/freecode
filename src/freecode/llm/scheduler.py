"""
llm.scheduler - rate-limit cooldown and failure backoff.

Two distinct timing states (FreeCode.md §8.9 / architecture):

1. **cooldown** — after a successful response, driven by live
   `delaySeconds` (floor-clamped by config).
2. **backoff** — after 429 / 5xx, capped exponential backoff with jitter.

The scheduler is transport-agnostic: callers record outcomes; it only
answers "am I allowed to send now?" and "how long until then?".

A pluggable Clock makes unit tests instant (no real 20–25s waits).
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from freecode.config.logging import get_logger
from freecode.config.settings import SchedulerSettings

log = get_logger(__name__)


class TimerMode(str, Enum):
    IDLE = "idle"
    COOLDOWN = "cooldown"
    BACKOFF = "backoff"


class Clock(Protocol):
    def monotonic(self) -> float:
        """Monotonic seconds (same scale as asyncio loop time)."""

    async def sleep(self, seconds: float) -> None:
        """Sleep for `seconds` (may be interrupted by FakeClock.advance)."""


class SystemClock:
    """Production clock backed by the event loop."""

    def monotonic(self) -> float:
        return asyncio.get_event_loop().time()

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            await asyncio.sleep(seconds)


class FakeClock:
    """
    Deterministic clock for tests.

    `sleep` parks until `advance` covers the requested duration (or the
    clock is advanced past it). Callers never wait on wall time.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start
        self._waiters: list[tuple[float, asyncio.Future[None]]] = []

    def monotonic(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            return
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[None] = loop.create_future()
        wake_at = self._now + seconds
        self._waiters.append((wake_at, fut))
        try:
            await fut
        finally:
            self._waiters = [(t, f) for t, f in self._waiters if f is not fut]

    def advance(self, seconds: float) -> None:
        """Move time forward and wake any sleepers whose deadline passed."""
        if seconds < 0:
            raise ValueError("cannot advance time backwards")
        self._now += seconds
        ready = [(t, f) for t, f in self._waiters if t <= self._now and not f.done()]
        for _, fut in ready:
            fut.set_result(None)

    def set_time(self, t: float) -> None:
        if t < self._now:
            raise ValueError("cannot set time backwards")
        delta = t - self._now
        if delta:
            self.advance(delta)


@dataclass(frozen=True, slots=True)
class SchedulerSnapshot:
    """Immutable view for TUI / logging (maps cleanly to CooldownBar)."""

    mode: TimerMode
    total_seconds: float
    remaining_seconds: float
    consecutive_failures: int

    @property
    def is_ready(self) -> bool:
        return self.mode is TimerMode.IDLE or self.remaining_seconds <= 0


class Scheduler:
    """
    Tracks when the next ApiFreeLLM request is allowed.

    Usage:
        sched = Scheduler(settings)
        await sched.wait_until_ready()
        try:
            resp = await client.send(msg)
            sched.record_success(resp.delay_seconds)
        except LLMRateLimitError as e:
            sched.record_rate_limit(e.retry_after_seconds)
        except LLMServerError:
            sched.record_server_error()
    """

    def __init__(
        self,
        settings: SchedulerSettings | None = None,
        *,
        clock: Clock | None = None,
        rng: random.Random | None = None,
        initial_backoff_seconds: float = 5.0,
    ) -> None:
        self._settings = settings or SchedulerSettings()
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._rng = rng if rng is not None else random.Random()
        self._initial_backoff = max(0.1, initial_backoff_seconds)

        self._mode = TimerMode.IDLE
        self._ready_at = 0.0
        self._total = 0.0
        self._consecutive_failures = 0

    # ── queries ──────────────────────────────────────────────────────

    @property
    def mode(self) -> TimerMode:
        self._refresh_if_elapsed()
        return self._mode

    @property
    def is_ready(self) -> bool:
        self._refresh_if_elapsed()
        return self._mode is TimerMode.IDLE

    @property
    def remaining_seconds(self) -> float:
        self._refresh_if_elapsed()
        if self._mode is TimerMode.IDLE:
            return 0.0
        return max(0.0, self._ready_at - self._clock.monotonic())

    @property
    def total_seconds(self) -> float:
        self._refresh_if_elapsed()
        return self._total if self._mode is not TimerMode.IDLE else 0.0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def snapshot(self) -> SchedulerSnapshot:
        self._refresh_if_elapsed()
        remaining = (
            0.0
            if self._mode is TimerMode.IDLE
            else max(0.0, self._ready_at - self._clock.monotonic())
        )
        return SchedulerSnapshot(
            mode=self._mode,
            total_seconds=self._total if self._mode is not TimerMode.IDLE else 0.0,
            remaining_seconds=remaining,
            consecutive_failures=self._consecutive_failures,
        )

    # ── mutations ────────────────────────────────────────────────────

    def record_success(self, delay_seconds: float | None = None) -> None:
        """
        Successful response: enter normal cooldown.

        Uses max(config floor, live delaySeconds). Missing delay falls
        back to the floor alone.
        """
        self._consecutive_failures = 0
        floor = self._settings.cooldown_floor_seconds
        if delay_seconds is None or delay_seconds < 0:
            total = floor
        else:
            total = max(floor, float(delay_seconds))
        self._arm(TimerMode.COOLDOWN, total)
        log.debug("cooldown armed total=%.2fs (floor=%.2fs live=%s)", total, floor, delay_seconds)

    def record_rate_limit(self, retry_after_seconds: float | None = None) -> None:
        """429 path: prefer Retry-After, else exponential backoff + jitter."""
        self._consecutive_failures += 1
        if retry_after_seconds is not None and retry_after_seconds > 0:
            total = min(float(retry_after_seconds), self._settings.backoff_cap_seconds)
            total = self._apply_jitter(total)
        else:
            total = self._next_backoff_seconds()
        self._arm(TimerMode.BACKOFF, total)
        log.debug(
            "backoff (rate-limit) total=%.2fs failures=%d",
            total,
            self._consecutive_failures,
        )

    def record_server_error(self) -> None:
        """5xx path: capped exponential backoff with jitter."""
        self._consecutive_failures += 1
        total = self._next_backoff_seconds()
        self._arm(TimerMode.BACKOFF, total)
        log.debug(
            "backoff (server-error) total=%.2fs failures=%d",
            total,
            self._consecutive_failures,
        )

    def reset(self) -> None:
        """Clear all timers and failure counters (tests / session restart)."""
        self._mode = TimerMode.IDLE
        self._ready_at = 0.0
        self._total = 0.0
        self._consecutive_failures = 0

    # ── waiting ──────────────────────────────────────────────────────

    async def wait_until_ready(self) -> None:
        """Block until the scheduler is idle (ready to send)."""
        while True:
            remaining = self.remaining_seconds
            if self.is_ready or remaining <= 0:
                self._mode = TimerMode.IDLE
                self._total = 0.0
                return
            await self._clock.sleep(remaining)

    # ── internals ────────────────────────────────────────────────────

    def _arm(self, mode: TimerMode, total: float) -> None:
        total = max(0.0, float(total))
        now = self._clock.monotonic()
        self._mode = mode if total > 0 else TimerMode.IDLE
        self._total = total
        self._ready_at = now + total

    def _refresh_if_elapsed(self) -> None:
        if self._mode is TimerMode.IDLE:
            return
        if self._clock.monotonic() >= self._ready_at:
            self._mode = TimerMode.IDLE
            self._total = 0.0

    def _next_backoff_seconds(self) -> float:
        # 5, 10, 20, ... capped, then jitter.
        exp = self._initial_backoff * (2 ** max(0, self._consecutive_failures - 1))
        capped = min(exp, self._settings.backoff_cap_seconds)
        return self._apply_jitter(capped)

    def _apply_jitter(self, seconds: float) -> float:
        """Uniform jitter in [85%, 100%] of the delay — never above cap."""
        if seconds <= 0:
            return 0.0
        factor = 0.85 + 0.15 * self._rng.random()
        jittered = seconds * factor
        return min(jittered, self._settings.backoff_cap_seconds)

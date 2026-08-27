"""
llm.queue - priority queue for pending LLM requests.

Priority order (lower value = higher priority), matching FreeCode.md:
  user interruption > tool result > continuation > background

The Event Coalescer (ph-09) will feed this queue; the Scheduler drains
it when a slot opens. This module is pure data structure — no I/O.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class RequestPriority(IntEnum):
    """Lower numeric value = higher priority."""

    USER = 0
    TOOL_RESULT = 1
    CONTINUATION = 2
    BACKGROUND = 3


@dataclass(order=True, slots=True)
class _QueueItem(Generic[T]):
    priority: int
    seq: int
    payload: T = field(compare=False)


class RequestQueue(Generic[T]):
    """
    Min-heap priority queue with FIFO tie-breaking within a priority.

    Not thread-safe; intended for single-threaded async use.
    """

    def __init__(self) -> None:
        self._heap: list[_QueueItem[T]] = []
        self._seq = itertools.count()

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def push(self, item: T, priority: RequestPriority = RequestPriority.CONTINUATION) -> None:
        heapq.heappush(
            self._heap,
            _QueueItem(priority=int(priority), seq=next(self._seq), payload=item),
        )

    def pop(self) -> T | None:
        if not self._heap:
            return None
        return heapq.heappop(self._heap).payload

    def peek(self) -> T | None:
        if not self._heap:
            return None
        return self._heap[0].payload

    def peek_priority(self) -> RequestPriority | None:
        if not self._heap:
            return None
        return RequestPriority(self._heap[0].priority)

    def clear(self) -> None:
        self._heap.clear()

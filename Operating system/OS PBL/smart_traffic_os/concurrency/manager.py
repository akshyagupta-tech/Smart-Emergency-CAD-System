"""Traffic-corridor locks and deadlock-avoidance controls."""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, TypeAlias

from concurrency.bankers import BankersAlgorithm, ProcessId, ResourceMatrix

Zone: TypeAlias = int


class LockOrderViolation(RuntimeError):
    """Raised when a thread attempts to acquire a lower zone out of order."""


class MonotonicIntersectionLock:
    """Manage Zone 1, Zone 2, and Zone 3 with monotonic lock ordering."""

    ZONE_COUNT = 3

    def __init__(self) -> None:
        self._locks = {
            zone: threading.Lock() for zone in range(1, self.ZONE_COUNT + 1)
        }
        self._held_zones = threading.local()

    def acquire(
        self, zone: Zone, blocking: bool = True, timeout: float = -1
    ) -> bool:
        """Acquire one zone, requiring strictly ascending order per thread."""
        self._validate_zone(zone)
        held = self._held()
        if held and zone <= held[-1]:
            raise LockOrderViolation(
                f"zone {zone} must be acquired after zone {held[-1]}"
            )
        acquired = self._locks[zone].acquire(blocking, timeout)
        if acquired:
            held.append(zone)
        return acquired

    def release(self, zone: Zone) -> None:
        """Release a zone, requiring reverse order and current-thread ownership."""
        self._validate_zone(zone)
        held = self._held()
        if not held or held[-1] != zone:
            raise LockOrderViolation("zones must be released in reverse order")
        self._locks[zone].release()
        held.pop()

    @contextmanager
    def hold(self, *zones: Zone) -> Iterator[None]:
        """Acquire several zones in ascending order and release them safely."""
        if list(zones) != sorted(set(zones)):
            raise LockOrderViolation("zones must be unique and strictly ascending")
        acquired: list[Zone] = []
        try:
            for zone in zones:
                self.acquire(zone)
                acquired.append(zone)
            yield
        finally:
            for zone in reversed(acquired):
                self.release(zone)

    def _held(self) -> list[Zone]:
        if not hasattr(self._held_zones, "zones"):
            self._held_zones.zones = []
        return self._held_zones.zones

    @classmethod
    def _validate_zone(cls, zone: Zone) -> None:
        if zone not in range(1, cls.ZONE_COUNT + 1):
            raise ValueError(f"zone must be between 1 and {cls.ZONE_COUNT}")


class PriorityCeilingMutex:
    """Mutex implementing a single-resource Priority Ceiling Protocol.

    Lower numbers represent higher scheduling priority. While the owner holds
    the mutex, its effective priority is raised to ``ceiling`` or kept higher
    if it already has a numerically smaller priority. The original priority is
    restored when the owner releases the resource.
    """

    def __init__(self, ceiling: int = 1) -> None:
        if ceiling < 0:
            raise ValueError("ceiling must be non-negative")
        self.ceiling = ceiling
        self._lock = threading.Lock()
        self._owner: object | None = None
        self._original_priority: int | None = None

    @property
    def owner(self) -> object | None:
        """Return the current owner, if any."""
        return self._owner

    def acquire(
        self,
        task: object,
        priority: int | None = None,
        blocking: bool = True,
        timeout: float = -1,
    ) -> bool:
        """Acquire the mutex and raise the task's effective priority."""
        original_priority = self._priority(task, priority)
        acquired = self._lock.acquire(blocking, timeout)
        if not acquired:
            return False
        self._owner = task
        self._original_priority = original_priority
        if hasattr(task, "priority"):
            setattr(task, "priority", min(original_priority, self.ceiling))
        return True

    def release(self, task: object) -> None:
        """Restore the owner's priority and release the mutex."""
        if self._owner is not task:
            raise RuntimeError("only the mutex owner may release it")
        if hasattr(task, "priority") and self._original_priority is not None:
            setattr(task, "priority", self._original_priority)
        self._owner = None
        self._original_priority = None
        self._lock.release()

    @contextmanager
    def hold(self, task: object, priority: int | None = None) -> Iterator[None]:
        """Acquire the mutex for a task and restore priority on exit."""
        self.acquire(task, priority=priority)
        try:
            yield
        finally:
            self.release(task)

    @staticmethod
    def _priority(task: object, priority: int | None) -> int:
        value = priority if priority is not None else getattr(task, "priority", None)
        if not isinstance(value, int) or value < 0:
            raise ValueError("task priority must be a non-negative integer")
        return value


class TrafficBankersAlgorithm(BankersAlgorithm):
    """Banker's algorithm adapter for traffic-corridor resource requests."""

    def __init__(
        self,
        processes: Sequence[ProcessId],
        available: Sequence[int],
        max_demand: Mapping[ProcessId, Sequence[int]],
        allocation: Mapping[ProcessId, Sequence[int]],
    ) -> None:
        super().__init__(processes, available, max_demand, allocation)
        self.max_demand = self.max_matrix
        self.allocation = self.allocation_matrix

    def is_safe_state(self) -> list[ProcessId] | None:
        """Return a safe completion sequence, or ``None`` if unsafe."""
        return self.safe_sequence()

    def request_resources(
        self, pid: ProcessId, request: Sequence[int]
    ) -> bool:
        """Grant a corridor resource request only if the resulting state is safe."""
        return self.request_corridor(pid, request)


__all__ = [
    "LockOrderViolation",
    "MonotonicIntersectionLock",
    "PriorityCeilingMutex",
    "TrafficBankersAlgorithm",
]
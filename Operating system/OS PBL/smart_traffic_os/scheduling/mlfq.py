"""Three-tier multilevel feedback queue scheduling."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable

from core.pcb import ExtendedPCB, ProcessState


@dataclass(frozen=True, slots=True)
class ScheduleEvent:
    """One execution, idle, or context-switch interval in the schedule."""

    start: float
    end: float
    pid: int | None
    queue: int | None
    kind: str


class MLFQScheduler:
    """Schedule processes using three feedback queues.

    Queue 0 and queue 1 are round-robin queues with 2 ms and 4 ms quanta.
    Queue 2 is FCFS. Processes begin in queue 0, are demoted after exhausting
    a quantum, and are promoted to queue 0 after waiting more than 15 ms.
    """

    QUEUE_QUANTA: tuple[float | None, ...] = (2.0, 4.0, None)
    AGING_THRESHOLD_MS = 15.0
    CONTEXT_SWITCH_PENALTY_MS = 0.2

    def __init__(self) -> None:
        self.time = 0.0
        self.context_switch_time = 0.0
        self._queues: list[deque[ExtendedPCB]] = [deque(), deque(), deque()]
        self._queue_levels: dict[int, int] = {}
        self._ready_since: dict[int, float] = {}
        self._pending: list[ExtendedPCB] = []
        self._previous_pid: int | None = None

    def run(self, processes: Iterable[ExtendedPCB]) -> list[ScheduleEvent]:
        """Run the scheduler and return its complete timing trace.

        The input processes are sorted by arrival time. Their state and
        remaining budgets are updated in place. A ``context_switch`` event has
        ``pid=None`` and accounts for the required 0.2 ms penalty.
        """
        self._reset()
        self._pending = sorted(processes, key=lambda process: (process.arrival, process.pid))
        self._validate_processes()
        events: list[ScheduleEvent] = []

        while self._pending or any(self._queues):
            self._add_arrivals()
            self._promote_aged()

            if not any(self._queues):
                next_arrival = self._pending[0].arrival
                events.append(ScheduleEvent(self.time, float(next_arrival), None, None, "idle"))
                self.time = float(next_arrival)
                self._add_arrivals()

            self._promote_aged()
            process, queue_level = self._next_process()
            if self._previous_pid is not None and self._previous_pid != process.pid:
                start = self.time
                self.time += self.CONTEXT_SWITCH_PENALTY_MS
                self.context_switch_time += self.CONTEXT_SWITCH_PENALTY_MS
                events.append(
                    ScheduleEvent(start, self.time, None, None, "context_switch")
                )
                self._add_arrivals()
                self._promote_aged()

            process.state = ProcessState.RUNNING
            start = self.time
            duration = self._execution_duration(process, queue_level)
            self.time += duration
            process.remaining -= duration
            events.append(
                ScheduleEvent(start, self.time, process.pid, queue_level, "execution")
            )
            self._add_arrivals()

            if process.remaining == 0:
                process.state = ProcessState.TERMINATED
                self._queue_levels.pop(process.pid, None)
                self._ready_since.pop(process.pid, None)
            else:
                process.state = ProcessState.READY
                self._ready_since[process.pid] = self.time
                next_level = queue_level
                quantum = self.QUEUE_QUANTA[queue_level]
                if quantum is not None and duration >= quantum:
                    next_level = min(queue_level + 1, len(self._queues) - 1)
                self._queue_levels[process.pid] = next_level
                self._queues[next_level].append(process)
            self._previous_pid = process.pid

        return events

    def schedule(self, processes: Iterable[ExtendedPCB]) -> list[ScheduleEvent]:
        """Alias for :meth:`run` for callers using scheduling terminology."""
        return self.run(processes)

    def _reset(self) -> None:
        self.time = 0.0
        self.context_switch_time = 0.0
        self._queues = [deque(), deque(), deque()]
        self._queue_levels.clear()
        self._ready_since.clear()
        self._pending = []
        self._previous_pid = None

    def _validate_processes(self) -> None:
        process_ids = [process.pid for process in self._pending]
        if len(process_ids) != len(set(process_ids)):
            raise ValueError("process IDs must be unique")
        if any(process.remaining is None for process in self._pending):
            raise ValueError("process remaining budgets must be initialized")

    def _add_arrivals(self) -> None:
        while self._pending and self._pending[0].arrival <= self.time:
            process = self._pending.pop(0)
            process.state = ProcessState.READY
            self._queue_levels[process.pid] = 0
            self._ready_since[process.pid] = self.time
            self._queues[0].append(process)

    def _promote_aged(self) -> None:
        for level in (1, 2):
            retained: deque[ExtendedPCB] = deque()
            while self._queues[level]:
                process = self._queues[level].popleft()
                waited = self.time - self._ready_since[process.pid]
                if waited > self.AGING_THRESHOLD_MS:
                    self._queue_levels[process.pid] = 0
                    self._queues[0].append(process)
                else:
                    retained.append(process)
            self._queues[level] = retained

    def _next_process(self) -> tuple[ExtendedPCB, int]:
        for level, queue in enumerate(self._queues):
            if queue:
                process = queue.popleft()
                return process, level
        raise RuntimeError("no runnable process is available")

    def _execution_duration(self, process: ExtendedPCB, queue_level: int) -> float:
        remaining = float(process.remaining)
        quantum = self.QUEUE_QUANTA[queue_level]
        duration = remaining if quantum is None else min(remaining, quantum)

        if queue_level > 0 and self._pending:
            until_arrival = float(self._pending[0].arrival) - self.time
            if 0 < until_arrival < duration:
                duration = until_arrival
        return duration
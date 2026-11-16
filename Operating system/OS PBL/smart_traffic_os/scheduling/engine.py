"""CPU scheduling simulations for the Smart Traffic OS prototype."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import TypeAlias, TypedDict

from core.pcb_manager import ExtendedPCB, ProcessState

C_SW = 0.2
ExecutionSlice: TypeAlias = tuple[str, float, float]


class ProcessMetrics(TypedDict):
    """Completion metrics for one process."""

    AWT: float
    ATAT: float
    ART: float
    completion_time: float
    waiting_time: float
    turnaround_time: float
    response_time: float


class ScheduleResult(TypedDict):
    """Result returned by every scheduling simulation."""

    metrics: dict[str, float]
    process_metrics: dict[str, ProcessMetrics]
    trace: list[ExecutionSlice]
    context_switches: int
    context_switch_time: float
    total_time: float


def simulate_preemptive_priority(
    workload: Iterable[ExtendedPCB],
    context_switch_overhead: float = C_SW,
) -> ScheduleResult:
    """Run lower numeric priority values first with arrival preemption."""
    _validate_context_switch_overhead(context_switch_overhead)
    processes = _prepare(workload)
    pending = deque(processes)
    ready: list[ExtendedPCB] = []
    trace: list[ExecutionSlice] = []
    now = 0.0
    previous_pid: str | None = None
    first_start: dict[str, float] = {}
    context_switches = 0

    while pending or ready:
        _arrive(pending, ready, now)
        if not ready:
            now = max(now, pending[0].arrival_time)
            _arrive(pending, ready, now)

        process = _select_priority(ready)
        now, previous_pid, switch_count = _dispatch(
            process, previous_pid, now, pending, ready, overhead=context_switch_overhead
        )
        context_switches += switch_count
        process.transition_state(ProcessState.RUNNING)
        first_start.setdefault(process.pid, now)
        next_arrival = pending[0].arrival_time if pending else float("inf")
        duration = min(process.remaining_time or 0.0, next_arrival - now)
        if duration <= 0.0:
            duration = process.remaining_time or 0.0
        end = now + duration
        trace.append((process.pid, now, end))
        process.remaining_time = max(0.0, (process.remaining_time or 0.0) - duration)
        now = end
        if process.remaining_time == 0.0:
            _complete(process, now)
        else:
            process.transition_state(ProcessState.READY)
            ready.append(process)

    return _result(
        processes, trace, first_start, context_switches, now, context_switch_overhead
    )


def simulate_round_robin(
    workload: Iterable[ExtendedPCB],
    quantum: float = 2.0,
    context_switch_overhead: float = C_SW,
) -> ScheduleResult:
    """Run a fair round-robin scheduler with the supplied time quantum."""
    if quantum <= 0.0:
        raise ValueError("quantum must be positive")
    _validate_context_switch_overhead(context_switch_overhead)
    processes = _prepare(workload)
    pending = deque(processes)
    ready: deque[ExtendedPCB] = deque()
    trace: list[ExecutionSlice] = []
    now = 0.0
    previous_pid: str | None = None
    first_start: dict[str, float] = {}
    context_switches = 0

    while pending or ready:
        _arrive(pending, ready, now)
        if not ready:
            now = max(now, pending[0].arrival_time)
            _arrive(pending, ready, now)
        process = ready.popleft()
        now, previous_pid, switch_count = _dispatch(
            process, previous_pid, now, pending, ready, overhead=context_switch_overhead
        )
        context_switches += switch_count
        process.transition_state(ProcessState.RUNNING)
        first_start.setdefault(process.pid, now)
        duration = min(process.remaining_time or 0.0, quantum)
        end = now + duration
        trace.append((process.pid, now, end))
        process.remaining_time = max(0.0, (process.remaining_time or 0.0) - duration)
        now = end
        _arrive(pending, ready, now)
        if process.remaining_time == 0.0:
            _complete(process, now)
        else:
            process.transition_state(ProcessState.READY)
            ready.append(process)

    return _result(
        processes, trace, first_start, context_switches, now, context_switch_overhead
    )


def simulate_mlfq(
    workload: Iterable[ExtendedPCB],
    context_switch_overhead: float = C_SW,
) -> ScheduleResult:
    """Run a 3-tier MLFQ with quantum 2 ms, 4 ms, and FCFS tiers."""
    _validate_context_switch_overhead(context_switch_overhead)
    processes = _prepare(workload)
    pending = deque(processes)
    queues: list[deque[ExtendedPCB]] = [deque(), deque(), deque()]
    ready_since: dict[str, float] = {}
    trace: list[ExecutionSlice] = []
    now = 0.0
    previous_pid: str | None = None
    first_start: dict[str, float] = {}
    context_switches = 0

    while pending or any(queues):
        while pending and pending[0].arrival_time <= now:
            process = pending.popleft()
            process.transition_state(ProcessState.READY)
            queues[0].append(process)
            ready_since[process.pid] = now
        _age(queues, ready_since, now)
        if not any(queues):
            now = pending[0].arrival_time
            continue

        level, process = _pop_highest(queues)
        now, previous_pid, switch_count = _dispatch(
            process,
            previous_pid,
            now,
            pending,
            queues[0],
            ready_since,
            overhead=context_switch_overhead,
        )
        context_switches += switch_count
        process.transition_state(ProcessState.RUNNING)
        first_start.setdefault(process.pid, now)
        quantum = (2.0, 4.0, None)[level]
        duration = process.remaining_time or 0.0
        if quantum is not None:
            duration = min(duration, quantum)
        elif pending:
            duration = min(duration, max(0.0, pending[0].arrival_time - now))
        if duration <= 0.0:
            duration = process.remaining_time or 0.0
        end = now + duration
        trace.append((process.pid, now, end))
        process.remaining_time = max(0.0, (process.remaining_time or 0.0) - duration)
        now = end

        while pending and pending[0].arrival_time <= now:
            arriving = pending.popleft()
            arriving.transition_state(ProcessState.READY)
            queues[0].append(arriving)
            ready_since[arriving.pid] = arriving.arrival_time
        if process.remaining_time == 0.0:
            _complete(process, now)
            ready_since.pop(process.pid, None)
        else:
            process.transition_state(ProcessState.READY)
            next_level = level
            if quantum is not None and duration >= quantum:
                next_level = min(level + 1, 2)
            queues[next_level].append(process)
            ready_since[process.pid] = now

    return _result(
        processes, trace, first_start, context_switches, now, context_switch_overhead
    )


def _prepare(workload: Iterable[ExtendedPCB]) -> list[ExtendedPCB]:
    processes = sorted(workload, key=lambda process: (process.arrival_time, process.pid))
    if not processes:
        raise ValueError("workload must contain at least one process")
    pids = [process.pid for process in processes]
    if len(set(pids)) != len(pids):
        raise ValueError("workload PIDs must be unique")
    for process in processes:
        process.remaining_time = process.burst_time
        process.completion_time = 0.0
        process.waiting_time = 0.0
        process.turnaround_time = 0.0
        process.total_switches = 0
        process.state = ProcessState.NEW
    return processes


def _arrive(
    pending: deque[ExtendedPCB], ready: deque[ExtendedPCB] | list[ExtendedPCB], now: float
) -> None:
    while pending and pending[0].arrival_time <= now:
        process = pending.popleft()
        process.transition_state(ProcessState.READY)
        ready.append(process)


def _select_priority(ready: list[ExtendedPCB]) -> ExtendedPCB:
    process = min(ready, key=lambda item: (item.priority, item.arrival_time, item.pid))
    ready.remove(process)
    return process


def _dispatch(
    process: ExtendedPCB,
    previous_pid: str | None,
    now: float,
    pending: deque[ExtendedPCB],
    ready: deque[ExtendedPCB],
    ready_since: dict[str, float] | None = None,
    overhead: float = C_SW,
) -> tuple[float, str, int]:
    if previous_pid is None or previous_pid == process.pid:
        return now, process.pid, 0
    now += overhead
    process.total_switches += 1
    while pending and pending[0].arrival_time <= now:
        arriving = pending.popleft()
        arriving.transition_state(ProcessState.READY)
        ready.append(arriving)
        if ready_since is not None:
            ready_since[arriving.pid] = arriving.arrival_time
    return now, process.pid, 1


def _validate_context_switch_overhead(overhead: float) -> None:
    if overhead < 0.0:
        raise ValueError("context_switch_overhead must be non-negative")


def _pop_highest(
    queues: list[deque[ExtendedPCB]],
) -> tuple[int, ExtendedPCB]:
    for level, queue in enumerate(queues):
        if queue:
            return level, queue.popleft()
    raise RuntimeError("no runnable process is available")


def _age(
    queues: list[deque[ExtendedPCB]], ready_since: dict[str, float], now: float
) -> None:
    for level in (1, 2):
        retained: deque[ExtendedPCB] = deque()
        while queues[level]:
            process = queues[level].popleft()
            if now - ready_since[process.pid] > 15.0:
                queues[0].append(process)
            else:
                retained.append(process)
        queues[level] = retained


def _complete(process: ExtendedPCB, now: float) -> None:
    process.completion_time = now
    process.turnaround_time = now - process.arrival_time
    process.waiting_time = process.turnaround_time - process.burst_time
    process.transition_state(ProcessState.TERMINATED)


def _result(
    processes: list[ExtendedPCB],
    trace: list[ExecutionSlice],
    first_start: dict[str, float],
    context_switches: int,
    total_time: float,
    context_switch_overhead: float,
) -> ScheduleResult:
    process_metrics: dict[str, ProcessMetrics] = {}
    for process in processes:
        response = first_start[process.pid] - process.arrival_time
        process_metrics[process.pid] = {
            "AWT": process.waiting_time,
            "ATAT": process.turnaround_time,
            "ART": response,
            "completion_time": process.completion_time,
            "waiting_time": process.waiting_time,
            "turnaround_time": process.turnaround_time,
            "response_time": response,
        }
    count = float(len(processes))
    return {
        "metrics": {
            "AWT": sum(item["AWT"] for item in process_metrics.values()) / count,
            "ATAT": sum(item["ATAT"] for item in process_metrics.values()) / count,
            "ART": sum(item["ART"] for item in process_metrics.values()) / count,
            "Throughput": count / total_time if total_time else 0.0,
        },
        "process_metrics": process_metrics,
        "trace": trace,
        "context_switches": context_switches,
        "context_switch_time": context_switches * context_switch_overhead,
        "total_time": total_time,
    }


__all__ = [
    "C_SW",
    "ExecutionSlice",
    "ScheduleResult",
    "simulate_mlfq",
    "simulate_preemptive_priority",
    "simulate_round_robin",
]
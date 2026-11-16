"""Asynchronous, thread-safe operating-system simulation service.

This service integrates the repository's existing OS teaching modules into a
20 Hz metropolitan-junction simulation. CPU timing, watchdogs, and actuator
events are simulated; this is not a hard real-time controller.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import random
import threading
import time
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any

from concurrency.bankers import BankersAlgorithm
from concurrency.manager import (
    MonotonicIntersectionLock,
    PriorityCeilingMutex,
)
from core.pcb_manager import ProcessState
from memory.page_replacement import compare_page_replacement
from memory.virtual_memory import ZeroCopySharedMemory
from scheduling.engine import C_SW

DIRECTIONS = ("North", "South", "East", "West")
TICK_SECONDS = 0.05
FRAME_CAPACITY = 8
PAGE_REFERENCE_LIMIT = 256
SHARED_FRAME_BYTES = 16 * 1024
logger = logging.getLogger("smart_traffic.kernel")


@dataclass(slots=True)
class ExtendedPCB:
    """Traffic task metadata and simulated register context."""

    pid: str
    tgid: int
    state: ProcessState = ProcessState.NEW
    priority: int = 2
    remaining_burst: float = 0.0
    registers: dict[str, int] = field(
        default_factory=lambda: {"RIP": 0, "RSP": 0, "CR3": 0}
    )
    arrival_time: float = 0.0
    burst_time: float | None = None
    total_switches: int = 0
    last_context_switch_ns: int = 0

    def __post_init__(self) -> None:
        if not self.pid:
            raise ValueError("pid must be a non-empty string")
        if self.tgid < 0:
            raise ValueError("tgid must be non-negative")
        if self.priority not in range(5):
            raise ValueError("priority must be between 0 and 4")
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if isinstance(self.remaining_burst, bool) or self.remaining_burst < 0:
            raise ValueError("remaining_burst must be non-negative")
        if self.burst_time is None:
            self.burst_time = float(self.remaining_burst)
        elif self.remaining_burst == 0:
            self.remaining_burst = float(self.burst_time)
        elif self.remaining_burst > self.burst_time:
            raise ValueError("remaining_burst cannot exceed burst_time")
        if self.burst_time < 0:
            raise ValueError("burst_time must be non-negative")
        self._validate_registers(self.registers)

    @property
    def remaining_time(self) -> float:
        """Compatibility alias for scheduler consumers using remaining_time."""
        return self.remaining_burst

    @remaining_time.setter
    def remaining_time(self, value: float) -> None:
        if value < 0:
            raise ValueError("remaining_time must be non-negative")
        self.remaining_burst = value

    @property
    def remaining(self) -> float:
        """Compatibility alias for remaining burst duration."""
        return self.remaining_burst

    @remaining.setter
    def remaining(self, value: float) -> None:
        self.remaining_time = value

    @property
    def burst(self) -> float:
        """Compatibility alias for the original burst duration."""
        return float(self.burst_time or 0.0)

    @burst.setter
    def burst(self, value: float) -> None:
        if value < 0:
            raise ValueError("burst must be non-negative")
        self.burst_time = value
        self.remaining_burst = value

    def transition_state(self, new_state: ProcessState) -> None:
        """Apply a valid PCB lifecycle transition."""
        allowed = {
            ProcessState.NEW: {ProcessState.READY, ProcessState.TERMINATED},
            ProcessState.READY: {
                ProcessState.RUNNING,
                ProcessState.WAITING,
                ProcessState.TERMINATED,
            },
            ProcessState.RUNNING: {
                ProcessState.READY,
                ProcessState.WAITING,
                ProcessState.TERMINATED,
            },
            ProcessState.WAITING: {ProcessState.READY, ProcessState.TERMINATED},
            ProcessState.TERMINATED: set(),
        }
        if new_state is not self.state and new_state not in allowed[self.state]:
            raise ValueError(
                f"invalid process transition: {self.state.name} -> {new_state.name}"
            )
        self.state = new_state

    def hardware_context_switch(
        self, next_process: ExtendedPCB | None = None
    ) -> int:
        """Measure switch latency, apply C_sw, and log register-address changes.

        This models the 0.2 ms scheduler cost; Python cannot perform a kernel
        register switch, so the measured value is process-level wall latency.
        """
        target_registers = (
            next_process.registers if next_process is not None else self.registers
        )
        started_ns = time.perf_counter_ns()
        time.sleep(C_SW / 1000)
        elapsed_ns = time.perf_counter_ns() - started_ns
        self.last_context_switch_ns = elapsed_ns
        self.total_switches += 1
        transitions = " ".join(
            f"{name}=0x{self.registers[name]:x}->0x{target_registers[name]:x}"
            for name in ("RIP", "RSP", "CR3")
        )
        logger.info(
            "context switch %s -> %s latency_ns=%d %s",
            self.pid,
            next_process.pid if next_process is not None else self.pid,
            elapsed_ns,
            transitions,
        )
        return elapsed_ns

    @staticmethod
    def _validate_registers(registers: Mapping[str, int]) -> None:
        if set(registers) != {"RIP", "RSP", "CR3"}:
            raise ValueError("registers must contain exactly RIP, RSP, and CR3")
        if any(not isinstance(value, int) or value < 0 for value in registers.values()):
            raise ValueError("register values must be non-negative integers")


class MLFQScheduler:
    """Three-tier, priority-aware MLFQ with 15 ms queue-2 aging."""

    QUEUE_QUANTA: tuple[float | None, ...] = (2.0, 4.0, None)
    AGING_THRESHOLD_MS = 15.0

    def __init__(self) -> None:
        self.time_ms = 0.0
        self.context_switch_time_ms = 0.0
        self.context_switch_time_ns = 0
        self._queues: list[deque[ExtendedPCB]] = [deque(), deque(), deque()]
        self._queue_levels: dict[str, int] = {}
        self._ready_since: dict[str, float] = {}
        self._boosted: set[str] = set()

    def run(self, processes: Sequence[ExtendedPCB]) -> dict[str, Any]:
        """Schedule a workload and return timing, queue, and switch metrics."""
        self._reset()
        pending = sorted(processes, key=lambda process: (process.arrival_time, process.pid))
        pids = [process.pid for process in pending]
        if len(pids) != len(set(pids)):
            raise ValueError("process IDs must be unique")
        for process in pending:
            process.remaining_burst = float(process.burst_time or 0.0)
            process.state = ProcessState.NEW

        previous: ExtendedPCB | None = None
        trace: list[tuple[str, float, float]] = []
        queue_trace: list[dict[str, Any]] = []
        ready_depths = [0, 0, 0]
        first_start: dict[str, float] = {}
        completion: dict[str, float] = {}
        context_switches = 0

        while pending or any(self._queues):
            self._admit(pending)
            self._promote_aged()
            if not any(self._queues):
                self.time_ms = float(pending[0].arrival_time)
                self._admit(pending)
                self._promote_aged()

            for index, queue in enumerate(self._queues):
                ready_depths[index] = max(ready_depths[index], len(queue))
            level = next(index for index, queue in enumerate(self._queues) if queue)
            process = self._queues[level].popleft()
            boosted = process.pid in self._boosted
            self._boosted.discard(process.pid)

            if previous is not None and previous.pid != process.pid:
                self.context_switch_time_ns += previous.hardware_context_switch(process)
                self.context_switch_time_ms += C_SW
                self.time_ms += C_SW
                context_switches += 1

            process.state = ProcessState.RUNNING
            first_start.setdefault(process.pid, self.time_ms)
            start = self.time_ms
            quantum = self.QUEUE_QUANTA[level]
            duration = (
                process.remaining_burst
                if quantum is None
                else min(process.remaining_burst, quantum)
            )
            if level == 2 and pending:
                until_arrival = float(pending[0].arrival_time) - self.time_ms
                if 0 < until_arrival < duration:
                    duration = until_arrival
            self.time_ms += duration
            process.remaining_burst = max(0.0, process.remaining_burst - duration)
            trace.append((process.pid, start, self.time_ms))
            queue_trace.append(
                {"pid": process.pid, "queue": level, "start": start, "end": self.time_ms}
            )
            self._admit(pending)

            if process.remaining_burst <= 0.0:
                process.remaining_burst = 0.0
                process.state = ProcessState.TERMINATED
                completion[process.pid] = self.time_ms
            else:
                process.state = ProcessState.READY
                next_level = 2 if boosted else level
                self._queue_levels[process.pid] = next_level
                self._ready_since[process.pid] = self.time_ms
                self._queues[next_level].append(process)
            previous = process

        waiting_times = [
            completion[process.pid]
            - process.arrival_time
            - float(process.burst_time or 0.0)
            for process in pending + [entry for entry in processes]
            if process.pid in completion
        ]
        turnaround_times = [
            completion[process.pid] - process.arrival_time for process in processes
        ]
        count = len(processes)
        return {
            "metrics": {
                "AWT": sum(waiting_times) / count if count else 0.0,
                "ATAT": sum(turnaround_times) / count if count else 0.0,
            },
            "trace": trace,
            "queue_trace": queue_trace,
            "queue_depths": ready_depths,
            "context_switches": context_switches,
            "context_switch_time_ms": self.context_switch_time_ms,
            "context_switch_time_ns": self.context_switch_time_ns,
            "total_time_ms": self.time_ms,
        }

    def _admit(self, pending: list[ExtendedPCB]) -> None:
        while pending and pending[0].arrival_time <= self.time_ms:
            process = pending.pop(0)
            level = 0 if process.priority <= 1 else 1 if process.priority == 2 else 2
            process.state = ProcessState.READY
            self._queue_levels[process.pid] = level
            self._ready_since[process.pid] = self.time_ms
            self._queues[level].append(process)

    def _promote_aged(self) -> None:
        retained: deque[ExtendedPCB] = deque()
        while self._queues[2]:
            process = self._queues[2].popleft()
            waited = self.time_ms - self._ready_since[process.pid]
            if waited > self.AGING_THRESHOLD_MS:
                self._queue_levels[process.pid] = 0
                self._boosted.add(process.pid)
                self._queues[0].append(process)
            else:
                retained.append(process)
        self._queues[2] = retained

    def _reset(self) -> None:
        self.time_ms = 0.0
        self.context_switch_time_ms = 0.0
        self.context_switch_time_ns = 0
        self._queues = [deque(), deque(), deque()]
        self._queue_levels.clear()
        self._ready_since.clear()
        self._boosted.clear()


class PCP_IntersectionManager:
    """Manage three monotonic zone mutexes with priority ceiling elevation."""

    ZONES = (1, 2, 3)
    CEILING_PRIORITY = 1

    def __init__(self) -> None:
        self._order = MonotonicIntersectionLock()
        self._ceilings = {
            zone: PriorityCeilingMutex(ceiling=self.CEILING_PRIORITY)
            for zone in self.ZONES
        }

    @contextmanager
    def hold(self, process: ExtendedPCB, *zones: int) -> Iterator[None]:
        """Hold ascending zone locks and restore priority after release."""
        if not zones:
            raise ValueError("at least one intersection zone is required")
        if any(zone not in self.ZONES for zone in zones):
            raise ValueError("zone must be 1, 2, or 3")
        with self._order.hold(*zones):
            with ExitStack() as stack:
                for zone in zones:
                    mutex = self._ceilings[zone]
                    if not mutex.acquire(process, priority=process.priority):
                        raise RuntimeError(f"failed to acquire zone {zone}")
                    stack.callback(mutex.release, process)
                yield

    def acquire_zones(
        self, process: ExtendedPCB, zones: Sequence[int]
    ) -> Any:
        """Return a context manager for acquiring an ordered zone sequence."""
        return self.hold(process, *zones)


class BankersEngine:
    """Dijkstra Banker safety checks for four agents and three zones."""

    PROCESSES = (0, 1, 2, 3)
    RESOURCE_COUNT = 3

    def __init__(
        self,
        available: Sequence[int] = (1, 1, 1),
        max_matrix: Mapping[int, Sequence[int]] | None = None,
        allocation_matrix: Mapping[int, Sequence[int]] | None = None,
    ) -> None:
        maximum = max_matrix or {pid: [1, 1, 1] for pid in self.PROCESSES}
        allocation = allocation_matrix or {
            pid: [0, 0, 0] for pid in self.PROCESSES
        }
        self._algorithm = BankersAlgorithm(
            self.PROCESSES, available, maximum, allocation
        )

    @property
    def available(self) -> list[int]:
        return self._algorithm.available.copy()

    @property
    def max_matrix(self) -> dict[int, list[int]]:
        return {pid: row.copy() for pid, row in self._algorithm.max_matrix.items()}

    @property
    def allocation_matrix(self) -> dict[int, list[int]]:
        return {
            pid: row.copy()
            for pid, row in self._algorithm.allocation_matrix.items()
        }

    @property
    def need_matrix(self) -> dict[int, list[int]]:
        return self._algorithm.need_matrix

    def safe_sequence(self) -> list[int] | None:
        return self._algorithm.safe_sequence()

    def request_corridor(
        self, pid: int, request_vector: Sequence[int]
    ) -> dict[str, Any]:
        """Grant only safe requests; the underlying engine rolls back failures."""
        if len(request_vector) != self.RESOURCE_COUNT or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in request_vector
        ):
            raise ValueError(
                "request_vector must contain three non-negative integer zone values"
            )
        before = self._algorithm.safe_sequence()
        granted = self._algorithm.request_corridor(pid, request_vector)
        return {
            "granted": granted,
            "outcome": "safe" if granted else "unsafe_rollback",
            "safe_sequence": self._algorithm.safe_sequence() if granted else before,
            "available": self.available,
        }


class MemoryManager:
    """Compare live frame-reference streams across four replacement policies."""

    POLICIES = ("FIFO", "LRU", "LFU", "Optimal")

    def __init__(
        self, capacity: int = FRAME_CAPACITY, reference_limit: int = PAGE_REFERENCE_LIMIT
    ) -> None:
        if capacity <= 0 or reference_limit <= 0:
            raise ValueError("capacity and reference_limit must be positive")
        self.capacity = capacity
        self._references: deque[int] = deque(maxlen=reference_limit)
        self._lock = threading.Lock()

    def reference(self, page: int) -> dict[str, Any]:
        """Record one camera-frame page and return the updated policy metrics."""
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            raise ValueError("page must be a non-negative integer")
        with self._lock:
            self._references.append(page)
            references = list(self._references)
        return self._calculate(references)

    def snapshot(self) -> dict[str, Any]:
        """Return policy hits, faults, and ratios for the current rolling stream."""
        with self._lock:
            references = list(self._references)
        return self._calculate(references)

    def _calculate(self, references: Sequence[int]) -> dict[str, Any]:
        results = compare_page_replacement(references, self.capacity) if references else {
            name: {"page_faults": 0, "page_hits": 0, "fault_ratio": 0.0}
            for name in self.POLICIES
        }
        count = len(references)
        policies = {
            name: {
                **metrics,
                "hit_ratio": metrics["page_hits"] / count if count else 0.0,
            }
            for name, metrics in results.items()
        }
        return {
            "capacity": self.capacity,
            "reference_count": count,
            "frames_used": min(self.capacity, len(set(references))),
            "policies": policies,
            **policies,
        }


class KernelService:
    """Own the simulated junction, scheduler, memory, and OS telemetry state."""

    def __init__(self, *, seed: int = 2026) -> None:
        self._random = random.Random(seed)
        self._lock = threading.RLock()
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._tick = 0
        self._started_at = time.monotonic()
        self._vehicle_sequence = 0
        self._frame_sequence = 0
        self._pending_emergency: tuple[str, str] | None = None
        self._override_direction: str | None = None
        self._override_until = 0
        self._intersection_manager = PCP_IntersectionManager()
        self._scheduler = MLFQScheduler()
        self._banker = self._new_banker()
        self.memory_manager = MemoryManager()
        self._queues: dict[str, deque[dict[str, Any]]] = {
            direction: deque(maxlen=64) for direction in DIRECTIONS
        }
        self._shared_memory: ZeroCopySharedMemory | None = None
        self._shared_memory_error: str | None = None
        self._shared_bytes_total = 0
        self._shared_bytes_per_second = 0.0
        self._last_frame_window = time.monotonic()
        self._frames_in_window = 0
        self._emergency_count = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=80)
        self._watchdog_restarts = 0
        self._state: dict[str, Any] = self._initial_state()

    async def start(self) -> None:
        """Start the background simulation task once."""
        if self._task is not None and not self._task.done():
            return
        self._stop_requested = False
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(
            self.run_kernel_loop(), name="kernel-service-20hz"
        )
        self._record_event("service_started", "20 Hz simulation loop started")

    async def stop(self) -> None:
        """Stop the simulation and release shared-memory resources cleanly."""
        self._stop_requested = True
        task = self._task
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._task = None
        await asyncio.to_thread(self._close_shared_memory)

    def snapshot(self) -> dict[str, Any]:
        """Return an isolated copy of the current state for concurrent readers."""
        return self.get_system_snapshot()

    def get_system_snapshot(self) -> dict[str, Any]:
        """Return an isolated, thread-safe system snapshot."""
        with self._lock:
            result = copy.deepcopy(self._state)
            result["events"] = list(self._events)[-20:]
            result["uptime_seconds"] = round(time.monotonic() - self._started_at, 2)
            return result

    def get_active_cores(self) -> dict[str, dict[str, Any]]:
        """Return an isolated, thread-safe view of each simulated CPU core."""
        with self._lock:
            cpu = self._state["cpu"]
            cores = {"core0": copy.deepcopy(cpu["core0"])}
            cores.update(
                {
                    f"core{core['core']}": copy.deepcopy(core)
                    for core in cpu["cores1_3"]
                }
            )
            return cores

    def get_current_signal_lights(self) -> dict[str, str]:
        """Return the current phase of each approach's signal light."""
        with self._lock:
            return {
                direction: state["phase"]
                for direction, state in self._state["traffic"].items()
            }

    def get_memory_hit_ratios(self) -> dict[str, float]:
        """Return current hit ratios for all four replacement policies."""
        with self._lock:
            policies = self._state["memory"].get("policy_metrics", {})
            return {
                name: float(metrics["hit_ratio"])
                for name, metrics in policies.items()
            }

    def trigger_emergency(self, vehicle_type: str = "Ambulance") -> dict[str, Any]:
        """Queue an immediate priority-zero emergency preemption."""
        normalized = vehicle_type.strip().title()
        if normalized not in {"Ambulance", "Fire"}:
            raise ValueError("vehicle_type must be Ambulance or Fire")
        with self._lock:
            direction = self._random.choice(DIRECTIONS)
            self._vehicle_sequence += 1
            vehicle = {
                "pid": f"{normalized.lower()}-{self._vehicle_sequence}",
                "kind": normalized,
                "priority": 0,
                "arrival_time": time.monotonic(),
            }
            self._queues[direction].appendleft(vehicle)
            self._pending_emergency = (direction, vehicle["pid"])
            self._override_direction = direction
            self._override_until = self._tick + 40
            self._emergency_count += 1
            cpu = self._state["cpu"]
            previous_pid = cpu["core0"]["active_process"]
            previous_process = ExtendedPCB(
                pid=str(previous_pid),
                tgid=0,
                priority=min(4, int(cpu["core0"].get("priority", 1))),
                remaining_burst=1.0,
            )
            emergency_process = ExtendedPCB(
                pid=vehicle["pid"],
                tgid=0,
                priority=0,
                remaining_burst=1.0,
                registers={
                    "RIP": self._vehicle_sequence * 0x1000,
                    "RSP": self._vehicle_sequence * 0x8000,
                    "CR3": self._vehicle_sequence * 0x10000,
                },
            )
            switch_latency_ns = previous_process.hardware_context_switch(
                emergency_process
            )
            self._record_event(
                "emergency_preemption",
                f"Priority 0 {normalized} preemption at {direction}",
                direction=direction,
                pid=vehicle["pid"],
                context_switch_latency_ns=switch_latency_ns,
            )
            cpu["core0"]["active_process"] = vehicle["pid"]
            cpu["core0"]["priority"] = 0
            cpu["context_switches"] = cpu.get("context_switches", 0) + 1
            cpu["context_switch_time_ns"] = (
                cpu.get("context_switch_time_ns", 0) + switch_latency_ns
            )
            cpu["emergency_switch_latency_ns"] = switch_latency_ns
            self._state["emergency_count"] = self._emergency_count
            self._state["emergency_override"] = {
                "active": True,
                "direction": direction,
                "vehicle_type": normalized,
                "priority": 0,
                "pcp_effective_priority": 0,
            }
            self._state["traffic"][direction]["phase"] = "GREEN"
            self._state["traffic"][direction]["lock_holder_pid"] = vehicle["pid"]
        return self.snapshot()

    def request_corridor(
        self, process_id: int | str, resources: Sequence[int]
    ) -> dict[str, Any]:
        """Run Banker's safety check and return its sequence or rollback result."""
        resolved_id = self._resolve_banker_pid(process_id)
        if len(resources) != 3 or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in resources
        ):
            raise ValueError("resources must contain three non-negative integers")
        with self._lock:
            decision = self._banker.request_corridor(resolved_id, resources)
            result = {
                **decision,
                "pid": process_id,
                "process_id": resolved_id,
                "resources": list(resources),
            }
            self._record_event(
                "banker_request",
                f"Corridor request {'granted' if decision['granted'] else 'rolled back'} for {process_id}",
                **result,
            )
            return result

    @staticmethod
    def _resolve_banker_pid(process_id: int | str) -> int:
        """Map operator process labels and legacy indices to Banker IDs."""
        if isinstance(process_id, int) and not isinstance(process_id, bool):
            if process_id in range(4):
                return process_id
        elif isinstance(process_id, str):
            aliases = {
                "P0": 0,
                "P1": 0,
                "P1_AMBULANCE": 0,
                "P2": 1,
                "P2_BRT_BUS": 1,
                "P3": 2,
                "P3_SMARTTRANSIT": 2,
                "P4": 3,
                "P4_LOGISTICS": 3,
            }
            if process_id.strip().upper() in aliases:
                return aliases[process_id.strip().upper()]
        raise ValueError("pid must identify one of P1_Ambulance through P4_Logistics")

    async def run_kernel_loop(self) -> None:
        """Run the 20 Hz control loop without blocking the async event loop."""
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while not self._stop_requested:
                await asyncio.to_thread(self._tick_once)
                next_tick += TICK_SECONDS
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except asyncio.CancelledError:
            raise

    async def _run_loop(self) -> None:
        """Compatibility alias for the original private loop entry point."""
        await self.run_kernel_loop()

    def _tick_once(self) -> None:
        """Advance one simulation tick without blocking the async event loop."""
        tick_started = time.perf_counter()
        with self._lock:
            self._tick += 1
            self._generate_regular_traffic()
            emergency = self._pending_emergency
            if emergency is None and self._tick > self._override_until:
                self._override_direction = None
            direction = self._override_direction or self._cycle_direction()
            traffic = self._traffic_snapshot(direction)
            schedule = self._scheduler.run(self._create_workloads())
            self._service_one_vehicle(direction)
            self._record_video_frame()
            self._pending_emergency = None

            active_pid = (
                emergency[1]
                if emergency is not None
                else schedule["trace"][-1][0]
                if schedule["trace"]
                else "idle"
            )
            self._state = {
                **self._state,
                "tick": self._tick,
                "timestamp": time.time(),
                "cpu": {
                    "core0": {
                        "role": "RT Actuator",
                        "active_process": active_pid,
                        "priority": 0 if emergency else 1,
                        "utilization_percent": round(
                            min(100.0, 20.0 + len(traffic) * 9.0), 1
                        ),
                    },
                    "cores1_3": [
                        {
                            "core": core,
                            "role": "Vision Ingest",
                            "active_process": f"vision-worker-{core}",
                            "utilization_percent": round(
                                24.0 + ((self._tick + core * 13) % 54), 1
                            ),
                        }
                        for core in range(1, 4)
                    ],
                    "context_switch_penalty_ms": C_SW,
                    "average_wait_ms": schedule["metrics"]["AWT"],
                    "average_turnaround_ms": schedule["metrics"]["ATAT"],
                    "mlfq_average_wait_ms": schedule["metrics"]["AWT"],
                    "priority_trace": schedule["trace"],
                    "mlfq_trace": schedule["queue_trace"],
                    "context_switches": schedule["context_switches"],
                    "context_switch_time_ns": schedule["context_switch_time_ns"],
                },
                "queues": {
                    "priority_depth": sum(len(queue) for queue in self._queues.values()),
                    "mlfq": schedule["queue_depths"],
                },
                "traffic": traffic,
                "memory": self._memory_snapshot(),
                "active_locks": [
                    f"Zone {(DIRECTIONS.index(direction) % 3) + 1}: {direction}"
                ],
                "emergency_count": self._emergency_count,
                "emergency_override": {
                    "active": self._override_direction is not None,
                    "direction": self._override_direction,
                    "vehicle_type": emergency[1].split("-")[0].title()
                    if emergency
                    else None,
                    "priority": 0 if self._override_direction else None,
                    "pcp_effective_priority": 0 if self._override_direction else None,
                },
                "watchdogs": {
                    "process_manager": "healthy",
                    "vision_worker": "healthy",
                    "restart_count": self._watchdog_restarts,
                },
                "simulation": {
                    "mode": "simulated",
                    "tick_hz": 20,
                    "last_tick_ms": 0.0,
                    "schedule_time_ms": schedule["total_time_ms"],
                },
            }
            if emergency is not None:
                self._record_event(
                    "emergency_dispatched",
                    f"{emergency[1]} dispatched on {emergency[0]}",
                    direction=emergency[0],
                )
            elapsed_ms = (time.perf_counter() - tick_started) * 1000
            self._state["simulation"]["last_tick_ms"] = round(elapsed_ms, 3)

    def _generate_regular_traffic(self) -> None:
        """Add bounded stochastic arrivals to each approach queue."""
        for direction, queue in self._queues.items():
            if len(queue) < queue.maxlen and self._random.random() < 0.055:
                self._vehicle_sequence += 1
                queue.append(
                    {
                        "pid": f"vehicle-{self._vehicle_sequence}",
                        "kind": "Vehicle",
                        "priority": self._random.randint(1, 4),
                        "arrival_time": time.monotonic(),
                    }
                )

    def _create_workloads(self) -> list[ExtendedPCB]:
        """Build independent PCB workloads from the four approach queues."""
        workloads: list[ExtendedPCB] = []
        for index, direction in enumerate(DIRECTIONS):
            queue = self._queues[direction]
            vehicle = queue[0] if queue else None
            pid = vehicle["pid"] if vehicle else f"idle-{direction.lower()}"
            priority = vehicle["priority"] if vehicle else 3
            workloads.append(
                ExtendedPCB(
                    pid=pid,
                    tgid=index + 1,
                    priority=priority,
                    remaining_burst=float(1 + len(queue) % 6),
                    registers={
                        "RIP": (index + 1) * 0x1000,
                        "RSP": (index + 1) * 0x8000,
                        "CR3": (index + 1) * 0x10000,
                    },
                    arrival_time=0.0,
                )
            )
        return workloads

    def _service_one_vehicle(self, direction: str) -> None:
        """Model a protected phase update and service the active approach."""
        zone = (DIRECTIONS.index(direction) % 3) + 1
        queue = self._queues[direction]
        lock_pid = queue[0]["pid"] if queue else f"signal-{direction.lower()}"
        signal_task = ExtendedPCB(
            pid=lock_pid,
            tgid=zone,
            priority=0 if self._override_direction else 4,
        )
        original_priority = signal_task.priority
        try:
            with self._intersection_manager.hold(signal_task, zone):
                queue = self._queues[direction]
                if queue:
                    queue.popleft()
                if signal_task.priority != min(original_priority, 1):
                    raise RuntimeError("PCP priority elevation invariant failed")
        except RuntimeError as error:
            self._record_event("lock_error", str(error))

    def _record_video_frame(self) -> None:
        """Page a small synthetic video tensor through policies and shared memory."""
        self._frame_sequence += 1
        page = self._random.randrange(16)
        self.memory_manager.reference(page)
        frame = bytes((self._frame_sequence + index) % 256 for index in range(4096))
        if self._shared_memory is None and self._shared_memory_error is None:
            try:
                self._shared_memory = ZeroCopySharedMemory(SHARED_FRAME_BYTES)
            except (OSError, RuntimeError) as error:
                self._shared_memory_error = str(error)
        if self._shared_memory is not None:
            try:
                self._shared_memory.write_frame(frame)
                self._shared_memory.read_frame(timeout=0.01)
                self._shared_bytes_total += len(frame)
                self._frames_in_window += 1
            except (OSError, RuntimeError, TimeoutError) as error:
                self._shared_memory_error = str(error)

    def _memory_snapshot(self) -> dict[str, Any]:
        """Calculate current replacement-policy metrics from recent references."""
        comparison = self.memory_manager.snapshot()
        policies = comparison["policies"]
        lru = policies["LRU"]
        fifo = policies["FIFO"]
        lfu = policies["LFU"]
        optimal = policies["Optimal"]
        now = time.monotonic()
        elapsed = now - self._last_frame_window
        if elapsed >= 1.0:
            self._shared_bytes_per_second = int(
                self._frames_in_window * 4096 / max(elapsed, 0.001)
            )
            self._frames_in_window = 0
            self._last_frame_window = now
        return {
            "frame_capacity": FRAME_CAPACITY,
            "frames_used": comparison["frames_used"],
            "page_references": comparison["reference_count"],
            "page_faults": int(lru.get("page_faults", 0)),
            "page_hits": int(lru.get("page_hits", 0)),
            "hit_ratio": round(float(lru["hit_ratio"]), 3),
            "fifo_hit_ratio": round(float(fifo["hit_ratio"]), 3),
            "lru_hit_ratio": round(float(lru["hit_ratio"]), 3),
            "lru_faults": int(lru.get("page_faults", 0)),
            "fifo_faults": int(fifo.get("page_faults", 0)),
            "lfu_faults": int(lfu.get("page_faults", 0)),
            "optimal_faults": int(optimal.get("page_faults", 0)),
            "policy_metrics": policies,
            "shm_bytes_total": self._shared_bytes_total,
            "shm_bytes_per_second": self._shared_bytes_per_second,
            "shm_name": self._shared_memory.name if self._shared_memory else None,
            "shm_error": self._shared_memory_error,
        }

    def _traffic_snapshot(self, green_direction: str) -> dict[str, dict[str, Any]]:
        """Return light phases and queue depths for all four approaches."""
        phase = "GREEN"
        if self._override_direction is None and self._tick % 140 >= 120:
            phase = "YELLOW"
        return {
            direction: {
                "phase": phase if direction == green_direction else "RED",
                "queue_depth": len(self._queues[direction]),
                "lock_holder": direction if direction == green_direction else None,
                "lock_holder_pid": (
                    self._queues[direction][0]["pid"]
                    if direction == green_direction and self._queues[direction]
                    else f"signal-{direction.lower()}"
                    if direction == green_direction
                    else None
                ),
                "approach": direction,
            }
            for direction in DIRECTIONS
        }

    def _cycle_direction(self) -> str:
        """Select a six-second green phase followed by a one-second yellow."""
        return DIRECTIONS[(self._tick // 140) % len(DIRECTIONS)]

    def _record_event(self, event_type: str, message: str, **details: Any) -> None:
        """Append one timestamped event while the state lock is held."""
        with self._lock:
            self._events.append(
                {
                    "timestamp": time.time(),
                    "type": event_type,
                    "message": message,
                    **details,
                }
            )

    def _close_shared_memory(self) -> None:
        """Close and unlink the service-owned POSIX shared-memory object."""
        with self._lock:
            if self._shared_memory is None:
                return
            try:
                self._shared_memory.close()
            finally:
                try:
                    self._shared_memory.unlink()
                except FileNotFoundError:
                    pass
                self._shared_memory = None

    def _new_banker(self) -> BankersEngine:
        """Create the four-agent, three-zone safety model."""
        return BankersEngine()

    def _initial_state(self) -> dict[str, Any]:
        """Create a stable API state before the first simulation tick."""
        memory = self.memory_manager.snapshot()
        return {
            "tick": 0,
            "timestamp": time.time(),
            "emergency_count": 0,
            "emergency_override": {
                "active": False,
                "direction": None,
                "vehicle_type": None,
                "priority": None,
                "pcp_effective_priority": None,
            },
            "cpu": {
                "core0": {"role": "RT Actuator", "active_process": "signal-controller", "priority": 1, "utilization_percent": 0.0},
                "cores1_3": [
                    {"core": core, "role": "Vision Ingest", "active_process": "idle", "utilization_percent": 0.0}
                    for core in range(1, 4)
                ],
                "context_switch_penalty_ms": C_SW,
                "context_switches": 0,
                "context_switch_time_ns": 0,
                "average_wait_ms": 0.0,
                "average_turnaround_ms": 0.0,
                "mlfq_average_wait_ms": 0.0,
                "priority_trace": [],
                "mlfq_trace": [],
            },
            "queues": {"priority_depth": 0, "mlfq": [0, 0, 0]},
            "traffic": {
                direction: {
                    "phase": "RED",
                    "queue_depth": 0,
                    "lock_holder": None,
                    "lock_holder_pid": None,
                    "approach": direction,
                }
                for direction in DIRECTIONS
            },
            "memory": {
                "frame_capacity": FRAME_CAPACITY,
                "frames_used": 0,
                "page_references": 0,
                "page_faults": 0,
                "page_hits": 0,
                "hit_ratio": 0.0,
                "fifo_hit_ratio": 0.0,
                "lru_hit_ratio": 0.0,
                "lru_faults": 0,
                "fifo_faults": 0,
                "lfu_faults": 0,
                "optimal_faults": 0,
                "policy_metrics": memory["policies"],
                "shm_bytes_total": 0,
                "shm_bytes_per_second": 0,
                "shm_name": None,
                "shm_error": None,
            },
            "active_locks": [],
            "watchdogs": {"process_manager": "healthy", "vision_worker": "healthy", "restart_count": 0},
            "simulation": {"mode": "simulated", "tick_hz": 20, "last_tick_ms": 0.0, "schedule_time_ms": 0.0},
            "events": [],
        }


__all__ = [
    "BankersEngine",
    "DIRECTIONS",
    "ExtendedPCB",
    "KernelService",
    "MLFQScheduler",
    "MemoryManager",
    "PCP_IntersectionManager",
    "ProcessState",
    "TICK_SECONDS",
]
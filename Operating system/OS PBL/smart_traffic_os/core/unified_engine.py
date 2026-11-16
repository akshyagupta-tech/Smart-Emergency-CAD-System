"""Unified 10 Hz Smart Traffic OS controller.

This is a deterministic simulation engine, not a certified physical signal
controller. Hardware actuation must be provided through a separately validated
driver and fail-safe interlocks.
"""

from __future__ import annotations

import asyncio
import copy
import random
import threading
import time
from collections.abc import Sequence
from typing import Any

from core.kernel_service import (
    BankersEngine,
    DIRECTIONS,
    ExtendedPCB,
    MLFQScheduler,
    MemoryManager,
    PCP_IntersectionManager,
)
from core.pcb_manager import ProcessState
from scheduling.engine import C_SW

TICK_SECONDS = 0.1
FRAME_CAPACITY = 3


class UnifiedEngine:
    """Compose scheduling, intersection locking, Banker checks, and paging."""

    def __init__(self, *, seed: int = 2026) -> None:
        self._random = random.Random(seed)
        self._lock = threading.RLock()
        self._task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._tick = 0
        self._started_at = time.monotonic()
        self._pid_sequence = 0
        self._pending_emergency: tuple[str, ExtendedPCB] | None = None
        self._scheduler = MLFQScheduler()
        self._intersection = PCP_IntersectionManager()
        self._banker = BankersEngine()
        self._memory = MemoryManager(capacity=FRAME_CAPACITY)
        self._state: dict[str, Any] = self._initial_state()

    async def start(self) -> None:
        """Start the asynchronous real-time loop if it is not already running."""
        if self._task is not None and not self._task.done():
            return
        self._stop_requested = False
        self._started_at = time.monotonic()
        self._task = asyncio.create_task(self.run_loop(), name="unified-engine-10hz")

    async def stop(self) -> None:
        """Stop the loop and wait for any active tick to finish."""
        self._stop_requested = True
        task = self._task
        if task is None:
            return
        await task
        self._task = None

    async def run_loop(self) -> None:
        """Run ticks at 10 Hz while keeping synchronous work off the event loop."""
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        try:
            while not self._stop_requested:
                await asyncio.to_thread(self._tick_once)
                deadline += TICK_SECONDS
                await asyncio.sleep(max(0.0, deadline - loop.time()))
        except asyncio.CancelledError:
            raise

    def get_live_telemetry(self) -> dict[str, Any]:
        """Return an isolated thread-safe copy of the current telemetry state."""
        with self._lock:
            snapshot = copy.deepcopy(self._state)
            snapshot["uptime_seconds"] = round(
                time.monotonic() - self._started_at, 3
            )
            snapshot["timestamp"] = time.time()
            return snapshot

    def trigger_emergency_override(self) -> dict[str, Any]:
        """Immediately dispatch a priority-zero ambulance task on Core 0."""
        with self._lock:
            self._pid_sequence += 1
            direction = self._random.choice(DIRECTIONS)
            pid = f"ambulance-{self._pid_sequence}"
            emergency = ExtendedPCB(
                pid=pid,
                tgid=0,
                priority=0,
                remaining_burst=2.0,
                registers={
                    "RIP": self._pid_sequence * 0x1000,
                    "RSP": self._pid_sequence * 0x8000,
                    "CR3": self._pid_sequence * 0x10000,
                },
            )
            active_pid = str(self._state["cpu"]["core0"]["active_process"])
            previous = ExtendedPCB(
                pid=active_pid or "signal-controller",
                tgid=0,
                priority=1,
                remaining_burst=1.0,
            )
            latency_ns = previous.hardware_context_switch(emergency)
            self._pending_emergency = (direction, emergency)
            self._state["emergency_override"] = {
                "active": True,
                "direction": direction,
                "pid": pid,
                "priority": 0,
                "context_switch_latency_ns": latency_ns,
            }
            self._state["cpu"]["core0"].update(
                {
                    "active_process": pid,
                    "priority": 0,
                    "context_switches": self._state["cpu"]["core0"].get(
                        "context_switches", 0
                    )
                    + 1,
                    "context_switch_latency_ns": latency_ns,
                }
            )
            self._state["traffic"] = self._traffic_state(direction, pid)
            self._record_event(
                "emergency_preemption",
                pid=pid,
                direction=direction,
                context_switch_latency_ns=latency_ns,
            )
        return self.get_live_telemetry()

    def evaluate_corridor_request(
        self, pid: int | str, request: Sequence[int]
    ) -> dict[str, Any]:
        """Evaluate a dynamic three-zone claim and preserve Banker rollback."""
        process_id = self._resolve_process_id(pid)
        with self._lock:
            result = self._banker.request_corridor(process_id, request)
            result.update(
                {
                    "pid": pid,
                    "process_id": process_id,
                    "request": list(request),
                }
            )
            self._record_event(
                "corridor_request",
                pid=pid,
                granted=result["granted"],
                safe_sequence=result["safe_sequence"],
            )
            return result

    @staticmethod
    def _resolve_process_id(pid: int | str) -> int:
        if isinstance(pid, int) and not isinstance(pid, bool) and pid in range(4):
            return pid
        if isinstance(pid, str):
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
            process_id = aliases.get(pid.strip().upper())
            if process_id is not None:
                return process_id
        raise ValueError("pid must identify one of P1_Ambulance through P4_Logistics")

    def _tick_once(self) -> None:
        started = time.perf_counter()
        with self._lock:
            self._tick += 1
            direction = self._pending_emergency[0] if self._pending_emergency else (
                DIRECTIONS[(self._tick - 1) % len(DIRECTIONS)]
            )
            workloads = self._create_workload(direction)
            schedule = self._scheduler.run(workloads)
            active_pid = (
                self._pending_emergency[1].pid
                if self._pending_emergency is not None
                else schedule["trace"][-1][0]
                if schedule["trace"]
                else "idle"
            )

            active_process = ExtendedPCB(
                pid=active_pid,
                tgid=DIRECTIONS.index(direction) + 1,
                priority=0 if self._pending_emergency else 2,
                remaining_burst=1.0,
            )
            zone = (DIRECTIONS.index(direction) % 3) + 1
            with self._intersection.hold(active_process, zone):
                traffic = self._traffic_state(direction, active_pid)

            page = self._random.randrange(8)
            memory = self._memory.reference(page)
            self._state.update(
                {
                    "tick": self._tick,
                    "cpu": {
                        "core0": {
                            "role": "RT Actuator",
                            "active_process": active_pid,
                            "priority": 0 if self._pending_emergency else active_process.priority,
                            "utilization_percent": round(
                                min(100.0, 25.0 + len(schedule["trace"]) * 5.0), 1
                            ),
                            "context_switches": schedule["context_switches"],
                            "context_switch_time_ns": schedule[
                                "context_switch_time_ns"
                            ],
                        },
                        "cores1_3": [
                            {
                                "core": core,
                                "role": "Vision AI",
                                "active_process": f"vision-worker-{core}",
                                "utilization_percent": round(
                                    20.0 + ((self._tick + core * 11) % 65), 1
                                ),
                            }
                            for core in range(1, 4)
                        ],
                        "context_switch_penalty_ms": C_SW,
                        "average_wait_ms": schedule["metrics"]["AWT"],
                        "average_turnaround_ms": schedule["metrics"]["ATAT"],
                        "mlfq_trace": schedule["queue_trace"],
                    },
                    "queues": {
                        "mlfq": schedule["queue_depths"],
                        "priority_depth": len(workloads),
                    },
                    "traffic": traffic,
                    "memory": self._memory_state(memory),
                    "simulation": {
                        "mode": "simulated",
                        "tick_hz": 10,
                        "last_tick_ms": round(
                            (time.perf_counter() - started) * 1000, 3
                        ),
                        "schedule_time_ms": schedule["total_time_ms"],
                    },
                }
            )
            if self._pending_emergency is not None:
                self._state["emergency_override"]["active"] = True
                self._pending_emergency = None
            else:
                self._state["emergency_override"] = {
                    "active": False,
                    "direction": None,
                    "pid": None,
                    "priority": None,
                    "context_switch_latency_ns": None,
                }

    def _create_workload(self, active_direction: str) -> list[ExtendedPCB]:
        workload: list[ExtendedPCB] = []
        for index, direction in enumerate(DIRECTIONS):
            self._pid_sequence += 1
            priority = 0 if self._pending_emergency and direction == active_direction else (
                self._random.randint(1, 4)
            )
            workload.append(
                ExtendedPCB(
                    pid=(
                        self._pending_emergency[1].pid
                        if self._pending_emergency and direction == active_direction
                        else f"vehicle-{self._pid_sequence}"
                    ),
                    tgid=index + 1,
                    priority=priority,
                    remaining_burst=float(self._random.randint(1, 6)),
                    arrival_time=0.0,
                    registers={
                        "RIP": (index + 1) * 0x1000,
                        "RSP": (index + 1) * 0x8000,
                        "CR3": (index + 1) * 0x10000,
                    },
                )
            )
        return workload

    @staticmethod
    def _memory_state(metrics: dict[str, Any]) -> dict[str, Any]:
        policies = metrics["policies"]
        return {
            "frame_capacity": FRAME_CAPACITY,
            "frames_used": metrics["frames_used"],
            "page_references": metrics["reference_count"],
            "policy_metrics": policies,
            "fifo_faults": policies["FIFO"]["page_faults"],
            "lru_faults": policies["LRU"]["page_faults"],
            "lfu_faults": policies["LFU"]["page_faults"],
            "optimal_faults": policies["Optimal"]["page_faults"],
        }

    def _traffic_state(
        self, green_direction: str, holder_pid: str | None = None
    ) -> dict[str, dict[str, Any]]:
        return {
            direction: {
                "phase": "GREEN" if direction == green_direction else "RED",
                "queue_depth": 0,
                "lock_holder": direction if direction == green_direction else None,
                "lock_holder_pid": (
                    holder_pid or f"signal-{direction.lower()}"
                    if direction == green_direction
                    else None
                ),
                "approach": direction,
            }
            for direction in DIRECTIONS
        }

    def _record_event(self, event_type: str, **details: Any) -> None:
        self._state["events"].append(
            {"timestamp": time.time(), "type": event_type, **details}
        )
        del self._state["events"][:-20]

    @staticmethod
    def _initial_state() -> dict[str, Any]:
        return {
            "tick": 0,
            "timestamp": time.time(),
            "uptime_seconds": 0.0,
            "cpu": {
                "core0": {
                    "role": "RT Actuator",
                    "active_process": "signal-controller",
                    "priority": 1,
                    "utilization_percent": 0.0,
                    "context_switches": 0,
                    "context_switch_time_ns": 0,
                },
                "cores1_3": [
                    {
                        "core": core,
                        "role": "Vision AI",
                        "active_process": "idle",
                        "utilization_percent": 0.0,
                    }
                    for core in range(1, 4)
                ],
                "context_switch_penalty_ms": C_SW,
                "average_wait_ms": 0.0,
                "average_turnaround_ms": 0.0,
                "mlfq_trace": [],
            },
            "queues": {"mlfq": [0, 0, 0], "priority_depth": 0},
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
                "policy_metrics": {
                    policy: {
                        "page_faults": 0,
                        "page_hits": 0,
                        "fault_ratio": 0.0,
                        "hit_ratio": 0.0,
                    }
                    for policy in MemoryManager.POLICIES
                },
                "fifo_faults": 0,
                "lru_faults": 0,
                "lfu_faults": 0,
                "optimal_faults": 0,
            },
            "emergency_override": {
                "active": False,
                "direction": None,
                "pid": None,
                "priority": None,
                "context_switch_latency_ns": None,
            },
            "simulation": {
                "mode": "simulated",
                "tick_hz": 10,
                "last_tick_ms": 0.0,
                "schedule_time_ms": 0.0,
            },
            "events": [],
        }


__all__ = ["FRAME_CAPACITY", "TICK_SECONDS", "UnifiedEngine"]
"""Run bounded local chaos checks against the Smart Traffic OS simulation.

Worker crashes are limited to a child process spawned by this test. Memory
pressure is capped at 16 MiB. The runner reports missing watchdog and lock-lease
recovery as failures rather than claiming that the current project implements
those mechanisms.
"""

from __future__ import annotations

import argparse
import random
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from textwrap import fill
from types import SimpleNamespace
from typing import Callable, TextIO

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from concurrency.manager import MonotonicIntersectionLock, PriorityCeilingMutex
from core.pcb_manager import ExtendedPCB
from scheduling.engine import C_SW, simulate_round_robin

LOG_PATH = PROJECT_ROOT / "logs" / "chaos_monkey.log"
MAX_MEMORY_BYTES = 16 * 1024 * 1024
WATCHDOG_DEADLINE_SECONDS = 0.2
LOCK_LEASE_SECONDS = 0.05


@dataclass(frozen=True, slots=True)
class FaultResult:
    name: str
    passed: bool
    measured: str
    detail: str


class ChaosEngine:
    """Inject local faults while a scheduler workload remains active."""

    def __init__(self, seed: int) -> None:
        self.random = random.Random(seed)
        self.seed = seed
        self.stop_simulation = threading.Event()
        self.simulation_iterations = 0
        self.simulation_thread = threading.Thread(
            target=self._run_simulation, name="chaos-simulation", daemon=True
        )

    def run(self) -> list[FaultResult]:
        actions: list[Callable[[], FaultResult]] = [
            self._inject_worker_crash,
            self._inject_memory_pressure,
            self._inject_lock_starvation,
            self._inject_core_throttle,
        ]
        self.random.shuffle(actions)
        results: list[FaultResult] = []
        self.simulation_thread.start()
        try:
            for action in actions:
                results.append(action())
        finally:
            self.stop_simulation.set()
            self.simulation_thread.join(timeout=1.0)
        return results

    def _run_simulation(self) -> None:
        while not self.stop_simulation.is_set():
            workload = [
                ExtendedPCB(pid="vehicle-1", tgid=1, burst_time=3.0, priority=1),
                ExtendedPCB(pid="camera-1", tgid=2, burst_time=4.0, priority=2),
                ExtendedPCB(pid="signal-1", tgid=3, burst_time=2.0, priority=0),
            ]
            simulate_round_robin(workload, context_switch_overhead=C_SW)
            self.simulation_iterations += 1
            self.stop_simulation.wait(0.002)

    def _inject_worker_crash(self) -> FaultResult:
        worker = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started = time.perf_counter()
        try:
            worker.send_signal(signal.SIGKILL)
            return_code = worker.wait(timeout=1.0)
            observed_ms = (time.perf_counter() - started) * 1000
            detected_in_time = observed_ms <= WATCHDOG_DEADLINE_SECONDS * 1000
            restarted = False
            return FaultResult(
                name="Worker Crash",
                passed=detected_in_time and restarted,
                measured=f"child_exit_observed={observed_ms:.2f} ms, returncode={return_code}",
                detail=(
                    "SIGKILL was confined to the test-owned worker; no daemon "
                    "watchdog/restart hook exists in this project."
                ),
            )
        finally:
            if worker.poll() is None:
                worker.terminate()
                worker.wait(timeout=1.0)

    def _inject_memory_pressure(self) -> FaultResult:
        pressure = bytearray(MAX_MEMORY_BYTES)
        for offset in range(0, len(pressure), 4096):
            pressure[offset] = 1
        allocated_mib = len(pressure) / (1024 * 1024)
        del pressure
        watchdog_triggered = False
        return FaultResult(
            name="Memory Pressure",
            passed=watchdog_triggered,
            measured=f"bounded_allocation={allocated_mib:.0f} MiB, threshold=85% RAM",
            detail=(
                "No 85%-RAM watchdog is implemented; allocation was capped at "
                "16 MiB to avoid destabilizing the host."
            ),
        )

    def _inject_lock_starvation(self) -> FaultResult:
        intersection = MonotonicIntersectionLock()
        mutex = PriorityCeilingMutex(ceiling=1)
        rogue_task = SimpleNamespace(priority=5)
        acquired = threading.Event()
        release_rogue = threading.Event()

        def rogue_holder() -> None:
            intersection.acquire(1)
            mutex.acquire(rogue_task)
            acquired.set()
            try:
                release_rogue.wait(LOCK_LEASE_SECONDS * 4)
            finally:
                mutex.release(rogue_task)
                intersection.release(1)

        holder = threading.Thread(target=rogue_holder, name="rogue-lock-holder")
        holder.start()
        try:
            if not acquired.wait(timeout=0.5):
                return FaultResult(
                    "Lock Starvation", False, "lock acquisition timed out", "PCP test setup failed."
                )
            time.sleep(LOCK_LEASE_SECONDS)
            intersection_available = intersection.acquire(1, blocking=False)
            if intersection_available:
                intersection.release(1)
            lease_broken = mutex.owner is None and intersection_available
            return FaultResult(
                name="Lock Starvation",
                passed=lease_broken,
                measured=(
                    f"lease={LOCK_LEASE_SECONDS * 1000:.0f} ms, "
                    f"intersection_available={intersection_available}, "
                    f"owner_priority={rogue_task.priority}"
                ),
                detail=(
                    "PCP raises the rogue owner's priority, but neither it nor "
                    "MonotonicIntersectionLock enforces an expiring lease."
                ),
            )
        finally:
            release_rogue.set()
            holder.join(timeout=1.0)

    def _inject_core_throttle(self) -> FaultResult:
        workload = [
            ExtendedPCB(pid="cpu-1", tgid=11, burst_time=3.0, priority=1),
            ExtendedPCB(pid="cpu-2", tgid=12, burst_time=4.0, priority=2),
            ExtendedPCB(pid="cpu-3", tgid=13, burst_time=2.0, priority=0),
        ]
        baseline = simulate_round_robin(
            workload,
            context_switch_overhead=C_SW,
        )
        throttled = simulate_round_robin(
            workload,
            context_switch_overhead=max(C_SW * 25, 5.0),
        )
        baseline_ms = baseline["context_switch_time"]
        throttled_ms = throttled["context_switch_time"]
        passed = throttled_ms > baseline_ms
        return FaultResult(
            name="Core Throttle",
            passed=passed,
            measured=f"modeled_switch_cost={baseline_ms:.2f} -> {throttled_ms:.2f} ms",
            detail="Scheduler latency was increased through the simulation's overhead parameter; no hardware frequency was changed.",
        )


def _write_scorecard(
    results: list[FaultResult], seed: int, simulation_iterations: int
) -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Chaos run seed={seed} time={time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"{'Scenario':<20} {'Result':<7} Measurement",
        "-" * 74,
    ]
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        row = f"{result.name:<20} {status:<7} {result.measured}"
        lines.append(fill(row, width=74, subsequent_indent="  "))
        lines.append(fill(f"  {result.detail}", width=74, subsequent_indent="    "))
    passed = sum(result.passed for result in results)
    lines.append("-" * 74)
    lines.append(f"Resilience score: {passed}/{len(results)} recovery benchmarks passed")

    rendered = "\n".join(lines)
    print(rendered)
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(rendered + "\n\n")
    print(f"Simulation iterations: {simulation_iterations}")
    print(f"Log: {LOG_PATH}")
    return 0 if passed == len(results) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=2026, help="fault order seed")
    args = parser.parse_args(argv)
    engine = ChaosEngine(args.seed)
    results = engine.run()
    return _write_scorecard(results, args.seed, engine.simulation_iterations)


if __name__ == "__main__":
    raise SystemExit(main())
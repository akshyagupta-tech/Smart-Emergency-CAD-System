"""One-click execution pipeline for the Smart Traffic OS simulation."""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from concurrency.manager import (
    MonotonicIntersectionLock,
    PriorityCeilingMutex,
    TrafficBankersAlgorithm,
)
from core.pcb_manager import ExtendedPCB, ProcessState
from memory.page_replacement import compare_page_replacement
from memory.virtual_memory import ZeroCopySharedMemory
from scheduling.engine import (
    ScheduleResult,
    simulate_mlfq,
    simulate_preemptive_priority,
    simulate_round_robin,
)
from telemetry.visualizer import render_memory_benchmark, render_scheduling_gantt

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Validated runtime dependency versions."""

    numpy: str
    matplotlib: str


def main() -> int:
    """Run every simulation stage and open generated charts on macOS."""
    print("Smart Traffic OS master pipeline")
    dependencies = validate_dependencies()
    print(f"Dependencies: numpy {dependencies.numpy}, matplotlib {dependencies.matplotlib}")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _run_pcb_audit()
    scheduling_results = _run_scheduling()
    _run_concurrency_checks()
    memory_results = _run_memory_benchmark()
    gantt_path, memory_path = _render_outputs(scheduling_results, memory_results)
    _open_in_preview(gantt_path, memory_path)
    print(f"Pipeline complete. Audit log: {LOG_DIR / 'context_switch_audit.log'}")
    return 0


def validate_dependencies() -> DependencyStatus:
    """Import and report required numerical and plotting dependencies."""
    try:
        numpy = importlib.import_module("numpy")
        matplotlib = importlib.import_module("matplotlib")
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency. Install requirements with: "
            "python3 -m pip install numpy matplotlib"
        ) from error
    return DependencyStatus(numpy.__version__, matplotlib.__version__)


def _run_pcb_audit() -> None:
    print("\n[1/6] PCB context-switch audit")
    log_path = LOG_DIR / "context_switch_audit.log"
    log_path.write_text("Smart Traffic OS context-switch audit\n", encoding="ascii")
    vehicle = ExtendedPCB(
        pid="ambulance-01",
        tgid=1,
        priority=0,
        burst_time=4.0,
        registers={"RIP": 0x1000, "RSP": 0x2000, "CR3": 0x3000, "FLAGS": 0x202},
    )
    vehicle.transition_state(ProcessState.READY)
    vehicle.transition_state(ProcessState.RUNNING)
    vehicle.dump_registers(str(log_path))
    vehicle.trigger_interrupt("emergency_preemption")
    vehicle.dump_registers(str(log_path))
    print(f"Wrote {log_path}")


def _traffic_workload() -> list[ExtendedPCB]:
    return [
        ExtendedPCB(pid="car-01", tgid=101, priority=3, burst_time=5.0),
        ExtendedPCB(pid="ambulance-02", tgid=102, priority=0, burst_time=2.0, arrival_time=1.0),
        ExtendedPCB(pid="bus-03", tgid=103, priority=2, burst_time=4.0, arrival_time=2.0),
        ExtendedPCB(pid="truck-04", tgid=104, priority=4, burst_time=3.0, arrival_time=3.0),
    ]


def _run_scheduling() -> dict[str, ScheduleResult]:
    print("\n[2/6] CPU scheduling comparison")
    results = {
        "Preemptive Priority": simulate_preemptive_priority(_traffic_workload()),
        "3-Tier MLFQ": simulate_mlfq(_traffic_workload()),
        "Round Robin": simulate_round_robin(_traffic_workload()),
    }
    print("Algorithm             AWT      ATAT     ART      Throughput")
    print("-" * 63)
    for name, result in results.items():
        metrics = result["metrics"]
        print(
            f"{name:<21} {metrics['AWT']:>7.2f}  {metrics['ATAT']:>7.2f}  "
            f"{metrics['ART']:>7.2f}  {metrics['Throughput']:>10.4f}"
        )
    return results


def _run_concurrency_checks() -> None:
    print("\n[3/6] Concurrency and deadlock checks")
    locks = MonotonicIntersectionLock()
    with locks.hold(1, 2, 3):
        print("Monotonic locks: Zone 1 -> Zone 2 -> Zone 3 acquired")

    priority_vehicle = ExtendedPCB(pid="ambulance-03", tgid=103, priority=5)
    with PriorityCeilingMutex().hold(priority_vehicle):
        assert priority_vehicle.priority == 1
    assert priority_vehicle.priority == 5
    print("PCP: ceiling elevation and restoration passed")

    banker = TrafficBankersAlgorithm(
        processes=[0, 1, 2, 3, 4],
        available=[3, 3, 2],
        max_demand={
            0: [7, 5, 3], 1: [3, 2, 2], 2: [9, 0, 2],
            3: [2, 2, 2], 4: [4, 3, 3],
        },
        allocation={
            0: [0, 1, 0], 1: [2, 0, 0], 2: [3, 0, 2],
            3: [2, 1, 1], 4: [0, 0, 2],
        },
    )
    sequence = banker.is_safe_state()
    if sequence is None:
        raise RuntimeError("traffic corridor Banker state is unsafe")
    print(f"Banker safety sequence: {sequence}")


def _run_memory_benchmark() -> dict[str, dict[str, int | float]]:
    print("\n[4/6] Memory benchmark and shared-memory demo")
    pages = [
        1, 2, 3, 4, 1, 2, 5, 1, 2, 3,
        4, 5, 2, 1, 3, 4, 5, 1, 2, 3,
    ]
    results = compare_page_replacement(pages, capacity=3)
    print("Algorithm  Faults  Hits  Fault ratio")
    print("-" * 40)
    for name, metrics in results.items():
        print(
            f"{name:<9} {metrics['page_faults']:>6}  {metrics['page_hits']:>4}  "
            f"{metrics['fault_ratio']:.4f}"
        )

    with ZeroCopySharedMemory(4096) as shared:
        frame = bytes(range(64))
        shared.write_frame(frame)
        if shared.read_frame(timeout=1.0) != frame:
            raise RuntimeError("shared-memory frame verification failed")
        shared.unlink()
    print("Shared-memory camera frame round trip passed")
    return results


def _render_outputs(
    scheduling_results: dict[str, ScheduleResult],
    memory_results: dict[str, dict[str, int | float]],
) -> tuple[Path, Path]:
    print("\n[5/6] Rendering telemetry charts")
    gantt_path = OUTPUT_DIR / "traffic_gantt_chart.png"
    memory_path = OUTPUT_DIR / "memory_benchmark_chart.png"
    render_scheduling_gantt(
        scheduling_results["Preemptive Priority"]["trace"],
        scheduling_results["3-Tier MLFQ"]["trace"],
        scheduling_results["Round Robin"]["trace"],
        str(gantt_path),
    )
    render_memory_benchmark(memory_results, str(memory_path))
    print(f"Generated {gantt_path}")
    print(f"Generated {memory_path}")
    return gantt_path, memory_path


def _open_in_preview(*paths: Path) -> None:
    print("\n[6/6] Opening charts")
    if sys.platform != "darwin":
        print("Skipping macOS Preview launch on non-macOS platform")
        return
    for path in paths:
        subprocess.run(["open", str(path)], check=False)
        print(f"Opened {path}")


if __name__ == "__main__":
    raise SystemExit(main())
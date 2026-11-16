"""System-level tests for the Smart Traffic OS prototype."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from unittest.mock import patch

from concurrency.manager import LockOrderViolation, TrafficBankersAlgorithm
from core.kernel_service import (
    BankersEngine,
    ExtendedPCB as KernelPCB,
    KernelService,
    MLFQScheduler,
    MemoryManager,
    PCP_IntersectionManager,
    TICK_SECONDS,
)
from core.pcb_manager import ExtendedPCB
from core.unified_engine import UnifiedEngine
from memory.virtual_memory import (
    simulate_fifo,
    simulate_lru,
    simulate_optimal,
)
from scheduling.engine import C_SW, ExecutionSlice, simulate_preemptive_priority


def test_preemptive_priority_math() -> None:
    """Verify emergency zero-jitter behavior and penalty-free AWT math."""
    workload = [
        ExtendedPCB(pid="P1", tgid=1, arrival_time=0.0, burst_time=3.0, priority=1),
        ExtendedPCB(pid="P2", tgid=2, arrival_time=1.0, burst_time=5.0, priority=2),
        ExtendedPCB(pid="P3", tgid=3, arrival_time=2.0, burst_time=8.0, priority=3),
        ExtendedPCB(pid="P4", tgid=4, arrival_time=3.0, burst_time=4.0, priority=4),
    ]

    result = simulate_preemptive_priority(workload)

    assert result["process_metrics"]["P1"]["waiting_time"] == 0.0
    assert _average_waiting_without_switch_penalty(
        result["trace"], workload
    ) == 5.25


def test_bankers_deadlock_avoidance() -> None:
    """Reject P4's unsafe corridor request and preserve the original state."""
    banker = TrafficBankersAlgorithm(
        processes=[
            "P1_Ambulance",
            "P2_BRT_Bus",
            "P3_SmartTransit",
            "P4_Logistics",
        ],
        available=[1, 1, 1],
        max_demand={
            "P1_Ambulance": [2, 1, 1],
            "P2_BRT_Bus": [2, 2, 1],
            "P3_SmartTransit": [3, 1, 2],
            "P4_Logistics": [2, 2, 2],
        },
        allocation={
            "P1_Ambulance": [1, 0, 0],
            "P2_BRT_Bus": [1, 1, 0],
            "P3_SmartTransit": [1, 0, 1],
            "P4_Logistics": [0, 1, 1],
        },
    )
    expected_sequence = [
        "P1_Ambulance",
        "P2_BRT_Bus",
        "P3_SmartTransit",
        "P4_Logistics",
    ]
    assert banker.is_safe_state() == expected_sequence

    available_before = banker.available.copy()
    allocation_before = {
        pid: vector.copy() for pid, vector in banker.allocation.items()
    }
    assert banker.request_resources("P4_Logistics", [1, 1, 0]) is False
    assert banker.available == available_before
    assert banker.allocation == allocation_before


def test_page_replacement_optimality() -> None:
    """Verify the expected capacity-three benchmark ordering."""
    pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]

    optimal_faults = simulate_optimal(pages, 3)[0]
    lru_faults = simulate_lru(pages, 3)[0]
    fifo_faults = simulate_fifo(pages, 3)[0]

    assert optimal_faults == 9
    assert optimal_faults <= lru_faults < fifo_faults
    assert lru_faults == 12
    assert fifo_faults == 15


def test_kernel_hardware_context_switch_applies_penalty_and_logs_addresses() -> None:
    previous = KernelPCB(
        "previous",
        1,
        registers={"RIP": 0x10, "RSP": 0x20, "CR3": 0x30},
    )
    next_process = KernelPCB(
        "next",
        2,
        registers={"RIP": 0x40, "RSP": 0x50, "CR3": 0x60},
    )
    with patch("core.kernel_service.time.sleep") as sleep:
        latency_ns = previous.hardware_context_switch(next_process)

    sleep.assert_called_once_with(C_SW / 1000)
    assert latency_ns > 0
    assert previous.last_context_switch_ns == latency_ns
    assert previous.total_switches == 1


def test_kernel_mlfq_ages_queue_two_tasks_into_queue_zero() -> None:
    workload = [
        KernelPCB(f"high-{index}", index, priority=0, remaining_burst=2.0)
        for index in range(8)
    ]
    workload.append(KernelPCB("aged", 9, priority=4, remaining_burst=1.0))

    result = MLFQScheduler().run(workload)

    assert any(
        event["pid"] == "aged" and event["queue"] == 0
        for event in result["queue_trace"]
    )
    assert result["context_switches"] > 0
    assert result["context_switch_time_ns"] > 0
    assert abs(
        result["total_time_ms"]
        - sum(float(process.burst_time or 0.0) for process in workload)
        - result["context_switches"] * C_SW
    ) < 1e-9
    assert all(process.state.name == "TERMINATED" for process in workload)


def test_kernel_pcp_restores_priority_and_rejects_reverse_order() -> None:
    process = KernelPCB("ambulance", 1, priority=4)
    manager = PCP_IntersectionManager()

    with manager.hold(process, 1, 2, 3):
        assert process.priority == 1
    assert process.priority == 4

    try:
        with manager.hold(process, 2, 1):
            raise AssertionError("reverse zone order should have been rejected")
    except LockOrderViolation:
        pass
    assert process.priority == 4


def test_kernel_banker_rolls_back_unsafe_corridor_request() -> None:
    banker = BankersEngine(
        available=[3, 3, 2],
        max_matrix={
            0: [7, 5, 3],
            1: [3, 2, 2],
            2: [9, 0, 2],
            3: [2, 2, 2],
        },
        allocation_matrix={
            0: [0, 1, 0],
            1: [2, 0, 0],
            2: [3, 0, 2],
            3: [2, 1, 1],
        },
    )
    available_before = banker.available
    allocation_before = banker.allocation_matrix

    result = banker.request_corridor(0, [3, 3, 0])

    assert result["granted"] is False
    assert result["outcome"] == "unsafe_rollback"
    assert result["safe_sequence"] is not None
    assert banker.available == available_before
    assert banker.allocation_matrix == allocation_before


def test_kernel_memory_manager_reports_all_policy_ratios() -> None:
    manager = MemoryManager(capacity=3)
    result = {}
    for page in [1, 2, 1, 3, 1, 2, 4, 1, 2, 3]:
        result = manager.reference(page)

    assert set(result["policies"]) == {"FIFO", "LRU", "LFU", "Optimal"}
    assert result["reference_count"] == 10
    for policy in result["policies"].values():
        assert policy["page_hits"] + policy["page_faults"] == 10
        assert 0.0 <= policy["hit_ratio"] <= 1.0
        assert 0.0 <= policy["fault_ratio"] <= 1.0


def test_kernel_async_loop_publishes_thread_safe_snapshot() -> None:
    service = KernelService()

    async def run_and_stop() -> None:
        await service.start()
        try:
            await asyncio.sleep(TICK_SECONDS * 2.5)
            snapshot = service.get_system_snapshot()
            assert snapshot["tick"] >= 2
            assert snapshot["simulation"]["tick_hz"] == 20
            assert set(snapshot["memory"]["policy_metrics"]) == {
                "FIFO",
                "LRU",
                "LFU",
                "Optimal",
            }
            assert set(service.get_memory_hit_ratios()) == {
                "FIFO",
                "LRU",
                "LFU",
                "Optimal",
            }
        finally:
            await service.stop()

    asyncio.run(run_and_stop())


def test_unified_engine_composes_live_os_modules() -> None:
    engine = UnifiedEngine(seed=7)

    async def run_and_stop() -> None:
        await engine.start()
        try:
            await asyncio.sleep(0.22)
            snapshot = engine.get_live_telemetry()
            assert snapshot["tick"] >= 2
            assert snapshot["simulation"]["tick_hz"] == 10
            assert snapshot["memory"]["frame_capacity"] == 3
            assert set(snapshot["memory"]["policy_metrics"]) == {
                "FIFO",
                "LRU",
                "LFU",
                "Optimal",
            }
            assert set(snapshot["traffic"]) == {"North", "South", "East", "West"}

            emergency = engine.trigger_emergency_override()
            assert emergency["cpu"]["core0"]["priority"] == 0
            assert emergency["emergency_override"]["active"]
            claim = engine.evaluate_corridor_request("P4_Logistics", [1, 1, 0])
            assert claim["granted"] and claim["safe_sequence"]
        finally:
            await engine.stop()

    asyncio.run(run_and_stop())


def _average_waiting_without_switch_penalty(
    trace: Iterable[ExecutionSlice], workload: Iterable[ExtendedPCB]
) -> float:
    """Compress switch gaps and calculate the trace's penalty-free AWT."""
    durations: dict[str, float] = {}
    for pid, start, end in trace:
        durations[pid] = durations.get(pid, 0.0) + (end - start)

    virtual_time = 0.0
    waiting_times: list[float] = []
    for process in sorted(workload, key=lambda item: (item.arrival_time, item.pid)):
        virtual_time = max(virtual_time, process.arrival_time)
        virtual_time += durations[process.pid]
        waiting_times.append(
            virtual_time - process.arrival_time - process.burst_time
        )
    return sum(waiting_times) / len(waiting_times)
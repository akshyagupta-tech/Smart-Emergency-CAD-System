#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
OUTPUT_DIR="${ROOT_DIR}/output"
DEMO_LOG="${LOG_DIR}/recorded_demo.log"
ROTATE_AT_BYTES=$((1024 * 1024))

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"
cd "${ROOT_DIR}"

if [[ -f "${DEMO_LOG}" ]] && (( $(wc -c < "${DEMO_LOG}") >= ROTATE_AT_BYTES )); then
    mv -f "${DEMO_LOG}" "${DEMO_LOG}.1"
fi

exec > >(tee -a "${DEMO_LOG}") 2>&1

printf '\033[2J\033[H'
printf '\n'
printf '======================================================================\n'
printf ' SMART TRAFFIC OS - REAL-TIME KERNEL SIMULATOR\n'
printf '======================================================================\n\n'
sleep 0.8

step() {
    printf '\n[DEMO] %s\n' "$1"
    sleep 0.8
}

step "Module 1: System health watchdog and log rotation check"
printf '[WATCHDOG] Python runtime: '
python3 --version
sleep 0.8
printf '[WATCHDOG] Required packages: '
python3 - <<'PY'
import importlib

for package in ("numpy", "matplotlib"):
    module = importlib.import_module(package)
    print(f"{package}={module.__version__}", end=" ")
print()
PY
sleep 0.8
printf '[WATCHDOG] Audit log: '
if [[ -f "${LOG_DIR}/context_switch_audit.log" ]]; then
    printf 'present (%s bytes)\n' "$(wc -c < "${LOG_DIR}/context_switch_audit.log")"
else
    printf 'not found; creating baseline\n'
    printf 'Smart Traffic OS demo audit\n' > "${LOG_DIR}/context_switch_audit.log"
fi
sleep 0.8
printf '[WATCHDOG] Log rotation check: PASS\n'
if [[ -f "${DEMO_LOG}.1" ]]; then
    printf '[WATCHDOG] Previous demo log rotated to: %s\n' "${DEMO_LOG}.1"
else
    printf '[WATCHDOG] Demo log is below the 1 MiB rotation threshold\n'
fi
sleep 0.8

step "Module 2: CPU scheduling math comparison"
python3 - <<'PY'
from core.pcb_manager import ExtendedPCB
from scheduling.engine import (
    simulate_mlfq,
    simulate_preemptive_priority,
    simulate_round_robin,
)

def workload():
    return [
        ExtendedPCB(pid="P1", tgid=1, arrival_time=0, burst_time=3, priority=1),
        ExtendedPCB(pid="P2", tgid=2, arrival_time=1, burst_time=5, priority=2),
        ExtendedPCB(pid="P3", tgid=3, arrival_time=2, burst_time=8, priority=3),
        ExtendedPCB(pid="P4", tgid=4, arrival_time=3, burst_time=4, priority=4),
    ]

results = {
    "Preemptive Priority": simulate_preemptive_priority(workload()),
    "3-Tier MLFQ": simulate_mlfq(workload()),
    "Round Robin": simulate_round_robin(workload()),
}
print("Algorithm             AWT      ATAT     ART      Switches")
print("-" * 63)
for name, result in results.items():
    metrics = result["metrics"]
    print(
        f"{name:<21} {metrics['AWT']:>7.2f}  {metrics['ATAT']:>7.2f}  "
        f"{metrics['ART']:>7.2f}  {result['context_switches']:>8}"
    )
PY
sleep 0.8

step "Module 3: Banker's Algorithm corridor request and rollback test"
python3 - <<'PY'
from concurrency.manager import TrafficBankersAlgorithm

banker = TrafficBankersAlgorithm(
    processes=["P1_Ambulance", "P2_BRT_Bus", "P3_SmartTransit", "P4_Logistics"],
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
print("SAFE SEQUENCE:", " -> ".join(banker.is_safe_state() or []))
available_before = banker.available.copy()
allocation_before = {pid: values.copy() for pid, values in banker.allocation.items()}
accepted = banker.request_resources("P4_Logistics", [1, 1, 0])
rolled_back = banker.available == available_before and banker.allocation == allocation_before
print(f"P4 request [1, 1, 0]: {'GRANTED' if accepted else 'DENIED'}")
print(f"Rollback integrity: {'PASS' if rolled_back else 'FAIL'}")
if accepted or not rolled_back:
    raise SystemExit(1)
PY
sleep 0.8

step "Module 4: Page replacement benchmark table"
python3 - <<'PY'
from memory.virtual_memory import simulate_fifo, simulate_lfu, simulate_lru, simulate_optimal

pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
results = {
    "FIFO": simulate_fifo(pages, 3),
    "LRU": simulate_lru(pages, 3),
    "LFU": simulate_lfu(pages, 3),
    "Optimal": simulate_optimal(pages, 3),
}
print("Policy      Faults  Hits  Fault Ratio")
print("-" * 39)
for name, (faults, hits, ratio) in results.items():
    print(f"{name:<10} {faults:>6}  {hits:>4}  {ratio:>11.4f}")
PY
sleep 0.8

step "Rendering scheduling and memory charts"
python3 - <<'PY'
from core.pcb_manager import ExtendedPCB
from memory.virtual_memory import simulate_fifo, simulate_lfu, simulate_lru, simulate_optimal
from scheduling.engine import (
    simulate_mlfq,
    simulate_preemptive_priority,
    simulate_round_robin,
)
from telemetry.visualizer import render_memory_benchmark, render_scheduling_gantt

def workload():
    return [
        ExtendedPCB(pid="P1", tgid=1, arrival_time=0, burst_time=3, priority=1),
        ExtendedPCB(pid="P2", tgid=2, arrival_time=1, burst_time=5, priority=2),
        ExtendedPCB(pid="P3", tgid=3, arrival_time=2, burst_time=8, priority=3),
        ExtendedPCB(pid="P4", tgid=4, arrival_time=3, burst_time=4, priority=4),
    ]

scheduling = {
    "Preemptive Priority": simulate_preemptive_priority(workload()),
    "3-Tier MLFQ": simulate_mlfq(workload()),
    "Round Robin": simulate_round_robin(workload()),
}
render_scheduling_gantt(
    scheduling["Preemptive Priority"]["trace"],
    scheduling["3-Tier MLFQ"]["trace"],
    scheduling["Round Robin"]["trace"],
    "output/traffic_gantt_chart.png",
)

pages = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
raw_results = {
    "FIFO": simulate_fifo(pages, 3),
    "LRU": simulate_lru(pages, 3),
    "LFU": simulate_lfu(pages, 3),
    "Optimal": simulate_optimal(pages, 3),
}
memory = {
    name: {"page_faults": faults, "page_hits": hits}
    for name, (faults, hits, _ratio) in raw_results.items()
}
render_memory_benchmark(memory, "output/memory_benchmark_chart.png")
print("Generated output/traffic_gantt_chart.png")
print("Generated output/memory_benchmark_chart.png")
PY
sleep 0.8

printf '\n======================================================================\n'
printf ' DEMO COMPLETE: ALL MODULES EXECUTED\n'
printf '======================================================================\n'
printf 'Charts:\n'
printf '  - %s\n' "${OUTPUT_DIR}/traffic_gantt_chart.png"
printf '  - %s\n' "${OUTPUT_DIR}/memory_benchmark_chart.png"
printf 'Logs:\n'
printf '  - %s\n' "${LOG_DIR}/context_switch_audit.log"
printf '  - %s\n' "${DEMO_LOG}"
if [[ -f "${DEMO_LOG}.1" ]]; then
    printf '  - %s\n' "${DEMO_LOG}.1"
fi
printf '\n'
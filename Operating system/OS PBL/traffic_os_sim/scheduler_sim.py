#!/usr/bin/env python3
"""
Module 2: Advanced Real-Time CPU Scheduling Simulator & Mathematical Engine
Includes: Context Switch Overhead (C_sw), Dynamic CSV parsing, Preemptive Priority,
Round Robin, and 3-Tier Multilevel Feedback Queue (MLFQ).
"""
import copy
from typing import List, Tuple

CONTEXT_SWITCH_OVERHEAD = 0.2  # 0.2 ms penalty on process switch

class Process:
    def __init__(self, pid: str, arrival_time: float, burst_time: float, priority: int):
        self.pid = pid
        self.arrival_time = float(arrival_time)
        self.burst_time = float(burst_time)
        self.priority = int(priority)
        self.remaining_time = float(burst_time)
        self.completion_time = 0.0
        self.waiting_time = 0.0
        self.turnaround_time = 0.0
        self.first_run_time = -1.0
        self.total_switches = 0

def simulate_preemptive_priority(workload: List[Process], c_sw: float = CONTEXT_SWITCH_OVERHEAD):
    procs = copy.deepcopy(workload)
    completed, curr_time, gantt = 0, 0.0, []
    prev_pid = None

    while completed < len(procs):
        ready = [p for p in procs if p.arrival_time <= curr_time and p.remaining_time > 0]
        if not ready:
            curr_time += 1.0
            continue
        ready.sort(key=lambda x: x.priority)
        p = ready[0]

        if prev_pid is not None and prev_pid != p.pid:
            curr_time += c_sw
            p.total_switches += 1

        if p.first_run_time == -1.0:
            p.first_run_time = curr_time

        step = 0.5  # Granular time step
        run_slice = min(step, p.remaining_time)
        start_t = curr_time
        curr_time += run_slice
        p.remaining_time -= run_slice

        if gantt and gantt[-1][0] == p.pid and abs(gantt[-1][2] - start_t) < 1e-4:
            gantt[-1] = (p.pid, gantt[-1][1], round(curr_time, 2))
        else:
            gantt.append((p.pid, round(start_t, 2), round(curr_time, 2)))

        prev_pid = p.pid
        if p.remaining_time <= 1e-6:
            p.completion_time = curr_time
            p.turnaround_time = p.completion_time - p.arrival_time
            p.waiting_time = p.turnaround_time - p.burst_time
            completed += 1

    return procs, gantt

def simulate_round_robin(workload: List[Process], quantum: float = 2.0, c_sw: float = CONTEXT_SWITCH_OVERHEAD):
    procs = copy.deepcopy(workload)
    procs.sort(key=lambda x: x.arrival_time)
    curr_time, queue, gantt = 0.0, [], []
    completed, visited = 0, set()
    prev_pid = None

    def update_queue():
        for p in procs:
            if p.arrival_time <= curr_time and p.pid not in visited:
                queue.append(p)
                visited.add(p.pid)

    update_queue()
    while completed < len(procs):
        if not queue:
            curr_time += 1.0
            update_queue()
            continue
        p = queue.pop(0)

        if prev_pid is not None and prev_pid != p.pid:
            curr_time += c_sw
            p.total_switches += 1

        if p.first_run_time == -1.0:
            p.first_run_time = curr_time

        exec_time = min(quantum, p.remaining_time)
        start_t = curr_time
        curr_time += exec_time
        p.remaining_time -= exec_time

        gantt.append((p.pid, round(start_t, 2), round(curr_time, 2)))
        prev_pid = p.pid
        update_queue()

        if p.remaining_time > 1e-6:
            queue.append(p)
        else:
            p.completion_time = curr_time
            p.turnaround_time = p.completion_time - p.arrival_time
            p.waiting_time = p.turnaround_time - p.burst_time
            completed += 1

    return procs, gantt

def simulate_mlfq(workload: List[Process], c_sw: float = CONTEXT_SWITCH_OVERHEAD):
    """
    3-Queue Multilevel Feedback Queue:
    - Queue 0: Round Robin (q = 2ms)
    - Queue 1: Round Robin (q = 4ms)
    - Queue 2: FCFS (batch jobs)
    """
    procs = copy.deepcopy(workload)
    procs.sort(key=lambda x: x.arrival_time)
    curr_time, gantt = 0.0, []
    q0, q1, q2 = [], [], []
    visited, completed = set(), 0
    prev_pid = None

    def update_queues():
        for p in procs:
            if p.arrival_time <= curr_time and p.pid not in visited:
                q0.append(p)
                visited.add(p.pid)

    update_queues()
    while completed < len(procs):
        if not q0 and not q1 and not q2:
            curr_time += 1.0
            update_queues()
            continue

        if q0:
            p = q0.pop(0)
            quantum = 2.0
            target_next = q1
        elif q1:
            p = q1.pop(0)
            quantum = 4.0
            target_next = q2
        else:
            p = q2.pop(0)
            quantum = p.remaining_time
            target_next = q2

        if prev_pid is not None and prev_pid != p.pid:
            curr_time += c_sw
            p.total_switches += 1

        if p.first_run_time == -1.0:
            p.first_run_time = curr_time

        exec_time = min(quantum, p.remaining_time)
        start_t = curr_time
        curr_time += exec_time
        p.remaining_time -= exec_time

        gantt.append((p.pid, round(start_t, 2), round(curr_time, 2)))
        prev_pid = p.pid
        update_queues()

        if p.remaining_time > 1e-6:
            target_next.append(p)
        else:
            p.completion_time = curr_time
            p.turnaround_time = p.completion_time - p.arrival_time
            p.waiting_time = p.turnaround_time - p.burst_time
            completed += 1

    return procs, gantt

def print_table(name: str, procs: List[Process]):
    print("=" * 72)
    print(f"Policy: {name}")
    print("=" * 72)
    print(f"{'PID':<10} {'Arr':<6} {'Burst':<7} {'Finish':<8} {'TAT':<7} {'Wait':<7} {'Switches':<8}")
    for p in procs:
        print(f"{p.pid:<10} {p.arrival_time:<6.1f} {p.burst_time:<7.1f} {p.completion_time:<8.2f} {p.turnaround_time:<7.2f} {p.waiting_time:<7.2f} {p.total_switches:<8}")
    
    awt = sum(p.waiting_time for p in procs) / len(procs)
    atat = sum(p.turnaround_time for p in procs) / len(procs)
    art = sum((p.first_run_time - p.arrival_time) for p in procs) / len(procs)
    total_time = max(p.completion_time for p in procs)
    print(f"\n[METRICS] AWT: {awt:.2f} ms | ATAT: {atat:.2f} ms | ART: {art:.2f} ms | Throughput: {len(procs)/total_time:.3f} tasks/ms\n")

if __name__ == "__main__":
    workload = [
        Process("P1_Emerg",  0, 3, priority=1),
        Process("P2_Actuat", 1, 5, priority=2),
        Process("P3_Camera", 2, 8, priority=3),
        Process("P4_Telemt", 3, 4, priority=4),
    ]

    rp, gp = simulate_preemptive_priority(workload)
    print_table("Preemptive Priority (with 0.2ms C_sw)", rp)

    rm, gm = simulate_mlfq(workload)
    print_table("3-Tier Multilevel Feedback Queue (MLFQ)", rm)

    rr, gr = simulate_round_robin(workload, quantum=2.0)
    print_table("Round Robin (q=2 with 0.2ms C_sw)", rr)

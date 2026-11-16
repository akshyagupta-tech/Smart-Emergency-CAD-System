#!/usr/bin/env python3
"""
Generates 3-way visual Gantt chart comparing:
1. Round Robin (q=2) - Shows fragmentation and switch overhead
2. Multilevel Feedback Queue (MLFQ) - Recommended multi-tier solution
3. Preemptive Priority - Hard real-time baseline
"""
import matplotlib.pyplot as plt
from scheduler_sim import (
    Process, simulate_preemptive_priority, simulate_round_robin, simulate_mlfq
)

def render_gantt():
    workload = [
        Process("P1_Emerg",  0, 3, priority=1),
        Process("P2_Actuat", 1, 5, priority=2),
        Process("P3_Camera", 2, 8, priority=3),
        Process("P4_Telemt", 3, 4, priority=4),
    ]

    _, gp = simulate_preemptive_priority(workload)
    _, gm = simulate_mlfq(workload)
    _, gr = simulate_round_robin(workload, quantum=2.0)

    fig, ax = plt.subplots(figsize=(11, 5))
    colors = {
        "P1_Emerg": "#e74c3c",   # Red
        "P2_Actuat": "#e67e22",  # Orange
        "P3_Camera": "#3498db",  # Blue
        "P4_Telemt": "#2ecc71"   # Green
    }

    traces = [
        ("Round Robin (q=2)", gr),
        ("3-Tier MLFQ (Q0, Q1, Q2)", gm),
        ("Preemptive Priority", gp)
    ]

    for y_idx, (name, events) in enumerate(traces):
        for pid, start, end in events:
            duration = end - start
            if duration <= 0:
                continue
            ax.barh(y_idx, duration, left=start, color=colors[pid], edgecolor="black", height=0.55)
            if duration >= 1.2:
                mid = (start + end) / 2
                ax.text(mid, y_idx, pid.split("_")[0], ha="center", va="center", color="white", fontweight="bold", fontsize=8.5)

    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["Round Robin (q=2)", "3-Tier MLFQ", "Preemptive Priority"], fontsize=10, fontweight="bold")
    ax.set_xlabel("Time (milliseconds)", fontsize=11, fontweight="bold")
    ax.set_title("Smart Traffic OS - Task Scheduling Timeline (Context-Switch Aware)", fontsize=12, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.6)
    
    plt.tight_layout()
    plt.savefig("traffic_gantt_chart.png", dpi=300)
    print("[SUCCESS] Upgraded Gantt chart generated: 'traffic_gantt_chart.png'")

if __name__ == "__main__":
    render_gantt()

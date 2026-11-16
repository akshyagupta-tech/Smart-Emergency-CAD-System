#!/usr/bin/env python3
"""
Advanced Module 4: Memory Management Visual Benchmark Generator
Renders a comparative analysis of Page Faults and Hit Ratios.
"""
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import matplotlib.pyplot as plt
from phase2.memory.page_replacement_sim import (
    simulate_fifo, simulate_lru, simulate_lfu, simulate_optimal
)

def render_memory_chart():
    reference_string = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
    capacity = 3
    
    algos = {
        "FIFO": simulate_fifo(reference_string, capacity),
        "LRU": simulate_lru(reference_string, capacity),
        "LFU": simulate_lfu(reference_string, capacity),
        "OPTIMAL": simulate_optimal(reference_string, capacity)
    }

    names = list(algos.keys())
    faults = [algos[k][0] for k in names]
    hits = [algos[k][1] for k in names]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bar_width = 0.35
    indices = range(len(names))

    b1 = ax.bar([i - bar_width/2 for i in indices], faults, bar_width, label="Page Faults", color="#e74c3c", edgecolor="black")
    b2 = ax.bar([i + bar_width/2 for i in indices], hits, bar_width, label="Page Hits", color="#2ecc71", edgecolor="black")

    ax.set_xlabel("Page Replacement Policy", fontsize=11, fontweight="bold")
    ax.set_ylabel("Frame Count", fontsize=11, fontweight="bold")
    ax.set_title(f"Virtual Memory Benchmark (Camera Tensor Ingest - Capacity = {capacity} Frames)", fontsize=12, fontweight="bold")
    ax.set_xticks(indices)
    ax.set_xticklabels(names, fontweight="bold")
    ax.legend(frameon=True)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    # Label values on bars
    for bar in b1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(int(bar.get_height())), ha="center", fontweight="bold")
    for bar in b2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3, str(int(bar.get_height())), ha="center", fontweight="bold")

    plt.tight_layout()
    chart_output = ROOT_DIR / "memory_benchmark_chart.png"
    plt.savefig(chart_output, dpi=300)
    print(f"[SUCCESS] Generated visual memory benchmark: '{chart_output.name}'")

if __name__ == "__main__":
    render_memory_chart()

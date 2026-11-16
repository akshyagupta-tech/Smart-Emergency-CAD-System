"""Matplotlib visualizations for scheduling and memory simulations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypeAlias

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

ExecutionSlice: TypeAlias = tuple[str, float, float]
Trace: TypeAlias = Sequence[ExecutionSlice]
BenchmarkResults: TypeAlias = Mapping[str, Mapping[str, int | float]]


def render_scheduling_gantt(
    prio_trace: Trace,
    mlfq_trace: Trace,
    rr_trace: Trace,
    output_filename: str = "traffic_gantt_chart.png",
) -> str:
    """Render three scheduling timelines and return the output path."""
    traces = {
        "Preemptive Priority": prio_trace,
        "3-Tier MLFQ": mlfq_trace,
        "Round Robin": rr_trace,
    }
    process_ids = sorted({item[0] for trace in traces.values() for item in trace})
    colors = {
        pid: plt.get_cmap("tab20")(index % 20)
        for index, pid in enumerate(process_ids)
    }

    figure, axis = plt.subplots(figsize=(13, 5.5), constrained_layout=True)
    lane_positions = {name: index for index, name in enumerate(traces)}
    for lane_name, trace in traces.items():
        lane = lane_positions[lane_name]
        for pid, start, end in trace:
            if end < start:
                raise ValueError(f"trace interval for {pid} ends before it starts")
            width = end - start
            axis.barh(
                lane,
                width,
                left=start,
                height=0.58,
                color=colors[pid],
                edgecolor="white",
                linewidth=0.8,
            )
            if width >= 0.35:
                axis.text(
                    start + width / 2,
                    lane,
                    pid,
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="black",
                )

    axis.set_yticks(list(lane_positions.values()), list(lane_positions))
    axis.invert_yaxis()
    axis.set_xlabel("Time (ms)")
    axis.set_title("Smart Traffic CPU Scheduling Timeline")
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    _add_process_legend(axis, process_ids, colors)
    _save_figure(figure, output_filename)
    return output_filename


def render_memory_benchmark(
    results_dict: BenchmarkResults,
    output_filename: str = "memory_benchmark_chart.png",
) -> str:
    """Render grouped page-fault and page-hit bars for each algorithm."""
    algorithms = ["FIFO", "LRU", "LFU", "Optimal"]
    missing = [algorithm for algorithm in algorithms if algorithm not in results_dict]
    if missing:
        raise ValueError(f"results_dict is missing algorithms: {', '.join(missing)}")

    faults = [results_dict[algorithm]["page_faults"] for algorithm in algorithms]
    hits = [results_dict[algorithm]["page_hits"] for algorithm in algorithms]
    figure, axis = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    positions = list(range(len(algorithms)))
    width = 0.36
    fault_bars = axis.bar(
        [position - width / 2 for position in positions],
        faults,
        width,
        label="Page Faults",
        color="#d95f59",
    )
    hit_bars = axis.bar(
        [position + width / 2 for position in positions],
        hits,
        width,
        label="Page Hits",
        color="#4c9f70",
    )
    _label_bars(axis, fault_bars)
    _label_bars(axis, hit_bars)
    axis.set_xticks(positions, algorithms)
    axis.set_ylabel("References")
    axis.set_title("Page Replacement Benchmark")
    axis.legend()
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    _save_figure(figure, output_filename)
    return output_filename


def _add_process_legend(
    axis: Axes, process_ids: Sequence[str], colors: Mapping[str, object]
) -> None:
    if not process_ids:
        return
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=colors[pid], label=pid)
        for pid in process_ids
    ]
    axis.legend(handles=handles, title="Process", loc="upper right")


def _label_bars(axis: Axes, bars: object) -> None:
    axis.bar_label(bars, fmt="%g", padding=3)


def _save_figure(figure: Figure, output_filename: str) -> None:
    path = Path(output_filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


__all__ = ["render_memory_benchmark", "render_scheduling_gantt"]
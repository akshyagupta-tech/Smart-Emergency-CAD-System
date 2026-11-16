"""Interactive Streamlit dashboard for the Smart Traffic OS demonstration."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from concurrency.manager import TrafficBankersAlgorithm
from core.pcb_manager import ExtendedPCB, ProcessState
from memory.virtual_memory import (
    simulate_fifo,
    simulate_lfu,
    simulate_lru,
    simulate_optimal,
)
from scheduling.engine import (
    simulate_mlfq,
    simulate_preemptive_priority,
    simulate_round_robin,
)


DEFAULT_WORKLOAD = [
    {"pid": "P1", "tgid": 1, "arrival": 0.0, "burst": 3.0, "priority": 1},
    {"pid": "P2", "tgid": 2, "arrival": 1.0, "burst": 5.0, "priority": 2},
    {"pid": "P3", "tgid": 3, "arrival": 2.0, "burst": 8.0, "priority": 3},
    {"pid": "P4", "tgid": 4, "arrival": 3.0, "burst": 4.0, "priority": 4},
]
DEFAULT_PAGES = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
PROCESS_NAMES = ["P1_Ambulance", "P2_BRT_Bus", "P3_SmartTransit", "P4_Logistics"]
RESOURCE_COLUMNS = ["Corridor 1", "Corridor 2", "Corridor 3"]


def main() -> None:
    st.set_page_config(page_title="Smart Traffic OS", page_icon="🚦", layout="wide")
    st.title("Smart Traffic Management System")
    st.caption("Interactive OS simulation dashboard | SDG 11 | NIET Group 02")

    policy, quantum, overhead, workload = sidebar_controls()
    st.subheader(f"Module 2: {policy}")
    schedule_result = run_scheduler(policy, workload, quantum, overhead)
    render_schedule(schedule_result, policy, overhead)

    st.divider()
    render_concurrency()

    st.divider()
    render_memory()


def sidebar_controls() -> tuple[str, float, float, list[ExtendedPCB]]:
    """Render controls and return the selected scheduling inputs."""
    with st.sidebar:
        st.header("Simulation Controls")
        policy = st.selectbox(
            "Scheduling Policy",
            ["Preemptive Priority", "Round Robin", "3-Tier MLFQ"],
        )
        quantum = st.slider("Round Robin Quantum (ms)", 1.0, 5.0, 2.0, 0.5)
        overhead = st.slider("Context Switch Overhead C_sw (ms)", 0.0, 1.0, 0.2, 0.1)
        use_default = st.checkbox("Load default 4-task intersection benchmark", value=True)
        if use_default:
            workload_data = DEFAULT_WORKLOAD
        else:
            st.caption("One process per line: PID, arrival, burst, priority")
            raw_workload = st.text_area(
                "Custom process burst parameters",
                "P1,0,3,1\nP2,1,5,2\nP3,2,8,3\nP4,3,4,4",
            )
            try:
                workload_data = parse_workload(raw_workload)
            except ValueError as error:
                st.error(str(error))
                workload_data = DEFAULT_WORKLOAD
    return policy, quantum, overhead, make_workload(workload_data)


def parse_workload(raw: str) -> list[dict[str, Any]]:
    """Parse custom rows formatted as PID, arrival, burst, priority."""
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 4:
            raise ValueError(f"Line {line_number}: expected PID, arrival, burst, priority")
        pid, arrival, burst, priority = fields
        rows.append({
            "pid": pid,
            "tgid": line_number,
            "arrival": float(arrival),
            "burst": float(burst),
            "priority": int(priority),
        })
    if not rows:
        raise ValueError("Enter at least one process")
    return rows


def make_workload(rows: list[dict[str, Any]]) -> list[ExtendedPCB]:
    return [
        ExtendedPCB(
            pid=str(row["pid"]),
            tgid=int(row["tgid"]),
            arrival_time=float(row["arrival"]),
            burst_time=float(row["burst"]),
            priority=int(row["priority"]),
        )
        for row in rows
    ]


def run_scheduler(
    policy: str,
    workload: list[ExtendedPCB],
    quantum: float,
    overhead: float,
) -> dict[str, Any]:
    """Run the selected scheduler with the current sidebar parameters."""
    if policy == "Preemptive Priority":
        return simulate_preemptive_priority(workload, context_switch_overhead=overhead)
    if policy == "Round Robin":
        return simulate_round_robin(
            workload, quantum=quantum, context_switch_overhead=overhead
        )
    return simulate_mlfq(workload, context_switch_overhead=overhead)


def render_schedule(result: dict[str, Any], policy: str, overhead: float) -> None:
    trace = result["trace"]
    if trace:
        process_ids = sorted({item[0] for item in trace})
        colors = {
            pid: f"hsl({(index * 67) % 360}, 65%, 55%)"
            for index, pid in enumerate(process_ids)
        }
        figure = go.Figure()
        for pid, start, end in trace:
            figure.add_trace(go.Bar(
                x=[end - start],
                y=[pid],
                base=[start],
                orientation="h",
                name=pid,
                marker_color=colors[pid],
                hovertemplate=f"{pid}<br>%{{base:.2f}} - %{{x:.2f}} ms<extra></extra>",
                showlegend=pid not in [trace_item.name for trace_item in figure.data],
            ))
        figure.update_layout(
            barmode="overlay",
            height=360,
            title=f"{policy} execution trace | C_sw = {overhead:.1f} ms",
            xaxis_title="Time (ms)",
            yaxis_title="Process",
            template="plotly_dark",
        )
        st.plotly_chart(figure, use_container_width=True)
    else:
        st.info("No execution slices were produced.")

    metrics = result["process_metrics"]
    metric_frame = pd.DataFrame.from_dict(metrics, orient="index")
    st.dataframe(
        metric_frame[["waiting_time", "turnaround_time", "response_time"]]
        .rename(columns={
            "waiting_time": "Waiting Time (ms)",
            "turnaround_time": "Turnaround Time (ms)",
            "response_time": "Response Time (ms)",
        })
        .round(3),
        use_container_width=True,
    )
    summary = result["metrics"]
    columns = st.columns(4)
    for column, label in zip(columns, ("AWT", "ATAT", "ART", "Throughput")):
        column.metric(label, f"{summary[label]:.3f}")


def render_concurrency() -> None:
    st.subheader("Module 3: Concurrency & Banker's Algorithm")
    available_frame = st.data_editor(
        pd.DataFrame([[1, 1, 1]], columns=RESOURCE_COLUMNS, index=["Available"]),
        key="available_matrix",
        num_rows="fixed",
        use_container_width=True,
    )
    default_allocation = pd.DataFrame(
        [[1, 0, 0], [1, 1, 0], [1, 0, 1], [0, 1, 1]],
        columns=RESOURCE_COLUMNS,
        index=PROCESS_NAMES,
    )
    default_max = pd.DataFrame(
        [[2, 1, 1], [2, 2, 1], [3, 1, 2], [2, 2, 2]],
        columns=RESOURCE_COLUMNS,
        index=PROCESS_NAMES,
    )
    allocation_frame = st.data_editor(default_allocation, key="allocation_matrix", use_container_width=True)
    max_frame = st.data_editor(default_max, key="max_matrix", use_container_width=True)
    if st.button("Evaluate Safe Sequence", type="primary"):
        try:
            banker = TrafficBankersAlgorithm(
                processes=PROCESS_NAMES,
                available=matrix_row(available_frame),
                max_demand=matrix_mapping(max_frame),
                allocation=matrix_mapping(allocation_frame),
            )
            sequence = banker.is_safe_state()
            if sequence is None:
                st.error("Deadlock risk: no complete safe sequence exists.")
            else:
                st.success("Safe sequence: " + " -> ".join(sequence))
        except (TypeError, ValueError, KeyError) as error:
            st.error(f"Matrix validation failed: {error}")

    if st.button("Trigger Emergency Override"):
        emergency = ExtendedPCB(pid="emergency-override", tgid=999, priority=0)
        emergency.transition_state(ProcessState.READY)
        emergency.transition_state(ProcessState.RUNNING)
        if emergency.trigger_interrupt("priority_0"):
            st.success("Emergency override: running task preempted immediately to READY.")


def matrix_row(frame: pd.DataFrame) -> list[int]:
    return [int(frame.iloc[0][column]) for column in RESOURCE_COLUMNS]


def matrix_mapping(frame: pd.DataFrame) -> dict[str, list[int]]:
    return {
        str(index): [int(row[column]) for column in RESOURCE_COLUMNS]
        for index, row in frame.iterrows()
    }


def render_memory() -> None:
    st.subheader("Module 4: Memory Management")
    left, right = st.columns([3, 1])
    with left:
        raw_pages = st.text_input(
            "Page reference string",
            value="7,0,1,2,0,3,0,4,2,3,0,3,2,1,2,0,1,7,0,1",
        )
    with right:
        capacity = st.number_input("Frame capacity", min_value=1, max_value=32, value=3)
    try:
        pages = [int(value.strip()) for value in raw_pages.split(",") if value.strip()]
        results = {
            "FIFO": simulate_fifo(pages, int(capacity)),
            "LRU": simulate_lru(pages, int(capacity)),
            "LFU": simulate_lfu(pages, int(capacity)),
            "Optimal": simulate_optimal(pages, int(capacity)),
        }
        chart = go.Figure()
        chart.add_trace(go.Bar(
            x=list(results),
            y=[metrics[2] for metrics in results.values()],
            text=[f"{metrics[2]:.2%}" for metrics in results.values()],
            textposition="auto",
            marker_color=["#D95F59", "#E6A23C", "#4C9F70", "#23CDB8"],
            name="Fault ratio",
        ))
        chart.update_layout(
            title="Page Fault Ratio Comparison",
            yaxis_title="Fault ratio",
            yaxis_tickformat=".0%",
            template="plotly_dark",
            height=380,
        )
        st.plotly_chart(chart, use_container_width=True)
        st.dataframe(
            pd.DataFrame(
                results,
                index=["Page faults", "Page hits", "Fault ratio"],
            ).T,
            use_container_width=True,
        )
    except (TypeError, ValueError) as error:
        st.error(f"Page input error: {error}")


if __name__ == "__main__":
    main()
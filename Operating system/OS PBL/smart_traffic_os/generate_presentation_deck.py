"""Generate the 12-slide Smart Traffic OS final presentation deck."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "OS_PBL_Final_Presentation.pptx"

SLATE = RGBColor(15, 29, 48)
SLATE_LIGHT = RGBColor(24, 45, 70)
TEAL = RGBColor(35, 205, 184)
TEAL_DARK = RGBColor(18, 123, 123)
WHITE = RGBColor(244, 248, 252)
MUTED = RGBColor(174, 193, 210)
AMBER = RGBColor(245, 180, 75)
RED = RGBColor(231, 104, 104)


def main() -> None:
    """Create and save the complete presentation deck."""
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    presentation.slides._sldIdLst.clear()

    add_title_slide(presentation)
    add_problem_slide(presentation)
    add_paradigm_slide(presentation)
    add_pcb_slide(presentation)
    add_scheduling_matrix_slide(presentation)
    add_scheduling_timeline_slide(presentation)
    add_lock_slide(presentation)
    add_pcp_slide(presentation)
    add_banker_slide(presentation)
    add_memory_slide(presentation)
    add_ipc_slide(presentation)
    add_conclusion_slide(presentation)

    presentation.save(OUTPUT)
    print(f"Generated {OUTPUT}")


def new_slide(presentation: Presentation, title: str, section: str) -> object:
    """Create a themed content slide and return it."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = slide.background.fill
    background.solid()
    background.fore_color.rgb = SLATE
    add_text(slide, section.upper(), 0.65, 0.28, 2.8, 0.25, 10, TEAL, bold=True)
    add_text(slide, title, 0.65, 0.62, 12.0, 0.55, 25, WHITE, bold=True)
    rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.65), Inches(1.35), Inches(1.2), Inches(0.06))
    rule.fill.solid()
    rule.fill.fore_color.rgb = TEAL
    rule.line.fill.background()
    add_text(slide, "SMART TRAFFIC OS  /  NIET  /  GROUP 02", 9.0, 7.12, 3.7, 0.18, 8, MUTED, align=PP_ALIGN.RIGHT)
    return slide


def add_title_slide(presentation: Presentation) -> None:
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = SLATE
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.25), Inches(7.5))
    accent.fill.solid()
    accent.fill.fore_color.rgb = TEAL
    accent.line.fill.background()
    add_text(slide, "OPERATING SYSTEMS PBL  /  CCSE0303A", 0.85, 0.72, 8, 0.3, 12, TEAL, bold=True)
    add_text(slide, "Smart Traffic Management System", 0.82, 1.55, 11.7, 0.75, 34, WHITE, bold=True)
    add_text(slide, "A typed OS simulation for resilient urban edge control", 0.86, 2.45, 10, 0.4, 18, MUTED)
    add_text(slide, "SDG 11  |  Sustainable Cities and Communities", 0.86, 3.12, 8, 0.35, 17, TEAL, bold=True)
    add_panel(slide, 0.85, 4.25, 5.35, 1.55, "PROJECT CREDENTIALS", [
        "Course: CCSE0303A",
        "Group: 02",
        "Platform: Python 3.11+ / POSIX concepts",
    ])
    add_panel(slide, 6.55, 4.25, 5.75, 1.55, "TEAM MEMBERS", [
        "[Member 1 - official name]  |  [ERP ID]",
        "[Member 2 - official name]  |  [ERP ID]",
        "[Member 3 - official name]  |  [ERP ID]",
        "[Member 4 / 5 - official name]  |  [ERP ID]",
    ])


def add_problem_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Urban Edge Contention & Scheduling Bottlenecks", "01 / motivation")
    add_bullets(slide, [
        "Traffic cameras, signal controllers, public transport, and emergency vehicles compete for finite CPU and memory.",
        "Naive scheduling creates emergency latency, fairness failures, context-switch overhead, and unpredictable actuation.",
        "Intersection zones are shared resources: incorrect acquisition can create circular waits and deadlock.",
        "The OS response is to make priority, safety, locality, and isolation explicit and measurable.",
    ], 0.85, 1.85, 7.0, 3.8)
    add_panel(slide, 8.25, 1.85, 4.1, 3.75, "DESIGN TARGETS", [
        "Emergency response",
        "Fair CPU service",
        "Deadlock avoidance",
        "Low-copy vision IPC",
        "Edge isolation",
    ])


def add_paradigm_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Operating System Paradigm Analysis", "02 / paradigm")
    headers = ["Paradigm", "Strength", "Traffic fit", "Decision"]
    rows = [
        ["Batch", "High throughput", "Poor emergency latency", "Baseline only"],
        ["SMP", "Parallel CPU execution", "Good for edge analytics", "Deployment target"],
        ["RTOS", "Bounded response", "Strong actuation model", "Design principle"],
        ["Prototype", "Observable simulation", "Reproducible OS behavior", "Implemented"],
    ]
    add_table(slide, headers, rows, 0.85, 1.75, 11.7, 3.2, [1.7, 3.0, 3.5, 2.4])
    add_text(slide, "The prototype borrows RTOS discipline while remaining a user-space Python simulation.", 0.9, 5.45, 11.5, 0.35, 15, TEAL)


def add_pcb_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Extended PCB Architecture & 5-State Lifecycle", "03 / process model")
    add_panel(slide, 0.8, 1.72, 5.35, 4.55, "EXTENDED PCB", [
        "PID / TGID / priority",
        "Arrival, burst, remaining, deadline metrics",
        "CPU affinity and switch counter",
        "RIP / RSP / CR3 / FLAGS register dictionary",
        "Priority-0 emergency interrupt path",
    ])
    states = ["NEW", "READY", "RUNNING", "WAITING", "TERMINATED"]
    for index, state in enumerate(states):
        x = 6.65 + (index % 2) * 2.8
        y = 1.9 + (index // 2) * 1.25
        add_chip(slide, state, x, y, TEAL if state == "RUNNING" else SLATE_LIGHT)
    add_text(slide, "Valid transitions are enforced; TERMINATED has no outgoing edge.", 6.7, 5.75, 5.5, 0.4, 14, MUTED)


def add_scheduling_matrix_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "CPU Scheduling Comparative Matrix", "04 / scheduling")
    headers = ["Algorithm", "Selection", "Preemptive", "Traffic behavior"]
    rows = [
        ["FCFS", "Earliest arrival", "No", "Simple, weak latency"],
        ["SJF", "Shortest burst", "No", "Good average wait"],
        ["SRTF", "Shortest remaining", "Yes", "Responsive, overhead"],
        ["Priority", "Lowest numeric priority", "Yes", "Emergency-first"],
        ["RR", "FIFO + q=2 ms", "Quantum", "Fair, switch-heavy"],
        ["3-Tier MLFQ", "Feedback + aging", "Queue policy", "Mixed workloads"],
    ]
    add_table(slide, headers, rows, 0.7, 1.65, 12.0, 4.7, [2.0, 3.1, 1.7, 4.0])


def add_scheduling_timeline_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Scheduling Timeline Analysis", "05 / evidence")
    image = ROOT / "output" / "traffic_gantt_chart.png"
    add_image_or_fallback(slide, image, 0.75, 1.65, 8.5, 4.9, "traffic_gantt_chart.png")
    add_panel(slide, 9.55, 1.75, 3.0, 3.7, "C_SW PROOF", [
        "C_sw = 0.2 ms",
        "Applied only when PID changes",
        "T_elapsed = T_run + N_sw C_sw",
        "Trace records execution intervals",
    ])


def add_lock_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Concurrency Architecture & Monotonic Lock Ordering", "06 / synchronization")
    for index, zone in enumerate(("Z1", "Z2", "Z3")):
        x = 1.0 + index * 3.75
        add_chip(slide, zone, x, 2.2, TEAL_DARK)
        if index < 2:
            add_text(slide, "→", x + 2.5, 2.22, 0.5, 0.4, 28, TEAL, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "Strict acquisition: Z1 < Z2 < Z3", 2.4, 3.55, 8.5, 0.5, 24, WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "A circular wait requires a descending edge. The monotonic hierarchy makes the wait-for graph acyclic.", 1.3, 4.55, 10.8, 0.6, 16, MUTED, align=PP_ALIGN.CENTER)


def add_pcp_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Priority Ceiling Protocol (PCP)", "07 / priority inversion")
    add_panel(slide, 0.85, 1.8, 5.2, 3.9, "WITHOUT PCP", [
        "Low-priority task holds intersection lock",
        "Ambulance waits for lock release",
        "Medium-priority tasks can delay the owner",
        "Unbounded priority inversion",
    ], color=RED)
    add_panel(slide, 6.75, 1.8, 5.2, 3.9, "WITH PCP", [
        "Resource ceiling = priority 1",
        "Owner inherits effective priority 1",
        "Medium tasks cannot extend the inversion",
        "Original priority restored on release",
    ], color=TEAL)


def add_banker_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Dijkstra's Banker for Dynamic Green Corridors", "08 / deadlock avoidance")
    add_text(slide, "Need = Max - Allocation", 0.9, 1.75, 5.4, 0.55, 25, TEAL, bold=True)
    add_bullets(slide, [
        "Compute Work = Available.",
        "Find a process with Need <= Work.",
        "Simulate completion and return its Allocation to Work.",
        "Grant requests only if all processes form a safe sequence.",
    ], 0.95, 2.65, 5.2, 2.7)
    add_panel(slide, 6.8, 1.8, 5.1, 3.9, "CORRIDOR DECISION", [
        "SAFE: request admitted",
        "UNSAFE: request denied",
        "Rollback: Available restored",
        "Rollback: Allocation restored",
    ])


def add_memory_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Virtual Memory & Page Replacement Benchmark", "09 / memory")
    image = ROOT / "output" / "memory_benchmark_chart.png"
    add_image_or_fallback(slide, image, 0.7, 1.62, 8.0, 4.95, "memory_benchmark_chart.png")
    add_panel(slide, 9.0, 1.8, 3.4, 3.7, "CAPACITY = 3", [
        "FIFO: 17 faults",
        "LRU: 18 faults",
        "LFU: 14 faults",
        "Optimal: 11 faults",
        "20-page reference stream",
    ])


def add_ipc_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Zero-Copy POSIX Shared Memory & CPU-Set Pinning", "10 / edge isolation")
    add_panel(slide, 0.8, 1.75, 5.45, 4.25, "CAMERA -> AI IPC", [
        "Producer maps raw shared byte buffer",
        "Frame length stored as shared metadata",
        "Consumer reads the same mapped payload",
        "No extra pipe/socket payload copy",
        "Linux namespace: typically /dev/shm",
    ])
    add_panel(slide, 6.85, 1.75, 5.45, 4.25, "DOCKER EDGE ISOLATION", [
        "Signal controller -> Core 0",
        "Camera ingest -> Core 1",
        "Vision workers -> Cores 2-3",
        "Telemetry -> best-effort service",
        "cgroups bound CPU and memory",
    ])


def add_conclusion_slide(presentation: Presentation) -> None:
    slide = new_slide(presentation, "Conclusion, Urban Impact & Future Scope", "11 / close")
    add_bullets(slide, [
        "The prototype connects PCB state, scheduling, synchronization, memory, and telemetry into one reproducible OS simulation.",
        "Emergency-first response, safe corridor allocation, and isolated edge workloads support SDG 11 resilience goals.",
        "Future scope: measured Linux RT scheduling, live camera ring buffers, formal property tests, and edge-device deployment.",
    ], 0.85, 1.85, 7.0, 3.7)
    add_panel(slide, 8.35, 1.8, 4.0, 3.7, "REFERENCES", [
        "Dijkstra: Banker's Algorithm",
        "POSIX shared memory and scheduling",
        "Linux cgroups and cpuset",
        "UN SDG 11 framework",
        "Repository: smart_traffic_os",
    ])
    add_text(slide, "Thank you  |  Questions?", 0.9, 6.0, 11.5, 0.5, 24, TEAL, bold=True, align=PP_ALIGN.CENTER)


def add_text(
    slide: object,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: int,
    color: RGBColor,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    """Add a styled text box."""
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.margin_left = Inches(0.03)
    frame.margin_right = Inches(0.03)
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.name = "Aptos"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def add_bullets(slide: object, items: Iterable[str], x: float, y: float, width: float, height: float) -> None:
    """Add a compact list of white bullet text."""
    shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    for index, item in enumerate(items):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = item
        paragraph.level = 0
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(16)
        paragraph.font.color.rgb = WHITE
        paragraph.space_after = Pt(11)
        paragraph.bullet = True


def add_panel(
    slide: object,
    x: float,
    y: float,
    width: float,
    height: float,
    heading: str,
    lines: Iterable[str],
    color: RGBColor = TEAL,
) -> None:
    """Add a dark panel with an accent heading and compact content."""
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(width), Inches(height))
    panel.fill.solid()
    panel.fill.fore_color.rgb = SLATE_LIGHT
    panel.line.color.rgb = color
    panel.line.width = Pt(1.2)
    add_text(slide, heading, x + 0.22, y + 0.18, width - 0.44, 0.28, 11, color, bold=True)
    add_bullets(slide, lines, x + 0.25, y + 0.58, width - 0.5, height - 0.7)


def add_chip(slide: object, label: str, x: float, y: float, color: RGBColor) -> None:
    """Add a compact lifecycle or zone chip."""
    chip = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(2.1), Inches(0.65))
    chip.fill.solid()
    chip.fill.fore_color.rgb = color
    chip.line.color.rgb = TEAL
    add_text(slide, label, x, y + 0.06, 2.1, 0.5, 17, WHITE, bold=True, align=PP_ALIGN.CENTER)


def add_table(
    slide: object,
    headers: list[str],
    rows: list[list[str]],
    x: float,
    y: float,
    width: float,
    height: float,
    column_widths: list[float],
) -> None:
    """Add a readable dark-themed table."""
    table_shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x), Inches(y), Inches(width), Inches(height))
    table = table_shape.table
    for index, column_width in enumerate(column_widths):
        table.columns[index].width = Inches(column_width)
    for row_index, values in enumerate([headers, *rows]):
        for column_index, value in enumerate(values):
            cell = table.cell(row_index, column_index)
            cell.text = value
            cell.fill.solid()
            cell.fill.fore_color.rgb = TEAL_DARK if row_index == 0 else SLATE_LIGHT
            cell.margin_left = Inches(0.08)
            cell.margin_right = Inches(0.08)
            cell.margin_top = Inches(0.04)
            cell.margin_bottom = Inches(0.04)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.name = "Aptos"
                paragraph.font.size = Pt(11 if row_index else 12)
                paragraph.font.bold = row_index == 0
                paragraph.font.color.rgb = WHITE
                paragraph.alignment = PP_ALIGN.LEFT


def add_image_or_fallback(
    slide: object,
    image_path: Path,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
) -> None:
    """Embed an existing image or render a clear placeholder panel."""
    if image_path.is_file():
        slide.shapes.add_picture(str(image_path), Inches(x), Inches(y), width=Inches(width), height=Inches(height))
        return
    add_panel(slide, x, y, width, height, "IMAGE UNAVAILABLE", [
        f"Expected artifact: {label}",
        "Run python3 run_master.py",
        "The deck remains valid and editable.",
    ], color=AMBER)


if __name__ == "__main__":
    main()
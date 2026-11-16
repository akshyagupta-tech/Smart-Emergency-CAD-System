"""Capture Linux sched_switch events or emit a clearly marked mock trace.

The sched_switch tracepoint exposes the scheduling decision and timestamp, but
not the hardware register-switch latency. This tool reports observed task run
intervals and per-CPU switch-interval jitter instead of mislabeling either as
hardware switch duration.
"""

from __future__ import annotations

import argparse
import ctypes
import platform
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "logs" / "kernel_sched_switch.log"
TRACEFS_PATHS = (Path("/sys/kernel/tracing"), Path("/sys/kernel/debug/tracing"))

SWITCH_PATTERN = re.compile(
    r"\[(?P<cpu>\s*\d+)\].*?\s(?P<timestamp>\d+\.\d+):\s+"
    r"sched_switch:\s+prev_comm=(?P<prev_comm>.*?)\s+"
    r"prev_pid=(?P<prev_pid>\d+)\s+prev_prio=-?\d+\s+"
    r"prev_state=(?P<prev_state>.*?)\s+==>\s+"
    r"next_comm=(?P<next_comm>.*?)\s+next_pid=(?P<next_pid>\d+)"
)


@dataclass(frozen=True, slots=True)
class SwitchEvent:
    timestamp_ns: int
    cpu: int
    prev_pid: int
    prev_comm: str
    prev_state: str
    next_pid: int
    next_comm: str
    source: str
    transition_duration_ns: int | None = None


class SwitchMetrics:
    """Derive task run intervals and switch-interval jitter from event times."""

    def __init__(self) -> None:
        self.running_since: dict[int, int] = {}
        self.last_switch: dict[int, int] = {}
        self.intervals: dict[int, deque[int]] = defaultdict(
            lambda: deque(maxlen=128)
        )
        self.transition_durations: deque[int] = deque(maxlen=128)

    def observe(
        self, event: SwitchEvent
    ) -> tuple[int | None, int | None, int | None]:
        run_duration = None
        if event.prev_pid in self.running_since:
            run_duration = event.timestamp_ns - self.running_since.pop(event.prev_pid)

        switch_interval = None
        jitter = None
        if event.cpu in self.last_switch:
            switch_interval = event.timestamp_ns - self.last_switch[event.cpu]
            history = self.intervals[event.cpu]
            if history:
                jitter = abs(switch_interval - int(median(history)))
            else:
                jitter = 0
            history.append(switch_interval)

        self.last_switch[event.cpu] = event.timestamp_ns
        self.running_since[event.next_pid] = event.timestamp_ns
        transition_jitter = None
        if event.transition_duration_ns is not None:
            if self.transition_durations:
                transition_jitter = abs(
                    event.transition_duration_ns
                    - int(median(self.transition_durations))
                )
            else:
                transition_jitter = 0
            self.transition_durations.append(event.transition_duration_ns)
        return run_duration, jitter, transition_jitter


def parse_trace_line(line: str) -> SwitchEvent | None:
    """Parse one trace_pipe sched_switch line, ignoring unrelated events."""
    match = SWITCH_PATTERN.search(line)
    if match is None:
        return None
    fields = match.groupdict()
    return SwitchEvent(
        timestamp_ns=_timestamp_to_ns(fields["timestamp"]),
        cpu=int(fields["cpu"]),
        prev_pid=int(fields["prev_pid"]),
        prev_comm=fields["prev_comm"],
        prev_state=fields["prev_state"],
        next_pid=int(fields["next_pid"]),
        next_comm=fields["next_comm"],
        source="tracefs",
    )


def _timestamp_to_ns(timestamp: str) -> int:
    seconds, fraction = timestamp.split(".", maxsplit=1)
    return int(seconds) * 1_000_000_000 + int(fraction[:9].ljust(9, "0"))


def _format_event(
    event: SwitchEvent,
    metrics: SwitchMetrics,
) -> str:
    run_duration, jitter, transition_jitter = metrics.observe(event)
    run_value = "n/a" if run_duration is None else str(run_duration)
    jitter_value = "n/a" if jitter is None else str(jitter)
    transition_value = (
        "n/a"
        if event.transition_duration_ns is None
        else str(event.transition_duration_ns)
    )
    transition_jitter_value = (
        "n/a" if transition_jitter is None else str(transition_jitter)
    )
    timestamp = f"{event.timestamp_ns / 1_000_000_000:.9f}"
    return (
        f"source={event.source} timestamp={timestamp} cpu={event.cpu} "
        f"prev_pid={event.prev_pid} prev_comm={event.prev_comm!r} "
        f"prev_state={event.prev_state!r} next_pid={event.next_pid} "
        f"next_comm={event.next_comm!r} prev_run_duration_ns={run_value} "
        f"switch_interval_jitter_ns={jitter_value} "
        f"scheduler_transition_duration_ns={transition_value} "
        f"scheduler_transition_jitter_ns={transition_jitter_value}"
    )


def _tracefs_root() -> Path:
    for path in TRACEFS_PATHS:
        if (path / "trace_pipe").is_file() and (
            path / "events/sched/sched_switch/enable"
        ).is_file():
            return path
    raise FileNotFoundError(
        "sched_switch tracefs event is unavailable. Mount tracefs and run with "
        "permission to read trace_pipe and enable the event."
    )


class TraceFSProbe:
    """Enable sched_switch in tracefs while restoring prior settings on exit."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.event_enable = root / "events/sched/sched_switch/enable"
        self.tracing_on = root / "tracing_on"
        self.old_event_state = self.event_enable.read_text(encoding="ascii").strip()
        self.old_tracing_state = self.tracing_on.read_text(encoding="ascii").strip()

    def __enter__(self) -> None:
        try:
            if self.old_event_state != "1":
                self.event_enable.write_text("1", encoding="ascii")
            if self.old_tracing_state != "1":
                self.tracing_on.write_text("1", encoding="ascii")
        except Exception:
            self._restore()
            raise

    def __exit__(self, *_: object) -> None:
        self._restore()

    def _restore(self) -> None:
        if self.old_event_state != "1":
            self.event_enable.write_text(self.old_event_state, encoding="ascii")
        if self.old_tracing_state != "1":
            self.tracing_on.write_text(self.old_tracing_state, encoding="ascii")


def _write_header(log_file: TextIO, mode: str) -> None:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_file.write(f"\n# kernel sched_switch trace mode={mode} started={started}\n")
    log_file.write(
        "# prev_run_duration_ns is observed task residency; "
        "switch_interval_jitter_ns is per-CPU inter-event variation, "
        "not hardware register-switch latency. BCC transition duration is "
        "sched_switch-to-finish_task_switch time, not hardware-only latency.\n"
    )
    log_file.flush()


def trace_kernel(log_file: TextIO) -> None:
    root = _tracefs_root()
    metrics = SwitchMetrics()
    with TraceFSProbe(root):
        with (root / "trace_pipe").open(
            "r", encoding="ascii", errors="replace"
        ) as trace_pipe:
            _write_header(log_file, f"tracefs:{root}")
            print(f"Reading sched_switch from {root / 'trace_pipe'}; press Ctrl-C to stop.")
            for line in trace_pipe:
                event = parse_trace_line(line)
                if event is None:
                    continue
                record = _format_event(event, metrics)
                log_file.write(record + "\n")
                log_file.flush()
                print(record)


BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#define TASK_COMM_LEN 16

struct switch_event_t {
    u64 timestamp_ns;
    u64 transition_duration_ns;
    u32 cpu;
    u32 prev_pid;
    char prev_comm[TASK_COMM_LEN];
    u64 prev_state;
    u32 next_pid;
    char next_comm[TASK_COMM_LEN];
};

BPF_PERCPU_ARRAY(pending_switch, struct switch_event_t, 1);
BPF_PERF_OUTPUT(events);

TRACEPOINT_PROBE(sched, sched_switch) {
    u32 key = 0;
    struct switch_event_t *event = pending_switch.lookup(&key);
    if (!event) {
        return 0;
    }
    event->timestamp_ns = bpf_ktime_get_ns();
    event->cpu = bpf_get_smp_processor_id();
    event->prev_pid = args->prev_pid;
    __builtin_memcpy(event->prev_comm, args->prev_comm, TASK_COMM_LEN);
    event->prev_state = args->prev_state;
    event->next_pid = args->next_pid;
    __builtin_memcpy(event->next_comm, args->next_comm, TASK_COMM_LEN);
    return 0;
}

int trace_finish_task_switch(struct pt_regs *ctx) {
    u32 key = 0;
    struct switch_event_t *event = pending_switch.lookup(&key);
    if (!event || !event->timestamp_ns) {
        return 0;
    }
    event->transition_duration_ns = bpf_ktime_get_ns() - event->timestamp_ns;
    events.perf_submit(ctx, event, sizeof(*event));
    event->timestamp_ns = 0;
    return 0;
}
"""


class BccSwitchEvent(ctypes.Structure):
    _fields_ = [
        ("timestamp_ns", ctypes.c_uint64),
        ("transition_duration_ns", ctypes.c_uint64),
        ("cpu", ctypes.c_uint32),
        ("prev_pid", ctypes.c_uint32),
        ("prev_comm", ctypes.c_char * 16),
        ("prev_state", ctypes.c_uint64),
        ("next_pid", ctypes.c_uint32),
        ("next_comm", ctypes.c_char * 16),
    ]


def _task_state_name(state: int) -> str:
    """Render common Linux task-state bitmasks like trace_pipe does."""
    state_names = {
        0: "R",
        1: "S",
        2: "D",
        4: "T",
        8: "t",
        16: "X",
        32: "Z",
        64: "P",
        1026: "I",
    }
    return state_names.get(state, f"0x{state:x}")


def _attach_bcc_probe(bpf_type: object) -> object:
    bpf = bpf_type(text=BPF_PROGRAM)
    bpf.attach_kprobe(event="finish_task_switch", fn_name="trace_finish_task_switch")
    return bpf


def trace_bcc(bpf: object, log_file: TextIO) -> None:
    metrics = SwitchMetrics()
    _write_header(log_file, "bcc sched_switch + finish_task_switch probe")
    print("Reading BCC scheduler events; press Ctrl-C to stop.")

    def handle_event(_cpu: int, data: int, _size: int) -> None:
        raw = ctypes.cast(data, ctypes.POINTER(BccSwitchEvent)).contents
        event = SwitchEvent(
            timestamp_ns=raw.timestamp_ns,
            cpu=raw.cpu,
            prev_pid=raw.prev_pid,
            prev_comm=raw.prev_comm.decode("utf-8", errors="replace").rstrip("\0"),
            prev_state=_task_state_name(raw.prev_state),
            next_pid=raw.next_pid,
            next_comm=raw.next_comm.decode("utf-8", errors="replace").rstrip("\0"),
            source="bcc",
            transition_duration_ns=raw.transition_duration_ns,
        )
        record = _format_event(event, metrics)
        log_file.write(record + "\n")
        log_file.flush()
        print(record)

    bpf["events"].open_perf_buffer(handle_event, page_cnt=64)
    while True:
        bpf.perf_buffer_poll()


def trace_linux(log_file: TextIO) -> None:
    try:
        from bcc import BPF
    except ImportError:
        trace_kernel(log_file)
        return

    try:
        bpf = _attach_bcc_probe(BPF)
    except Exception as error:
        print(f"BCC probe unavailable ({error}); falling back to tracefs.", file=sys.stderr)
        trace_kernel(log_file)
        return
    trace_bcc(bpf, log_file)


def mock_events(count: int) -> list[SwitchEvent]:
    """Generate deterministic scheduler-like events for non-Linux testing."""
    if count <= 0:
        raise ValueError("mock event count must be positive")
    tasks = [(101, "ambulance"), (202, "signal_worker"), (303, "camera_ai")]
    run_intervals = (1_000_000, 1_200_000, 950_000, 1_050_000)
    timestamp_ns = 1_000_000_000
    events: list[SwitchEvent] = []
    previous = (0, "swapper")
    for index in range(count):
        next_task = tasks[index % len(tasks)]
        if index:
            timestamp_ns += run_intervals[(index - 1) % len(run_intervals)]
        events.append(
            SwitchEvent(
                timestamp_ns=timestamp_ns,
                cpu=0,
                prev_pid=previous[0],
                prev_comm=previous[1],
                prev_state="R" if index % 2 == 0 else "S",
                next_pid=next_task[0],
                next_comm=next_task[1],
                source="mock",
                transition_duration_ns=(8_000 + (index % 3) * 750),
            )
        )
        previous = next_task
    return events


def trace_mock(log_file: TextIO, count: int) -> None:
    metrics = SwitchMetrics()
    _write_header(log_file, "mock (synthetic; not kernel measurements)")
    for event in mock_events(count):
        record = _format_event(event, metrics)
        log_file.write(record + "\n")
        log_file.flush()
        print(record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="write deterministic synthetic events instead of reading the kernel",
    )
    parser.add_argument(
        "--events",
        type=int,
        default=12,
        help="number of events to generate in mock mode (default: 12)",
    )
    args = parser.parse_args(argv)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            if args.mock or platform.system() != "Linux":
                trace_mock(log_file, args.events)
            else:
                trace_linux(log_file)
    except KeyboardInterrupt:
        print("\nTrace stopped.")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Tracing failed: {error}", file=sys.stderr)
        return 1

    print(f"Trace written to {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
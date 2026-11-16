"""Typed process-control-block lifecycle and interrupt management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import ClassVar, Mapping


class ProcessState(Enum):
    """Five-state lifecycle model used by the process simulator."""

    NEW = auto()
    READY = auto()
    RUNNING = auto()
    WAITING = auto()
    TERMINATED = auto()


@dataclass(slots=True)
class RegisterContext:
    """Compatibility helper for constructing a register dictionary."""

    RIP: int = 0
    RSP: int = 0
    CR3: int = 0
    FLAGS: int = 0

    def as_dict(self) -> dict[str, int]:
        """Return the register context in the PCB's canonical format."""
        return {
            "RIP": self.RIP,
            "RSP": self.RSP,
            "CR3": self.CR3,
            "FLAGS": self.FLAGS,
        }


@dataclass(slots=True)
class ExtendedPCB:
    """OS process-control block with scheduling and context state."""

    EMERGENCY_PRIORITY: ClassVar[int] = 0
    REGISTER_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"RIP", "RSP", "CR3", "FLAGS"}
    )

    pid: str
    tgid: int
    state: ProcessState = ProcessState.NEW
    priority: int = 0
    burst_time: float = 0.0
    remaining_time: float | None = None
    arrival_time: float = 0.0
    completion_time: float = 0.0
    waiting_time: float = 0.0
    turnaround_time: float = 0.0
    total_switches: int = 0
    cpu_affinity: int = 0
    registers: dict[str, int] = field(default_factory=lambda: {
        "RIP": 0,
        "RSP": 0,
        "CR3": 0,
        "FLAGS": 0,
    })

    def __post_init__(self) -> None:
        """Validate process metadata and initialize derived runtime fields."""
        if not isinstance(self.pid, str) or not self.pid:
            raise ValueError("pid must be a non-empty string")
        if self.tgid < 0:
            raise ValueError("tgid must be non-negative")
        if self.priority < 0:
            raise ValueError("priority must be non-negative")
        if self.burst_time < 0 or self.arrival_time < 0:
            raise ValueError("burst_time and arrival_time must be non-negative")
        if self.remaining_time is None:
            self.remaining_time = self.burst_time
        if not 0 <= self.remaining_time <= self.burst_time:
            raise ValueError("remaining_time must be between zero and burst_time")
        if self.completion_time < 0 or self.waiting_time < 0 or self.turnaround_time < 0:
            raise ValueError("execution metrics must be non-negative")
        if self.total_switches < 0 or self.cpu_affinity < 0:
            raise ValueError("switch count and CPU affinity must be non-negative")
        if isinstance(self.registers, RegisterContext):
            self.registers = self.registers.as_dict()
        self._validate_registers(self.registers)

    @classmethod
    def _validate_registers(cls, registers: Mapping[str, int]) -> None:
        if set(registers) != cls.REGISTER_NAMES:
            raise ValueError("registers must contain exactly RIP, RSP, CR3, and FLAGS")
        if any(not isinstance(value, int) or value < 0 for value in registers.values()):
            raise ValueError("register values must be non-negative integers")

    def transition_state(self, new_state: ProcessState) -> None:
        """Validate and apply a process lifecycle transition."""
        valid_transitions = {
            ProcessState.NEW: {ProcessState.READY, ProcessState.TERMINATED},
            ProcessState.READY: {
                ProcessState.RUNNING,
                ProcessState.WAITING,
                ProcessState.TERMINATED,
            },
            ProcessState.RUNNING: {
                ProcessState.READY,
                ProcessState.WAITING,
                ProcessState.TERMINATED,
            },
            ProcessState.WAITING: {ProcessState.READY, ProcessState.TERMINATED},
            ProcessState.TERMINATED: set(),
        }
        if new_state not in valid_transitions[self.state]:
            raise ValueError(
                f"invalid process transition: {self.state.name} -> {new_state.name}"
            )
        self.state = new_state

    def dump_registers(self, log_path: str) -> None:
        """Append a low-level hexadecimal register dump to ``log_path``."""
        self._validate_registers(self.registers)
        path = Path(log_path)
        with path.open("a", encoding="ascii") as log_file:
            log_file.write(f"PID={self.pid} TGID={self.tgid} CONTEXT_SWITCH\n")
            for name in ("RIP", "RSP", "CR3", "FLAGS"):
                log_file.write(f"{name}=0x{self.registers[name]:016x}\n")

    def trigger_interrupt(self, interrupt_type: str) -> bool:
        """Preempt a running process for an emergency priority-0 interrupt."""
        if not isinstance(interrupt_type, str) or not interrupt_type.strip():
            raise ValueError("interrupt_type must be a non-empty string")
        normalized = interrupt_type.strip().upper().replace("-", "_").replace(" ", "_")
        emergency_types = {
            "EMERGENCY",
            "EMERGENCY_PREEMPTION",
            "PRIORITY_0",
            "PRIORITY_0_EMERGENCY",
        }
        if normalized not in emergency_types or self.state is not ProcessState.RUNNING:
            return False
        self.transition_state(ProcessState.READY)
        self.total_switches += 1
        return True

    def interrupt_handler(self, event_priority: int) -> bool:
        """Compatibility adapter for numeric emergency interrupt priorities."""
        if event_priority < 0:
            raise ValueError("event priority must be non-negative")
        return self.trigger_interrupt(f"PRIORITY_{event_priority}")

    @property
    def burst(self) -> float:
        """Compatibility alias for ``burst_time``."""
        return self.burst_time

    @burst.setter
    def burst(self, value: float) -> None:
        self.burst_time = value

    @property
    def remaining(self) -> float:
        """Compatibility alias for ``remaining_time``."""
        return self.remaining_time or 0.0

    @remaining.setter
    def remaining(self, value: float) -> None:
        self.remaining_time = value

    @property
    def arrival(self) -> float:
        """Compatibility alias for ``arrival_time``."""
        return self.arrival_time

    @arrival.setter
    def arrival(self, value: float) -> None:
        self.arrival_time = value


class PCBManager:
    """Own process registration and single-CPU interrupt dispatch."""

    def __init__(self) -> None:
        self._processes: dict[str, ExtendedPCB] = {}

    @property
    def processes(self) -> tuple[ExtendedPCB, ...]:
        """Return registered PCBs in PID order."""
        return tuple(self._processes[pid] for pid in sorted(self._processes))

    @property
    def running_process(self) -> ExtendedPCB | None:
        """Return the sole running process, if one exists."""
        running = [
            process
            for process in self._processes.values()
            if process.state is ProcessState.RUNNING
        ]
        if len(running) > 1:
            raise RuntimeError("multiple running processes on a single simulated CPU")
        return running[0] if running else None

    def register(self, process: ExtendedPCB) -> None:
        """Register a PCB by PID, rejecting duplicates."""
        if process.pid in self._processes:
            raise ValueError(f"PID {process.pid} is already registered")
        self._processes[process.pid] = process

    def get(self, pid: str) -> ExtendedPCB:
        """Return a registered PCB or raise ``KeyError``."""
        return self._processes[pid]

    def dispatch_emergency_interrupt(self, event_priority: int) -> bool:
        """Dispatch a numeric interrupt to the running process."""
        process = self.running_process
        return process.interrupt_handler(event_priority) if process else False


MockRegisters = RegisterContext

__all__ = [
    "ExtendedPCB",
    "MockRegisters",
    "PCBManager",
    "ProcessState",
    "RegisterContext",
]

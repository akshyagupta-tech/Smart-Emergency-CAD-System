"""Backward-compatible imports for the process-control-block API."""

from core.pcb_manager import (
    ExtendedPCB,
    MockRegisters,
    PCBManager,
    ProcessState,
    RegisterContext,
)

__all__ = [
    "ExtendedPCB",
    "MockRegisters",
    "PCBManager",
    "ProcessState",
    "RegisterContext",
]
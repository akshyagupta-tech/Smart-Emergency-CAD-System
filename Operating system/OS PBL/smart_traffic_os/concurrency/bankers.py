"""Dijkstra's Banker's algorithm for deadlock avoidance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

ProcessId: TypeAlias = int
ResourceVector: TypeAlias = list[int]
ResourceMatrix: TypeAlias = dict[ProcessId, ResourceVector]


class BankersAlgorithm:
    """Track resources and grant requests only when the state stays safe.

    ``max_matrix`` and ``allocation_matrix`` are keyed by process ID. Resource
    vectors use one position per resource type, and ``available`` contains the
    currently unallocated instances of each type.
    """

    def __init__(
        self,
        processes: Sequence[ProcessId],
        available: Sequence[int],
        max_matrix: Mapping[ProcessId, Sequence[int]],
        allocation_matrix: Mapping[ProcessId, Sequence[int]],
    ) -> None:
        self.processes = list(processes)
        self._validate_processes()
        self.resource_count = len(available)
        self.available = self._copy_vector(available, "available")
        self.max_matrix = self._copy_matrix(max_matrix, "max_matrix")
        self.allocation_matrix = self._copy_matrix(
            allocation_matrix, "allocation_matrix"
        )
        self._validate_state()

    @property
    def need_matrix(self) -> ResourceMatrix:
        """Return the remaining maximum resource need for every process."""
        return {
            pid: [
                maximum - allocated
                for maximum, allocated in zip(
                    self.max_matrix[pid], self.allocation_matrix[pid]
                )
            ]
            for pid in self.processes
        }

    def safe_sequence(self) -> list[ProcessId] | None:
        """Return a safe completion order, or ``None`` if the state is unsafe."""
        return self._find_safe_sequence(
            self.available, self.allocation_matrix, self.need_matrix
        )

    def is_safe(self) -> bool:
        """Return whether all processes can complete without deadlock."""
        return self.safe_sequence() is not None

    def request_corridor(
        self, pid: ProcessId, request_vector: Sequence[int]
    ) -> bool:
        """Grant a request only if it passes all three Banker checks.

        The request must be no greater than the process's remaining need and
        the currently available resources. The tentative allocation is then
        checked for a safe sequence. Unsafe requests are rolled back before
        returning ``False``.
        """
        if pid not in self.processes:
            return False
        request = self._copy_vector(request_vector, "request_vector")
        if any(value > need for value, need in zip(request, self.need_matrix[pid])):
            return False
        if any(value > available for value, available in zip(request, self.available)):
            return False

        original_available = self.available.copy()
        original_allocation = self.allocation_matrix[pid].copy()
        try:
            self.available = [
                available - value
                for available, value in zip(self.available, request)
            ]
            self.allocation_matrix[pid] = [
                allocated + value
                for allocated, value in zip(original_allocation, request)
            ]
            if self.is_safe():
                return True
        finally:
            if not self.is_safe():
                self.available = original_available
                self.allocation_matrix[pid] = original_allocation
        return False

    def _find_safe_sequence(
        self,
        available: Sequence[int],
        allocation_matrix: Mapping[ProcessId, Sequence[int]],
        need_matrix: Mapping[ProcessId, Sequence[int]],
    ) -> list[ProcessId] | None:
        work = list(available)
        unfinished = set(self.processes)
        sequence: list[ProcessId] = []

        while unfinished:
            progress = False
            for pid in self.processes:
                if pid not in unfinished:
                    continue
                if all(need <= free for need, free in zip(need_matrix[pid], work)):
                    work = [
                        free + allocated
                        for free, allocated in zip(work, allocation_matrix[pid])
                    ]
                    unfinished.remove(pid)
                    sequence.append(pid)
                    progress = True
            if not progress:
                return None
        return sequence

    def _validate_processes(self) -> None:
        if not self.processes:
            raise ValueError("at least one process is required")
        if len(set(self.processes)) != len(self.processes):
            raise ValueError("process IDs must be unique")

    def _copy_vector(self, vector: Sequence[int], name: str) -> ResourceVector:
        values = list(vector)
        if len(values) != self.resource_count and name != "available":
            raise ValueError(f"{name} must contain {self.resource_count} resources")
        if any(value < 0 for value in values):
            raise ValueError(f"{name} must contain non-negative values")
        return values

    def _copy_matrix(
        self,
        matrix: Mapping[ProcessId, Sequence[int]],
        name: str,
    ) -> ResourceMatrix:
        if set(matrix) != set(self.processes):
            raise ValueError(f"{name} must contain exactly the configured processes")
        return {
            pid: self._copy_vector(values, name)
            for pid, values in matrix.items()
        }

    def _validate_state(self) -> None:
        for pid in self.processes:
            if any(
                allocated > maximum
                for allocated, maximum in zip(
                    self.allocation_matrix[pid], self.max_matrix[pid]
                )
            ):
                raise ValueError(f"allocation for process {pid} exceeds its maximum")
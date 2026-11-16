"""Comparative page-replacement simulations."""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Sequence
from typing import Callable, TypeAlias

Page = int
Metrics: TypeAlias = dict[str, float | int]
Comparison: TypeAlias = dict[str, Metrics]
Policy: TypeAlias = Callable[[Sequence[Page], int], Metrics]


def fifo(reference_string: Sequence[Page], capacity: int) -> Metrics:
    """Simulate first-in, first-out page replacement."""
    frames: set[Page] = set()
    order: deque[Page] = deque()
    faults = 0

    for page in reference_string:
        if page in frames:
            continue
        faults += 1
        if len(frames) == capacity:
            frames.remove(order.popleft())
        frames.add(page)
        order.append(page)

    return _metrics(faults, len(reference_string))


def lru(reference_string: Sequence[Page], capacity: int) -> Metrics:
    """Simulate least recently used page replacement."""
    frames: OrderedDict[Page, None] = OrderedDict()
    faults = 0

    for page in reference_string:
        if page in frames:
            frames.move_to_end(page)
            continue
        faults += 1
        if len(frames) == capacity:
            frames.popitem(last=False)
        frames[page] = None

    return _metrics(faults, len(reference_string))


def lfu(reference_string: Sequence[Page], capacity: int) -> Metrics:
    """Simulate least frequently used replacement.

    Frequency ties are resolved by least recent use for deterministic output.
    """
    frequency: dict[Page, int] = {}
    last_used: dict[Page, int] = {}
    faults = 0

    for timestamp, page in enumerate(reference_string):
        if page in frequency:
            frequency[page] += 1
            last_used[page] = timestamp
            continue
        faults += 1
        if len(frequency) == capacity:
            victim = min(
                frequency,
                key=lambda candidate: (
                    frequency[candidate],
                    last_used[candidate],
                ),
            )
            del frequency[victim]
            del last_used[victim]
        frequency[page] = 1
        last_used[page] = timestamp

    return _metrics(faults, len(reference_string))


def optimal(reference_string: Sequence[Page], capacity: int) -> Metrics:
    """Simulate the optimal replacement policy using future references."""
    frames: list[Page] = []
    faults = 0

    for index, page in enumerate(reference_string):
        if page in frames:
            continue
        faults += 1
        if len(frames) == capacity:
            victim_index = max(
                range(len(frames)),
                key=lambda frame_index: _next_use(
                    reference_string, index + 1, frames[frame_index]
                ),
            )
            frames.pop(victim_index)
        frames.append(page)

    return _metrics(faults, len(reference_string))


def compare_page_replacement(
    reference_string: Sequence[Page], capacity: int
) -> Comparison:
    """Run FIFO, LRU, LFU, and Optimal for the same input."""
    _validate_input(reference_string, capacity)
    policies: dict[str, Policy] = {
        "FIFO": fifo,
        "LRU": lru,
        "LFU": lfu,
        "Optimal": optimal,
    }
    return {
        name: policy(reference_string, capacity)
        for name, policy in policies.items()
    }


def detect_belady_anomaly(
    reference_string: Sequence[Page], frame_sizes: Sequence[int]
) -> bool:
    """Return whether FIFO has more faults with a larger frame size.

    ``frame_sizes`` must be strictly increasing. The anomaly is present when
    any adjacent larger frame size produces more FIFO faults than the prior
    size.
    """
    _validate_reference_string(reference_string)
    sizes = list(frame_sizes)
    if len(sizes) < 2 or any(size <= 0 for size in sizes):
        raise ValueError("frame_sizes must contain at least two positive sizes")
    if any(left >= right for left, right in zip(sizes, sizes[1:])):
        raise ValueError("frame_sizes must be strictly increasing")

    faults = [int(fifo(reference_string, size)["page_faults"]) for size in sizes]
    return any(left < right for left, right in zip(faults, faults[1:]))


def _metrics(faults: int, references: int) -> Metrics:
    return {
        "page_faults": faults,
        "page_hits": references - faults,
        "fault_ratio": faults / references if references else 0.0,
    }


def _next_use(
    reference_string: Sequence[Page], start: int, page: Page
) -> int:
    try:
        return reference_string.index(page, start)
    except ValueError:
        return len(reference_string) + 1


def _validate_input(reference_string: Sequence[Page], capacity: int) -> None:
    _validate_reference_string(reference_string)
    if capacity <= 0:
        raise ValueError("capacity must be positive")


def _validate_reference_string(reference_string: Sequence[Page]) -> None:
    if any(not isinstance(page, int) for page in reference_string):
        raise TypeError("reference_string must contain only integers")
"""Virtual-memory page replacement and zero-copy frame transport."""

from __future__ import annotations

import multiprocessing
import struct
from collections import OrderedDict, deque
from collections.abc import Iterable
from multiprocessing import shared_memory
from typing import TypeAlias

PageResult: TypeAlias = tuple[int, int, float]
Frame = bytes | bytearray | memoryview

_FRAME_LENGTH = struct.Struct("!Q")


def simulate_fifo(pages: list[int], capacity: int) -> PageResult:
    """Simulate first-in, first-out page replacement."""
    _validate_pages(pages, capacity)
    frames: set[int] = set()
    order: deque[int] = deque()
    faults = 0
    for page in pages:
        if page in frames:
            continue
        faults += 1
        if len(frames) == capacity:
            frames.remove(order.popleft())
        frames.add(page)
        order.append(page)
    return _result(faults, len(pages))


def simulate_lru(pages: list[int], capacity: int) -> PageResult:
    """Simulate least recently used page replacement."""
    _validate_pages(pages, capacity)
    frames: OrderedDict[int, None] = OrderedDict()
    faults = 0
    for page in pages:
        if page in frames:
            frames.move_to_end(page)
            continue
        faults += 1
        if len(frames) == capacity:
            frames.popitem(last=False)
        frames[page] = None
    return _result(faults, len(pages))


def simulate_lfu(pages: list[int], capacity: int) -> PageResult:
    """Simulate LFU replacement with FIFO tie-breaking."""
    _validate_pages(pages, capacity)
    frequency: dict[int, int] = {}
    loaded_at: dict[int, int] = {}
    faults = 0
    load_sequence = 0
    for page in pages:
        if page in frequency:
            frequency[page] += 1
            continue
        faults += 1
        if len(frequency) == capacity:
            victim = min(
                frequency,
                key=lambda candidate: (frequency[candidate], loaded_at[candidate]),
            )
            del frequency[victim]
            del loaded_at[victim]
        frequency[page] = 1
        loaded_at[page] = load_sequence
        load_sequence += 1
    return _result(faults, len(pages))


def simulate_optimal(pages: list[int], capacity: int) -> PageResult:
    """Simulate optimal replacement using the farthest future reference."""
    _validate_pages(pages, capacity)
    frames: list[int] = []
    faults = 0
    for index, page in enumerate(pages):
        if page in frames:
            continue
        faults += 1
        if len(frames) == capacity:
            victim = max(
                range(len(frames)),
                key=lambda frame_index: _next_use(pages, index + 1, frames[frame_index]),
            )
            frames.pop(victim)
        frames.append(page)
    return _result(faults, len(pages))


class ZeroCopySharedMemory:
    """Shared raw-frame buffer for camera producer and AI consumer processes.

    The operating system creates POSIX shared-memory objects in its shared
    memory namespace (typically ``/dev/shm`` on Linux). The first eight bytes
    store the current frame length; frame payloads are written directly into
    the shared buffer and are not copied through a pipe or socket.
    """

    def __init__(self, capacity: int, name: str | None = None) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._size = _FRAME_LENGTH.size + capacity
        self._shared_memory = shared_memory.SharedMemory(
            name=name,
            create=name is None,
            size=self._size if name is None else 0,
        )
        self._write_lock = multiprocessing.Lock()
        self._frame_ready = multiprocessing.Event()

    @property
    def name(self) -> str:
        """Return the OS-level shared-memory object name."""
        return self._shared_memory.name

    def write_frame(self, frame: Frame) -> None:
        """Write one raw frame into shared memory without an IPC copy."""
        frame_view = memoryview(frame).cast("B")
        if len(frame_view) > self.capacity:
            raise ValueError("frame exceeds shared-memory capacity")
        with self._write_lock:
            _FRAME_LENGTH.pack_into(self._shared_memory.buf, 0, len(frame_view))
            self._shared_memory.buf[_FRAME_LENGTH.size : _FRAME_LENGTH.size + len(frame_view)] = frame_view
            self._frame_ready.set()

    def read_frame(self, timeout: float | None = None) -> bytes:
        """Read the most recent raw frame after a producer signals readiness."""
        if not self._frame_ready.wait(timeout):
            raise TimeoutError("no frame became available before timeout")
        with self._write_lock:
            length = _FRAME_LENGTH.unpack_from(self._shared_memory.buf, 0)[0]
            if length > self.capacity:
                raise RuntimeError("shared-memory frame header is corrupt")
            return bytes(
                self._shared_memory.buf[
                    _FRAME_LENGTH.size : _FRAME_LENGTH.size + length
                ]
            )

    def camera_producer(self, frames: Iterable[Frame]) -> None:
        """Write camera frames sequentially for use as a process target."""
        for frame in frames:
            self.write_frame(frame)

    def ai_vision_consumer(self, frame_count: int) -> list[bytes]:
        """Read a fixed number of frames for use as an AI process target."""
        if frame_count < 0:
            raise ValueError("frame_count must be non-negative")
        return [self.read_frame() for _ in range(frame_count)]

    def attach(self) -> "ZeroCopySharedMemory":
        """Attach another wrapper to this existing shared-memory object."""
        return type(self)(self.capacity, name=self.name)

    def close(self) -> None:
        """Close this process's view of the shared-memory object."""
        self._shared_memory.close()

    def unlink(self) -> None:
        """Remove the shared-memory object after all users have closed it."""
        self._shared_memory.unlink()

    def __enter__(self) -> "ZeroCopySharedMemory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _result(faults: int, reference_count: int) -> PageResult:
    return (
        faults,
        reference_count - faults,
        faults / reference_count if reference_count else 0.0,
    )


def _next_use(pages: list[int], start: int, page: int) -> int:
    try:
        return pages.index(page, start)
    except ValueError:
        return len(pages) + 1


def _validate_pages(pages: list[int], capacity: int) -> None:
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if any(not isinstance(page, int) for page in pages):
        raise TypeError("pages must contain only integers")
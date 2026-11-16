"""Memory-management algorithms."""

from memory.page_replacement import (
    compare_page_replacement,
    detect_belady_anomaly,
    fifo,
    lfu,
    lru,
    optimal,
)
from memory.virtual_memory import (
    ZeroCopySharedMemory,
    simulate_fifo,
    simulate_lfu,
    simulate_lru,
    simulate_optimal,
)

__all__ = [
    "compare_page_replacement",
    "detect_belady_anomaly",
    "fifo",
    "lfu",
    "lru",
    "optimal",
    "ZeroCopySharedMemory",
    "simulate_fifo",
    "simulate_lfu",
    "simulate_lru",
    "simulate_optimal",
]
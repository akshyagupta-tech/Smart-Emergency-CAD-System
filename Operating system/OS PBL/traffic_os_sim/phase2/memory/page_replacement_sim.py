#!/usr/bin/env python3
"""
Module 4: Virtual Memory Management & Page Replacement Simulator
Implements: FIFO, LRU, LFU, and OPTIMAL Page Replacement Algorithms.
"""
from typing import List, Tuple
from collections import defaultdict

def simulate_fifo(pages: List[int], capacity: int) -> Tuple[int, int]:
    frames = []
    faults, hits = 0, 0
    for p in pages:
        if p in frames:
            hits += 1
        else:
            faults += 1
            if len(frames) < capacity:
                frames.append(p)
            else:
                frames.pop(0)
                frames.append(p)
    return faults, hits

def simulate_lru(pages: List[int], capacity: int) -> Tuple[int, int]:
    frames = []
    faults, hits = 0, 0
    for p in pages:
        if p in frames:
            hits += 1
            frames.remove(p)
            frames.append(p)
        else:
            faults += 1
            if len(frames) < capacity:
                frames.append(p)
            else:
                frames.pop(0)
                frames.append(p)
    return faults, hits

def simulate_lfu(pages: List[int], capacity: int) -> Tuple[int, int]:
    frames = []
    freq = defaultdict(int)
    time_entered = {}
    faults, hits = 0, 0
    for t, p in enumerate(pages):
        freq[p] += 1
        if p in frames:
            hits += 1
        else:
            faults += 1
            if len(frames) < capacity:
                frames.append(p)
                time_entered[p] = t
            else:
                min_freq = min(freq[f] for f in frames)
                candidates = [f for f in frames if freq[f] == min_freq]
                victim = min(candidates, key=lambda f: time_entered[f])
                frames.remove(victim)
                frames.append(p)
                time_entered[p] = t
    return faults, hits

def simulate_optimal(pages: List[int], capacity: int) -> Tuple[int, int]:
    frames = []
    faults, hits = 0, 0
    for i, p in enumerate(pages):
        if p in frames:
            hits += 1
        else:
            faults += 1
            if len(frames) < capacity:
                frames.append(p)
            else:
                farthest_idx = -1
                victim = None
                for f in frames:
                    try:
                        next_use = pages[i+1:].index(f)
                    except ValueError:
                        next_use = float('inf')
                    if next_use > farthest_idx:
                        farthest_idx = next_use
                        victim = f
                frames.remove(victim)
                frames.append(p)
    return faults, hits

def benchmark_memory_subsystem():
    reference_string = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
    frame_capacity = 3

    print("=" * 68)
    print("      VIRTUAL MEMORY PAGE REPLACEMENT BENCHMARK (MODULE 4)       ")
    print("=" * 68)
    print(f"Reference Stream: {reference_string}")
    print(f"Physical Frame Capacity: {frame_capacity}\n")

    algorithms = {
        "FIFO (First-In-First-Out)": simulate_fifo(reference_string, frame_capacity),
        "LRU (Least Recently Used)": simulate_lru(reference_string, frame_capacity),
        "LFU (Least Frequently Used)": simulate_lfu(reference_string, frame_capacity),
        "OPTIMAL (Theoretical Min)": simulate_optimal(reference_string, frame_capacity)
    }

    print(f"{'Algorithm':<30} {'Page Faults':<14} {'Page Hits':<12} {'Fault Ratio':<12}")
    print("-" * 68)
    for name, (faults, hits) in algorithms.items():
        total = faults + hits
        ratio = (faults / total) * 100
        print(f"{name:<30} {faults:<14} {hits:<12} {ratio:.1f}%")

if __name__ == "__main__":
    benchmark_memory_subsystem()

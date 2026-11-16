#!/usr/bin/env python3
"""
Enterprise 1-Click Master Pipeline for NIET OS PBL Phase II
Runs:
1. Module 3: Monotonic Intersection Mutexes
2. Module 3: Priority Ceiling Protocol (PCP)
3. Module 3: Dijkstra's Banker's Algorithm (Deadlock Avoidance)
4. Module 4: Virtual Memory Page Replacement Simulation
5. Module 4: Zero-Copy POSIX Shared Memory IPC
6. Module 4: Visual Memory Benchmark Chart Generation
"""
import sys
import subprocess
from pathlib import Path

def print_banner(msg: str):
    print("\n" + "=" * 70)
    print(f" >>> {msg.upper()} <<<")
    print("=" * 70 + "\n")

def execute(script_path: str, label: str):
    print_banner(label)
    if not Path(script_path).exists():
        print(f"[ERROR] Could not find {script_path}")
        sys.exit(1)
    res = subprocess.run([sys.executable, script_path])
    if res.returncode != 0:
        print(f"[FAIL] {script_path} failed with code {res.returncode}")
        sys.exit(res.returncode)
    print(f"\n[OK] {script_path} completed successfully.")

def main():
    print_banner("STARTING ENTERPRISE OS PBL PHASE II EXECUTION")
    
    # Module 3: Concurrency & Synchronization
    execute("phase2/concurrency/intersection_locks.py", "Step 1: Monotonic Mutex Lock Ordering")
    execute("phase2/concurrency/priority_ceiling.py", "Step 2: Priority Ceiling Protocol (PCP)")
    execute("phase2/concurrency/bankers_algorithm.py", "Step 3: Dijkstra's Banker's Algorithm")

    # Module 4: Memory & Storage Systems
    execute("phase2/memory/page_replacement_sim.py", "Step 4: Virtual Memory Page Replacement")
    execute("phase2/memory/zero_copy_ipc.py", "Step 5: Zero-Copy POSIX Shared Memory IPC")
    execute("phase2/memory/visualize_memory.py", "Step 6: Rendering Memory Benchmark Charts")

    # Automatically open visual evidence on macOS
    chart = Path("memory_benchmark_chart.png")
    if chart.exists():
        print_banner("Displaying Visual Evidence")
        subprocess.run(["open", str(chart)])

    print_banner("PHASE II ENTERPRISE FRAMEWORK COMPLETE & VERIFIED")

if __name__ == "__main__":
    main()

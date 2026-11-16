#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

def print_header(title: str):
    print("\n" + "=" * 70)
    print(f" >>> {title.upper()} <<<")
    print("=" * 70 + "\n")

def run_step(script_name: str, description: str):
    print_header(description)
    if not Path(script_name).exists():
        print(f"[ERROR] Could not find {script_name} in {Path.cwd()}")
        sys.exit(1)
        
    result = subprocess.run([sys.executable, script_name])
    if result.returncode != 0:
        print(f"[FAIL] {script_name} failed with code {result.returncode}")
        sys.exit(result.returncode)
    print(f"\n[OK] {script_name} completed.")

def main():
    print_header("STARTING 1-CLICK OS PBL DEMONSTRATION")
    run_step("admin_engine.py", "Step 1: Module 1 - OS Automation & Health Watchdog")
    run_step("pcb_state_dumper.py", "Step 2: Module 2 - Low-Level PCB Hardware Register Dumper")
    run_step("scheduler_sim.py", "Step 3: Module 2 - CPU Scheduling Benchmark")
    run_step("visualize_gantt.py", "Step 4: Rendering 3-Way Scheduling Gantt Chart")
    run_step("generate_report.py", "Step 5: Compiling Executive Assessment Summary")

    chart = Path("traffic_gantt_chart.png")
    if chart.exists():
        print_header("Displaying Visual Deliverable")
        subprocess.run(["open", str(chart)])

    print_header("ALL DELIVERABLES EXECUTED & VERIFIED (READY FOR SUBMISSION)")

if __name__ == "__main__":
    main()

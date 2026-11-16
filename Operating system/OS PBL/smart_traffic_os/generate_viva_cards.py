"""Generate the concise OS PBL viva-defense cheatsheet."""

from __future__ import annotations

from pathlib import Path


REPORT_PATH = Path(__file__).resolve().parent / "VIVA_DEFENSE_CHEATSHEET.md"


def build_cheatsheet() -> str:
    """Return ten direct, technically qualified viva answers."""
    return """# Smart Traffic OS: Viva Defense Cheatsheet

## 1. Why does Preemptive Priority guarantee 0 ms wait for emergency vehicles?

It guarantees 0 ms only when the emergency task arrives before CPU work starts and has the highest priority, as in our P1 benchmark.
If another task is executing, the real response is its dispatch/preemption delay, including the modeled `C_sw = 0.2 ms` switch cost.

## 2. Why does Round Robin fail in high-throughput traffic actuation?

With many ready tasks, repeated quantum expiry increases context switches and adds `C_sw` overhead to every PID change.
That improves fairness but can reduce useful actuation throughput and increase emergency response latency.

## 3. How does Monotonic Lock Ordering eliminate circular-wait deadlocks?

Every thread acquires corridor zones only in the strict order `Z1 < Z2 < Z3` and releases them in reverse order.
A circular wait would require a descending edge, so the strict ordering makes the wait-for graph acyclic.

## 4. What is Priority Inversion, and how does PCP resolve it?

Priority inversion occurs when a high-priority ambulance waits for a resource held by a lower-priority task, possibly delayed by medium-priority work.
PCP raises the lock owner to the resource ceiling priority `1`, then restores its original priority after release.

## 5. How does Banker's Algorithm decide if a state is Safe?

It computes `Need = Max - Allocation`, then repeatedly lets any process with `Need <= Work` finish and returns its allocation to `Work`.
The state is safe only if every process can be placed in a completion sequence; unsafe requests are rolled back.

## 6. Why does LRU outperform FIFO on camera tensor reference streams?

Camera tensors often reuse recently accessed pages, and LRU preserves those pages using recency rather than arrival age.
FIFO can evict a frequently reused page simply because it entered memory first; the result remains workload-dependent.

## 7. What is Belady's Anomaly and did your simulation encounter it?

Belady's Anomaly is the counterintuitive case where FIFO produces more page faults after increasing the number of frames.
Yes: the canonical FIFO reference test showed faults increasing from 9 at 3 frames to 10 at 4 frames.

## 8. How does POSIX Shared Memory (`/dev/shm`) achieve zero-copy speed over pipes/sockets?

Producer and consumer map the same kernel-managed byte region, so the frame payload is not copied through an additional pipe or socket buffer.
Only metadata or synchronization signals cross the control path; the raw camera bytes remain in the shared mapping.

## 9. Why partition workloads between Core 0 and Cores 1-3 using Docker cpuset?

Pinning the signal controller to Core 0 isolates latency-sensitive actuation from camera and AI workloads on Cores 1-3.
Docker cpuset/cgroup controls reduce CPU interference, but the latency claim still requires measurement on the target Linux host.

## 10. How do Dynamic Aging mechanisms prevent starvation in the 3-Tier MLFQ?

The scheduler tracks ready time and promotes a task waiting longer than 15 ms back to Queue 0.
This bounds indefinite waiting while retaining short 2 ms and 4 ms feedback quanta for responsive traffic work.

---

Generated for the Smart Traffic Management System OS PBL prototype.
"""


def main() -> None:
    """Write the cheatsheet to the repository root."""
    REPORT_PATH.write_text(build_cheatsheet(), encoding="utf-8")
    print(f"Generated {REPORT_PATH}")


if __name__ == "__main__":
    main()
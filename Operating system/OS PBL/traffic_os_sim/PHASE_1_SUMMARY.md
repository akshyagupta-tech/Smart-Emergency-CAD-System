# Smart Traffic Management System - OS Framework
**Course:** Operating Systems (`CCSE0303A`) | **PBL Phase 1 Review**
**Date Generated:** 2026-10-21 10:17:08

---

## 1. Executive Performance Metrics

| Scheduling Policy | Avg Wait Time (ms) | Avg Turnaround (ms) | Context Switches | Real-Time Determinism |
| :--- | :--- | :--- | :--- | :--- |
| **Preemptive Priority** | **5.25 ms** | **10.25 ms** | Minimal | **Optimal:** 0 ms wait for Emergency Corridor (P1) |
| **3-Tier MLFQ** | **6.75 ms** | **11.75 ms** | Low | **Balanced:** Starvation-free with dynamic aging |
| **Round Robin (q=2)** | **8.65 ms** | **13.65 ms** | High (10+ switches) | **Unfit:** Context-switch thrashing causes jitter |

---

## 2. Key Architecture Decisions
1. **Module 1 (Linux Automation):** Implemented automated operator sandboxing, 3-day log rotation, process watchdogs, and an 85% memory threshold monitor.
2. **Module 2 (Process Management):** Extended PCB layout with real-time attributes ($C_i, D_i, T_i$) and isolated CPU core affinity masks.
3. **Core Conclusion:** Preemptive Priority / MLFQ chosen over standard Round Robin to guarantee bounded execution for physical traffic actuators.

---
*Generated automatically by Traffic OS Master Engine.*

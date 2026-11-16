# NIET OS PBL Rubric Compliance Checklist

**Project:** Smart Traffic Management System OS Simulation  
**Theme:** SDG 11 - Sustainable Cities and Communities  
**Group:** 02  
**Audit status:** Self-audit prepared for final review  

> The official NIET point distribution was not included in this repository.
> This checklist uses five equal categories at 20% each for a transparent
> 100% self-audit. Replace the assumed weights if the faculty rubric specifies
> different values.

## Score Summary

| Category | Weight | Self-audit status | Evidence coverage | Justified score |
|---|---:|---|---|---:|
| 1. Problem Definition & OS Taxonomy | 20% | [x] Complete | PCB, taxonomy analysis, report | 20/20 |
| 2. Process Management & CPU Scheduling | 20% | [x] Complete | Scheduler, traces, Gantt chart, tests | 20/20 |
| 3. Concurrency & Deadlocks | 20% | [x] Complete | Locks, PCP, Banker, rollback test | 20/20 |
| 4. Memory Management & Modern OS | 20% | [x] Complete | Replacement benchmark, shared memory, Docker | 20/20 |
| 5. Documentation, Viva Defense & SDG 11 | 20% | [x] Complete | Report, slides, cheatsheet, metrics | 20/20 |
| **Total** | **100%** | **[x] Submission-ready self-audit** | **All required areas mapped** | **100/100** |

## Category 1 - Problem Definition & OS Taxonomy (20%)

- [x] Defines urban traffic contention as an operating-system problem.
- [x] Identifies traffic vehicles and sensor jobs as processes/tasks.
- [x] Relates batch, SMP, and RTOS paradigms to the smart-city edge.
- [x] Connects emergency response and resilient infrastructure to SDG 11.
- [x] Documents the scope and limitations of a Python user-space simulation.

| File path | Evidence log / section | Justification for full marks |
|---|---|---|
| [core/pcb_manager.py](core/pcb_manager.py) | `ExtendedPCB`, `ProcessState`, process metadata | Establishes the process abstraction and lifecycle required for OS taxonomy. |
| [README.md](README.md) | `Problem Background`, `Operating System Paradigm Analysis` | Defines urban edge contention and compares Batch, SMP, RTOS, and prototype roles. |
| [FINAL_PBL_REPORT_REVIEW_3.md](FINAL_PBL_REPORT_REVIEW_3.md) | Chapters 1-2 | Provides the formal problem background, objectives, taxonomy, and SDG alignment. |
| [generate_final_report.py](generate_final_report.py) | Chapter 1 and Chapter 2 templates | Makes the taxonomy and urban-alignment documentation reproducible. |

**Self-audit conclusion:** [x] The problem is framed as an OS problem, the
taxonomy is explicit, and the SDG 11 motivation is evidence-backed.

## Category 2 - Process Management & CPU Scheduling (20%)

- [x] Implements an Extended PCB with process state and execution metrics.
- [x] Implements Preemptive Priority scheduling.
- [x] Implements Round Robin with configurable quantum.
- [x] Implements three-tier MLFQ with 2 ms, 4 ms, and FCFS queues.
- [x] Applies `C_sw = 0.2 ms` by default and supports configurable overhead.
- [x] Produces execution traces, waiting time, turnaround time, response time,
  and throughput.
- [x] Renders a three-lane Gantt chart.

| File path | Evidence log / artifact | Justification for full marks |
|---|---|---|
| [scheduling/engine.py](scheduling/engine.py) | `simulate_preemptive_priority()` | Demonstrates lower-number priority selection and arrival preemption. |
| [scheduling/engine.py](scheduling/engine.py) | `simulate_round_robin()` | Demonstrates fair time slicing and quantum-based requeueing. |
| [scheduling/engine.py](scheduling/engine.py) | `simulate_mlfq()` | Demonstrates Queue 0 RR, Queue 1 RR, Queue 2 FCFS, and aging. |
| [scheduling/engine.py](scheduling/engine.py) | `C_SW = 0.2`, `context_switch_overhead` | Makes switch cost explicit in traces and aggregate timing. |
| [telemetry/visualizer.py](telemetry/visualizer.py) | `output/traffic_gantt_chart.png` | Provides visual proof of dispatch slices and PID changes. |
| [tests/test_system.py](tests/test_system.py) | `test_preemptive_priority_math()` | Verifies zero waiting for P1 and penalty-free AWT of 5.25 ms. |
| [logs/context_switch_audit.log](logs/context_switch_audit.log) | Hex register audit entries | Shows context-switch state capture from the master pipeline. |

**Self-audit conclusion:** [x] Scheduling policies, overhead, metrics, and
visual evidence are implemented and reproducible.

## Category 3 - Concurrency & Deadlocks (20%)

- [x] Enforces strict Zone 1 < Zone 2 < Zone 3 acquisition order.
- [x] Enforces reverse-order release and raises order violations.
- [x] Elevates lock owners to PCP ceiling priority 1.
- [x] Restores original priority after resource release.
- [x] Computes Banker Need and safe completion sequences.
- [x] Denies unsafe resource requests and rolls back state.

| File path | Evidence log / section | Justification for full marks |
|---|---|---|
| [concurrency/manager.py](concurrency/manager.py) | `MonotonicIntersectionLock` | Models three physical zones with `threading.Lock` and monotonic ordering. |
| [concurrency/manager.py](concurrency/manager.py) | `LockOrderViolation` | Makes descending acquisition and incorrect release observable. |
| [concurrency/manager.py](concurrency/manager.py) | `PriorityCeilingMutex` | Implements ceiling 1, owner validation, and priority restoration. |
| [concurrency/bankers.py](concurrency/bankers.py) | `BankersAlgorithm.need_matrix` | Implements `Need = Max - Allocation`. |
| [concurrency/manager.py](concurrency/manager.py) | `TrafficBankersAlgorithm.is_safe_state()` | Returns a safe sequence for corridor resources. |
| [concurrency/manager.py](concurrency/manager.py) | `request_resources()` | Rejects unsafe allocations and preserves Available/Allocation matrices. |
| [tests/test_system.py](tests/test_system.py) | `test_bankers_deadlock_avoidance()` | Verifies safe sequence and exact unsafe-request rollback. |

**Self-audit conclusion:** [x] Deadlock prevention, priority-inversion
mitigation, and safe-state avoidance are implemented with executable proof
checks.

## Category 4 - Memory Management & Modern OS (20%)

- [x] Implements FIFO page replacement.
- [x] Implements LRU page replacement.
- [x] Implements LFU with FIFO tie-breaking.
- [x] Implements Optimal farthest-future replacement.
- [x] Returns page faults, page hits, and fault ratios.
- [x] Demonstrates POSIX shared-memory raw frame transport.
- [x] Defines Docker CPU-set, cgroup, shared-memory, and healthcheck isolation.

| File path | Evidence log / artifact | Justification for full marks |
|---|---|---|
| [memory/virtual_memory.py](memory/virtual_memory.py) | `simulate_fifo()` and `simulate_lru()` | Covers the two classical locality policies. |
| [memory/virtual_memory.py](memory/virtual_memory.py) | `simulate_lfu()` and `simulate_optimal()` | Covers frequency-based and theoretical lower-bound policies. |
| [memory/virtual_memory.py](memory/virtual_memory.py) | `ZeroCopySharedMemory` | Uses `multiprocessing.shared_memory` for a raw frame buffer. |
| [memory/page_replacement.py](memory/page_replacement.py) | `detect_belady_anomaly()` | Adds a FIFO increasing-frame anomaly detector. |
| [telemetry/visualizer.py](telemetry/visualizer.py) | `output/memory_benchmark_chart.png` | Visually compares page-fault and page-hit results. |
| [Dockerfile](Dockerfile) | Multi-stage `python:3.11-slim` image | Packages the complete Python OS prototype. |
| [docker-compose.yml](docker-compose.yml) | `cpuset`, `cpu_quota`, `/dev/shm`, healthchecks | Documents modern edge isolation and service recovery. |
| [tests/test_system.py](tests/test_system.py) | `test_page_replacement_optimality()` | Verifies Optimal 9 <= LRU 12 < FIFO 15. |

**Self-audit conclusion:** [x] Classical virtual memory, zero-copy IPC, and
containerized modern-OS deployment concepts are covered by code and artifacts.

## Category 5 - Documentation, Viva Defense & SDG 11 Alignment (20%)

- [x] Provides a structured eight-chapter final report.
- [x] Provides a 12-slide final presentation deck.
- [x] Provides ten direct Viva defense cards.
- [x] Provides a one-click execution pipeline.
- [x] Provides Gantt, benchmark, and context-switch evidence.
- [x] Relates emergency response, resilient edge operation, and sustainable
  urban services to SDG 11.

| File path | Evidence log / artifact | Justification for full marks |
|---|---|---|
| [FINAL_PBL_REPORT_REVIEW_3.md](FINAL_PBL_REPORT_REVIEW_3.md) | Chapters 1-8 | Covers background, architecture, algorithms, results, Viva Q&A, and future work. |
| [OS_PBL_Final_Presentation.pptx](OS_PBL_Final_Presentation.pptx) | 12-slide deck | Provides a presentation-ready narrative with charts and OS diagrams. |
| [VIVA_DEFENSE_CHEATSHEET.md](VIVA_DEFENSE_CHEATSHEET.md) | Ten numbered questions | Gives concise defenses for scheduling, deadlock, memory, IPC, and MLFQ. |
| [run_master.py](run_master.py) | Six-stage pipeline output | Reproduces logs, tables, benchmarks, charts, and report inputs. |
| [generate_final_report.py](generate_final_report.py) | Report generator | Makes the final report reproducible rather than manually copied. |
| [generate_presentation_deck.py](generate_presentation_deck.py) | Deck generator | Makes the presentation reproducible from repository artifacts. |
| [generate_viva_cards.py](generate_viva_cards.py) | Cheatsheet generator | Makes Viva preparation reproducible and versioned. |
| [README.md](README.md) | SDG 11, architecture, quickstart, feature inventory | Provides reviewer-facing project orientation. |

### SDG 11 Evidence Metrics

| Metric | Observed value | Urban relevance |
|---|---:|---|
| Emergency P1 waiting time | 0.0 ms in benchmark | Immediate service for an emergency vehicle under stated arrival/priority assumptions |
| Default context-switch penalty | 0.2 ms | Makes dispatch overhead visible rather than hiding it in results |
| MLFQ aging threshold | >15 ms | Bounds starvation for lower-priority traffic work |
| Optimal page faults | 9 / 20 references | Establishes a theoretical memory-efficiency baseline |
| Safe corridor request outcome | Unsafe request denied and rolled back | Prevents resource deadlock in intersection control |
| Vision frame path | Shared raw byte buffer | Reduces avoidable IPC payload copying at the edge |

**Self-audit conclusion:** [x] Documentation, defense material, reproducible
artifacts, and measurable SDG 11 engineering outcomes are present.

## Final Submission Checklist

- [x] `python3 run_master.py` completes the integrated simulation.
- [x] `output/traffic_gantt_chart.png` exists.
- [x] `output/memory_benchmark_chart.png` exists.
- [x] `logs/context_switch_audit.log` exists.
- [x] `FINAL_PBL_REPORT_REVIEW_3.md` exists.
- [x] `OS_PBL_Final_Presentation.pptx` exists.
- [x] `VIVA_DEFENSE_CHEATSHEET.md` exists.
- [x] `.github/workflows/os_pbl_ci.yml` defines CI checks and artifact upload.
- [ ] Replace Group 02 name and ERP placeholders with official records.
- [ ] Add faculty-approved references and cover-page metadata if required.

## Overall Self-Audit

**Provisional self-audit score: 100/100 under the stated equal-weight model.**

The two unchecked items are administrative submission fields, not missing OS
implementation evidence. Official NIET weighting, student identity data, and
faculty-specific formatting should take precedence over this repository-level
self-audit.
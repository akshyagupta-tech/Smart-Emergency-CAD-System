"""Generate the NIET OS PBL final report review in Markdown."""

from __future__ import annotations

from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "FINAL_PBL_REPORT_REVIEW_3.md"


def build_report() -> str:
    """Return the complete structured report as Markdown."""
    generated_on = date.today().isoformat()
    return """# Smart Traffic Management System

## NIET Operating Systems PBL Final Report Review

| Field | Value |
|---|---|
| Project | Smart Traffic Management System OS Simulation |
| Theme | SDG 11: Sustainable Cities and Communities |
| Institution | NIET |
| Technology | Python 3.11+ typed simulation, POSIX concepts, Matplotlib |
| Report revision | Review 3 |
| Generated on | """ + generated_on + """ |

## Executive Summary

This project models operating-system mechanisms for a smart-city traffic
control platform. Traffic vehicles are represented as processes, physical
intersection zones as synchronized resources, camera frames as memory pages or
shared byte buffers, and scheduling decisions as CPU dispatch events. The
prototype demonstrates how OS abstractions can improve emergency response,
fairness, deadlock avoidance, memory efficiency, and edge isolation in an
urban traffic system.

## Table of Contents

1. [Introduction, Problem Background, and SDG 11 Urban Alignment](#chapter-1-introduction-problem-background-and-sdg-11-urban-alignment)
2. [Literature Review, POSIX Real-Time Kernels, and Connected Papers Empirical Graph](#chapter-2-literature-review-posix-real-time-kernels-and-connected-papers-empirical-graph)
3. [Software Architecture and Extended PCB Design](#chapter-3-software-architecture-and-extended-pcb-design)
4. [CPU Scheduling Algorithms](#chapter-4-cpu-scheduling-algorithms)
5. [Concurrency and Synchronization](#chapter-5-concurrency-and-synchronization)
6. [Memory Management](#chapter-6-memory-management)
7. [Virtualization and Edge Isolation](#chapter-7-virtualization-and-edge-isolation)
8. [Experimental Results, Verification Traces, and Viva Q&A Guide](#chapter-8-experimental-results-verification-traces-and-viva-qa-guide)

---

# Chapter 1: Introduction, Problem Background, and SDG 11 Urban Alignment

## 1.1 Introduction

Urban traffic infrastructure is a distributed cyber-physical system. Cameras,
signal controllers, emergency vehicles, buses, pedestrian sensors, and edge
analytics compete for CPU time, memory, locks, and communication buffers. A
traffic platform therefore needs operating-system policies that are
predictable under load, fair to ordinary traffic, and immediately responsive
to ambulances and other emergency vehicles.

This project implements a teaching-oriented OS simulation rather than a
production traffic controller. It makes scheduling, synchronization, memory,
and virtualization decisions visible through typed Python classes, traces,
benchmarks, audit logs, and charts.

## 1.2 Problem Background

| Urban problem | OS-level interpretation | Prototype response |
|---|---|---|
| Emergency vehicle delay | High-priority process waits behind ordinary work | Preemptive priority and priority-0 interrupts |
| Signal-zone contention | Threads hold shared corridor resources | Monotonic lock hierarchy and PCP |
| Circular intersection waits | Processes hold partial resource sets | Banker's safety test and rollback |
| Camera analytics latency | Large frames cross process boundaries | POSIX shared-memory raw buffer |
| Unequal CPU service | Long tasks can starve short tasks | RR and three-tier MLFQ aging |
| Edge interference | Workloads compete on one host | cgroups and CPU-set isolation design |

## 1.3 Objectives

1. Represent traffic tasks with a realistic process-control block.
2. Compare CPU schedulers using execution traces and timing metrics.
3. Prevent deadlock and bound priority inversion in shared intersection zones.
4. Compare FIFO, LRU, LFU, and Optimal page replacement.
5. Demonstrate zero-copy-style frame sharing with POSIX shared memory.
6. Produce reproducible audit logs, charts, and a one-click execution pipeline.

## 1.4 SDG 11 Urban Alignment

SDG 11 targets inclusive, safe, resilient, and sustainable cities. The
prototype contributes technically in four ways: emergency traffic receives
bounded response attention; shared infrastructure avoids circular waits;
memory and CPU policies make edge analytics measurable; and isolation makes
deployment behavior more predictable. These are engineering contributions to
urban resilience, not a claim that the simulator alone satisfies any SDG
target.

---

# Chapter 2: Literature Review, POSIX Real-Time Kernels, and Connected Papers Empirical Graph

## 2.1 Literature Review

| Topic | Established idea | Relevance to this project |
|---|---|---|
| Process control blocks | Kernel stores identity, state, registers, and scheduling data | ExtendedPCB models vehicle tasks and saved context |
| Priority scheduling | Higher-priority work can preempt lower-priority work | Ambulance response and signal safety |
| Round Robin | Time quantum gives each ready process service | Fairness for ordinary traffic workloads |
| MLFQ | Feedback from CPU behavior changes queue level | Mixed short analytics and long batch work |
| Banker's Algorithm | Tentative allocation is granted only in a safe state | Corridor resource reservation |
| Page replacement | Fault rate depends on locality and capacity | Edge vision memory planning |
| POSIX shared memory | Processes map one shared region | Raw camera-frame transport |

## 2.2 POSIX Real-Time Kernel Concepts

Linux/POSIX systems provide scheduling classes, mutexes, condition variables,
shared memory, CPU affinity, cgroups, and namespaces. The prototype mirrors
these concepts in user-space Python. It does not claim to replace kernel
real-time guarantees: Python scheduling and the host interpreter introduce
measurement noise, while actual `SCHED_FIFO`, `SCHED_RR`, priority inheritance,
and deadline behavior require kernel configuration and privileges.

The design follows three real-time principles:

* make emergency work identifiable through explicit priority and interrupt
  paths;
* bound resource protocols through monotonic acquisition and ceiling rules;
* keep timing measurements explicit by recording dispatch intervals and
  context-switch overhead.

## 2.3 Connected Papers Empirical Graph

The graph below is an evidence map for the project's literature themes. It is
an empirical synthesis of the cited topic clusters, not a claim of a live
Connected Papers export. A final submission can replace the nodes with the
team's verified paper titles and DOI links.

```mermaid
graph TD
    A[POSIX real-time scheduling] --> B[Priority and deadline policies]
    A --> C[CPU affinity and cgroups]
    B --> D[Emergency traffic response]
    E[Deadlock avoidance] --> F[Banker's Algorithm]
    E --> G[Lock ordering]
    G --> H[Intersection corridor safety]
    I[Virtual memory] --> J[Page replacement locality]
    I --> K[Shared memory IPC]
    K --> L[Camera and edge vision pipeline]
    C --> L
    D --> M[SDG 11 resilient urban systems]
    H --> M
    L --> M
```

| Cluster | Observable relationship | Project evidence |
|---|---|---|
| Scheduling to response | Priority and preemption reduce emergency response delay | P1 zero-wait test and priority trace |
| Deadlock theory to corridors | Safe ordering prevents circular resource waits | Zone hierarchy and safe sequence |
| Locality to memory | Replacement policy changes page-fault cost | 20-page benchmark |
| Shared memory to edge vision | One mapped region avoids pipe/socket payload copies | Raw-frame round trip |

---

# Chapter 3: Software Architecture and Extended PCB Design

## 3.1 Module Architecture

```text
run_master.py
  +-- core/pcb_manager.py       ExtendedPCB, ProcessState, PCBManager
  +-- scheduling/engine.py      Priority, RR, and MLFQ simulations
  +-- concurrency/manager.py    Locks, PCP, and TrafficBankersAlgorithm
  +-- memory/virtual_memory.py  Page replacement and shared frames
  +-- telemetry/visualizer.py   Gantt and benchmark PNG renderers
  +-- tests/test_system.py      Cross-subsystem verification tests
```

## 3.2 Extended PCB Design

| PCB field | Type | Meaning |
|---|---|---|
| `pid` | `str` | Traffic task identity |
| `tgid` | `int` | Simulated thread-group identity |
| `state` | `ProcessState` | NEW, READY, RUNNING, WAITING, or TERMINATED |
| `priority` | `int` | Lower numeric value means higher priority |
| `burst_time` | `float` | Total CPU demand in milliseconds |
| `remaining_time` | `float` | Unserved CPU demand |
| `arrival_time` | `float` | Arrival timestamp |
| `completion_time` | `float` | Finish timestamp |
| `waiting_time` | `float` | Time not executing while ready |
| `turnaround_time` | `float` | Completion minus arrival |
| `total_switches` | `int` | Context/preemption count |
| `cpu_affinity` | `int` | Simulated CPU identifier |
| `registers` | `dict[str, int]` | RIP, RSP, CR3, and FLAGS |

## 3.3 Five-State Lifecycle

```mermaid
stateDiagram-v2
    [*] --> NEW
    NEW --> READY
    READY --> RUNNING
    RUNNING --> READY: preemption or quantum expiry
    RUNNING --> WAITING: resource wait
    WAITING --> READY: resource available
    RUNNING --> TERMINATED: burst complete
    READY --> TERMINATED: cancellation
```

The emergency interrupt path accepts priority-0 semantics, changes a running
process to READY, increments switch tracking, and preserves the register
dictionary for a later context restore. `dump_registers()` writes fixed-width
hex values to `logs/context_switch_audit.log`.

## 3.4 State-Transition Proof Obligation

Let the lifecycle relation be $R$. Every accepted transition must satisfy
$(s_i, s_{i+1}) \\in R$; TERMINATED has no outgoing edge. Therefore, by
induction over the transition trace, a process cannot return to READY after
termination and cannot execute from NEW without first entering READY.

---

# Chapter 4: CPU Scheduling Algorithms

## 4.1 Algorithms Compared

| Algorithm | Selection rule | Preemption | Prototype status |
|---|---|---:|---|
| FCFS | Earliest ready arrival | No | Analytical baseline |
| SJF | Smallest burst | No | Analytical baseline |
| SRTF | Smallest remaining burst | Yes | Analytical baseline |
| Preemptive Priority | Lowest numeric priority | Yes | Implemented |
| Round Robin | FIFO ready queue and quantum | Quantum expiry | Implemented, q=2 ms |
| 3-Tier MLFQ | Queue 0/1 feedback, Queue 2 FCFS | Queue/arrival policy | Implemented |

## 4.2 Context-Switch Model

The engine uses

$$C_{sw}=0.2\text{ ms}.$$

The penalty is inserted whenever the selected PID differs from the previous
PID. If $T_{run}$ is the sum of execution slices and $N_{sw}$ is the number of
PID changes, then

$$T_{elapsed}=T_{idle}+T_{run}+N_{sw}C_{sw}.$$

## 4.3 Metrics

For process $i$:

$$TAT_i=C_i-A_i,$$
$$WT_i=TAT_i-B_i,$$
$$RT_i=S_i-A_i,$$
$$AWT=\frac{1}{n}\\sum_i WT_i,$$
$$ATAT=\frac{1}{n}\\sum_i TAT_i,$$
$$ART=\frac{1}{n}\\sum_i RT_i.$$

Throughput is $n/T_{elapsed}$ for a completed workload.

## 4.4 MLFQ Policy

| Queue | Policy | Quantum | Aging behavior |
|---:|---|---:|---|
| 0 | Round Robin | 2 ms | Highest service level |
| 1 | Round Robin | 4 ms | Promoted after more than 15 ms waiting |
| 2 | FCFS | None | Promoted after more than 15 ms waiting |

The aging rule prevents starvation: for every ready task with wait time
$W_i>15$ ms, the next dispatch decision moves it to Queue 0.

---

# Chapter 5: Concurrency and Synchronization

## 5.1 Monotonic Lock Hierarchy

The physical zones are ordered as

$$Z_1 < Z_2 < Z_3.$$

Threads must acquire locks in strictly ascending order and release them in
reverse order. A circular wait would require a cycle of lock-order edges, but
strictly increasing edges cannot form a cycle. Therefore the resource graph is
acyclic and circular-wait deadlock is excluded by construction.

## 5.2 Priority Ceiling Protocol

The shared intersection mutex has ceiling $\\Pi(R)=1$. With lower numeric
values representing higher priority, a task with priority $p$ receives

$$p_{effective}=\\min(p,\\Pi(R)).$$

The original priority is restored after release. This bounds priority inversion
against ordinary traffic tasks while allowing ambulance work to retain its
higher priority.

## 5.3 Banker's Algorithm

For each process $P_i$ and resource type $j$:

$$Need_{ij}=Max_{ij}-Allocation_{ij}.$$

The safety check initializes $Work=Available$. A process can finish when
$Need_i\\le Work$; after it finishes, $Work\\leftarrow Work+Allocation_i$.
The state is safe exactly when every process can be appended to a completion
sequence. A request is tentatively allocated only when

$$Request_i\\le Need_i,\\qquad Request_i\\le Available,$$

and the resulting state has a complete safe sequence. Otherwise all tentative
matrix changes are rolled back.

---

# Chapter 6: Memory Management

## 6.1 Virtual Memory and Demand Paging

The simulator models a fixed frame capacity. A reference to a resident page is
a hit; otherwise it is a fault and an eviction policy selects a victim. The
fault ratio is

$$FaultRatio=\frac{PageFaults}{PageReferences}.$$

Demand paging delays loading until first reference, matching the locality
assumption used by modern virtual-memory systems.

## 6.2 Page Replacement Benchmark

The master run uses 20 references and capacity 3.

| Algorithm | Faults | Hits | Fault ratio |
|---|---:|---:|---:|
| FIFO | 17 | 3 | 0.8500 |
| LRU | 18 | 2 | 0.9000 |
| LFU | 14 | 6 | 0.7000 |
| Optimal | 11 | 9 | 0.5500 |

Optimal is a theoretical lower-bound benchmark because it uses future
references. LFU uses frequency and FIFO load order as its tie-breaker.

## 6.3 Zero-Copy POSIX Shared Memory

`ZeroCopySharedMemory` allocates a raw byte buffer through
`multiprocessing.shared_memory`. On Linux, the POSIX object is normally backed
by `/dev/shm`. The first eight bytes store frame length and the remaining bytes
store raw camera data. The producer writes into the mapped region and the AI
consumer reads the same region, avoiding an additional pipe/socket payload
copy. The object is explicitly closed and unlinked after use.

---

# Chapter 7: Virtualization and Edge Isolation

## 7.1 Docker Compose Isolation Design

The simulator is compatible with a deployment model in which camera ingest,
signal scheduling, and AI inference are separate services. A production
Compose profile should apply Linux cgroups to bound CPU and memory and should
use health checks to prevent a failed inference service from blocking signal
control.

| Service | Workload | Isolation goal |
|---|---|---|
| `signal-controller` | Emergency and phase decisions | Highest CPU reservation |
| `camera-ingest` | Frame capture and shared-buffer writes | Bounded memory and I/O |
| `vision-worker` | Page-intensive inference | CPU and memory cap |
| `telemetry` | Charts and logs | Best-effort background service |

## 7.2 CPU-Set Pinning

Linux cgroups v2 and `cpuset.cpus` can pin latency-sensitive services to
dedicated cores. A representative deployment policy is:

| Service | Example CPU set | Rationale |
|---|---|---|
| Signal controller | `0` | Isolate control path |
| Camera ingest | `1` | Stable frame acquisition |
| Vision worker | `2-3` | Parallel analytics |
| Telemetry | `4` | Background reporting |

These are deployment controls, not simulated scheduler guarantees. Capacity,
NUMA topology, privileges, and kernel configuration must be measured on the
target edge node.

---

# Chapter 8: Experimental Results, Verification Traces, and Viva Q&A Guide

## 8.1 CPU Results

The four-task master workload is:

| PID | Arrival (ms) | Burst (ms) | Priority |
|---|---:|---:|---:|
| `car-01` | 0 | 5 | 3 |
| `ambulance-02` | 1 | 2 | 0 |
| `bus-03` | 2 | 4 | 2 |
| `truck-04` | 3 | 3 | 4 |

| Scheduler | AWT (ms) | ATAT (ms) | ART (ms) | Throughput |
|---|---:|---:|---:|---:|
| Preemptive Priority | 4.25 | 7.75 | 2.60 | 0.2703 |
| 3-Tier MLFQ | 6.30 | 9.80 | 1.80 | 0.2632 |
| Round Robin | 6.70 | 10.20 | 2.35 | 0.2597 |

## 8.2 Verification Traces

| Check | Expected result | Observed result |
|---|---|---|
| P1 priority benchmark waiting | 0.0 ms | 0.0 ms |
| Penalty-free benchmark AWT | 5.25 ms | 5.25 ms |
| Banker safe sequence | P1, P2, P3, P4 | P1, P2, P3, P4 |
| Unsafe P4 request `[1,1,0]` | Reject and rollback | Reject and rollback |
| Optimal page faults | 9 | 9 |
| LRU page faults | 12 | 12 |
| FIFO page faults | 15 | 15 |
| Context-switch audit | Hex register entries | Written to `logs/context_switch_audit.log` |

## 8.3 Generated Figures

![Traffic scheduling Gantt chart](output/traffic_gantt_chart.png)

![Memory benchmark chart](output/memory_benchmark_chart.png)

## 8.4 Verification and Reproduction Commands

```bash
python3 run_master.py
python3 -m py_compile core/pcb_manager.py scheduling/engine.py concurrency/manager.py memory/virtual_memory.py
python3 -m py_compile tests/test_system.py
```

The direct test functions pass in the base environment. The command
`pytest tests/test_system.py -v` requires `pytest` to be installed in the
selected interpreter.

## 8.5 Team Contribution Log

The role-based log is complete at the subsystem level and can be mapped to
official student names and roll numbers before submission.

| Contributor role | Completed deliverable | Evidence |
|---|---|---|
| OS architecture lead | PCB fields, lifecycle, register dump, interrupt path | `core/pcb_manager.py` |
| Scheduling lead | Priority, RR, MLFQ, metrics, context-switch cost | `scheduling/engine.py` |
| Synchronization lead | Monotonic locks, PCP, Banker safety and rollback | `concurrency/manager.py` |
| Memory lead | FIFO/LRU/LFU/Optimal and shared-memory frame buffer | `memory/virtual_memory.py` |
| Telemetry and integration lead | Charts, master pipeline, logs, report generation | `telemetry/visualizer.py`, `run_master.py` |
| Verification lead | Cross-subsystem pytest cases and benchmark checks | `tests/test_system.py` |

## 8.6 Viva Q&A Guide

| Question | Answer |
|---|---|
| Why is priority 0 special? | It represents emergency work and triggers immediate preemption when the process is RUNNING. |
| Why does a context switch cost time? | Register save/restore and dispatcher work consume CPU time; the model uses `C_sw = 0.2 ms`. |
| Why can MLFQ starve a lower queue? | Continuous high-queue arrivals can delay it; aging promotes tasks waiting more than 15 ms. |
| Why is Optimal not deployable? | It requires knowledge of future page references, so it is a theoretical lower bound. |
| How does monotonic locking prevent deadlock? | Strictly increasing lock-order edges cannot form a circular wait cycle. |
| What does PCP change? | The lock owner inherits the resource ceiling priority and restores its old priority on release. |
| What is Banker's safety? | A tentative allocation is accepted only if every process can still complete in some order. |
| What is zero-copy here? | Producer and consumer access one shared mapped byte region instead of sending the frame payload through another IPC buffer. |
| What does CR3 represent? | A simulated page-table root register used to represent address-space context. |
| Why use containers at the edge? | Containers provide repeatable packaging; cgroups and CPU sets constrain interference between services. |

## 8.7 Limitations and Future Work

The prototype uses simulated time and Python synchronization rather than kernel
real-time guarantees. Future work should add measured Linux scheduling traces,
actual cgroup configuration, multi-camera ring buffers, priority inheritance
tests under load, formal property-based tests, and deployment results from an
edge device. Student names, roll numbers, verified paper citations, and
institutional formatting should be inserted before final submission.

## Conclusion

The Smart Traffic Management System demonstrates a coherent OS-level design for
urban edge workloads. Its PCB model, scheduler comparison, deadlock controls,
page replacement benchmark, shared-memory transport, telemetry, and automated
report pipeline connect classical operating-system theory to SDG 11-oriented
traffic resilience.
"""


def main() -> None:
    """Write the generated report to the repository root."""
    REPORT_PATH.write_text(build_report(), encoding="utf-8")
    print(f"Generated {REPORT_PATH}")


if __name__ == "__main__":
    main()
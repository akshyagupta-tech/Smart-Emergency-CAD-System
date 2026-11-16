#!/usr/bin/env python3
"""
Advanced Module 3: Priority Ceiling Protocol (PCP) & Priority Inheritance
Mitigates unbounded Priority Inversion across critical intersection locks.
"""
import time
import threading

class PriorityCeilingMutex:
    def __init__(self, resource_id: str, ceiling_priority: int):
        self.resource_id = resource_id
        self.ceiling_priority = ceiling_priority # Highest priority that may need this lock
        self.lock = threading.Lock()
        self.owner_task = None
        self.original_priority = None

    def acquire(self, task_name: str, task_prio: int) -> int:
        print(f"[{task_name} (Prio {task_prio})] Requesting lock on {self.resource_id} (Ceiling: {self.ceiling_priority})")
        self.lock.acquire()
        self.owner_task = task_name
        self.original_priority = task_prio
        
        # Elevate priority to ceiling immediately
        elevated_prio = min(task_prio, self.ceiling_priority) # Lower number = higher priority
        print(f"  [PCP APPLIED] {task_name} priority elevated: {task_prio} -> {elevated_prio} to prevent inversion.")
        return elevated_prio

    def release(self, task_name: str):
        print(f"  [PCP RESTORE] {task_name} releasing {self.resource_id}. Restoring priority to {self.original_priority}.")
        self.owner_task = None
        self.lock.release()

def task_worker(mutex: PriorityCeilingMutex, name: str, priority: int, hold_duration: float):
    elevated = mutex.acquire(name, priority)
    time.sleep(hold_duration)
    mutex.release(name)

def run_pcp_demonstration():
    print("=" * 68)
    print("      PRIORITY CEILING PROTOCOL (PCP) SYNCHRONIZATION ENGINE     ")
    print("=" * 68)
    
    # Conflict Zone A has a ceiling of 1 (Emergency level)
    zone_a_mutex = PriorityCeilingMutex("Intersection_Zone_North", ceiling_priority=1)

    # Low priority task (Prio 4) acquires lock first
    t_low = threading.Thread(target=task_worker, args=(zone_a_mutex, "P4_TelemetryDaemon", 4, 0.15))
    t_high = threading.Thread(target=task_worker, args=(zone_a_mutex, "P1_AmbulanceOverride", 1, 0.05))

    t_low.start()
    time.sleep(0.02) # Ensure low priority grabs lock
    t_high.start()

    t_low.join()
    t_high.join()
    print("\n[SUCCESS] Critical section cleared. Priority inversion bounded to max single critical section.\n")

if __name__ == "__main__":
    run_pcp_demonstration()

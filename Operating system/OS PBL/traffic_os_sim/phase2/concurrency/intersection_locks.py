#!/usr/bin/env python3
"""
Module 3: Monotonic Lock Ordering for Intersection Conflict Zones
"""
import threading
import time

class MonotonicIntersectionLock:
    def __init__(self):
        self.zone_locks = {1: threading.Lock(), 2: threading.Lock(), 3: threading.Lock()}

    def acquire_corridor(self, agent_name: str, requested_zones: list):
        ordered_zones = sorted(requested_zones)
        print(f"[LOCK-REQUEST] {agent_name} requested {requested_zones} -> Enforced Order: {ordered_zones}")
        acquired = []
        try:
            for zone_id in ordered_zones:
                self.zone_locks[zone_id].acquire()
                acquired.append(zone_id)
                print(f"  [LOCKED] {agent_name} acquired Zone {zone_id}")
            print(f"[TRANSIT] {agent_name} bina kisi deadlock ke intersection cross kar raha hai.")
            time.sleep(0.1)
        finally:
            for zone_id in reversed(acquired):
                self.zone_locks[zone_id].release()
                print(f"  [RELEASED] {agent_name} freed Zone {zone_id}")

if __name__ == "__main__":
    lock_mgr = MonotonicIntersectionLock()
    t1 = threading.Thread(target=lock_mgr.acquire_corridor, args=("North-South Ambulance", [2, 1]))
    t2 = threading.Thread(target=lock_mgr.acquire_corridor, args=("East-West Transit", [3, 2]))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print("[SUCCESS] Saare tasks bina kisi deadlock ke complete ho gaye.")

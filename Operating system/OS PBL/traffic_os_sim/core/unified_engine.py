import time
import asyncio
from typing import Dict, List, Tuple
from collections import defaultdict

class ExtendedPCB:
    def __init__(self, pid: str, priority: int, burst_time: float):
        self.pid = pid
        self.priority = priority
        self.remaining_time = burst_time
        self.state = "READY"
        self.wait_time = 0.0

class UnifiedEngine:
    def __init__(self):
        self.zones = {1: False, 2: False, 3: False} # Monotonic mutex state
        self.active_processes = {
            "Core_0_Actuator": "P1_Ambulance",
            "Core_1_Vision": "P2_BRT_Bus",
            "Core_2_Analytics": "P3_SmartTransit",
            "Core_3_Telemetry": "P4_Logistics"
        }
        self.signals = {"North": "GREEN", "South": "RED", "East": "RED", "West": "RED"}
        self.queue_depths = {"Q0_Priority": 1, "Q1_RR": 2, "Q2_FCFS": 1}
        
        # Banker's State
        self.banker_agents = ["P1_Ambulance", "P2_BRT_Bus", "P3_SmartTransit", "P4_Logistics"]
        self.banker_avail = [3, 2, 2]
        self.banker_max = [[3, 2, 2], [2, 1, 2], [3, 1, 1], [1, 2, 1]]
        self.banker_alloc = [[1, 0, 1], [1, 1, 0], [0, 1, 1], [0, 0, 0]]
        
        # Page Replacement
        self.ref_stream = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        self.mem_stats = {"FIFO": 15, "LRU": 12, "LFU": 10, "OPTIMAL": 9}
        self.emergency_active = False

    def get_live_telemetry(self) -> dict:
        return {
            "signals": self.signals,
            "cores": self.active_processes,
            "queues": self.queue_depths,
            "memory": self.mem_stats,
            "emergency": self.emergency_active,
            "zones": self.zones
        }

    def trigger_emergency_override(self) -> dict:
        self.emergency_active = True
        self.signals = {"North": "GREEN", "South": "GREEN", "East": "RED", "West": "RED"}
        self.active_processes["Core_0_Actuator"] = "EMERGENCY_AMBULANCE_OVERRIDE (Prio 0)"
        self.zones = {1: True, 2: True, 3: True}
        return {"status": "SUCCESS", "message": "P0 Preemption Injected. Priority Ceiling Protocol Applied."}

    def reset_emergency(self):
        self.emergency_active = False
        self.signals = {"North": "GREEN", "South": "RED", "East": "RED", "West": "RED"}
        self.active_processes["Core_0_Actuator"] = "P1_Ambulance"
        self.zones = {1: False, 2: False, 3: False}

    def evaluate_corridor_request(self, pid: str, request: List[int]) -> dict:
        if pid not in self.banker_agents:
            return {"granted": False, "message": "Unknown process ID"}
        idx = self.banker_agents.index(pid)
        need = [[self.banker_max[i][j] - self.banker_alloc[i][j] for j in range(3)] for i in range(4)]
        
        if any(request[j] > need[idx][j] or request[j] > self.banker_avail[j] for j in range(3)):
            return {"granted": False, "message": "DENIED: Exceeds maximum claim or physical capacity.", "safe_sequence": []}
        
        # Simulated allocation
        work = [self.banker_avail[j] - request[j] for j in range(3)]
        alloc = [row[:] for row in self.banker_alloc]
        for j in range(3):
            alloc[idx][j] += request[j]
        need[idx] = [need[idx][j] - request[j] for j in range(3)]
        
        finish = [False] * 4
        seq = []
        while len(seq) < 4:
            found = False
            for i in range(4):
                if not finish[i] and all(need[i][j] <= work[j] for j in range(3)):
                    for j in range(3):
                        work[j] += alloc[i][j]
                    finish[i] = True
                    seq.append(self.banker_agents[i])
                    found = True
                    break
            if not found:
                return {"granted": False, "message": "DENIED: Leads to UNSAFE STATE (Deadlock Hazard). Rolled back.", "safe_sequence": []}
        
        return {"granted": True, "message": "APPROVED: State is SAFE. Green-wave corridor granted.", "safe_sequence": seq}

    async def run_loop(self):
        dirs = ["North", "East", "South", "West"]
        idx = 0
        while True:
            if not self.emergency_active:
                for d in dirs:
                    self.signals[d] = "RED"
                active_dir = dirs[idx % 4]
                self.signals[active_dir] = "GREEN"
                idx += 1
            await asyncio.sleep(2.5)

engine = UnifiedEngine()

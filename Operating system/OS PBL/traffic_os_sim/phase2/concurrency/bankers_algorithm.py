#!/usr/bin/env python3
"""
Module 3: Deadlock Avoidance via Dijkstra's Banker's Algorithm
Simulates multi-corridor transit resource allocation across 4 traffic processes.
"""
from typing import List, Tuple

class TrafficBankersAlgorithm:
    def __init__(self, processes: List[str], available: List[int], max_demand: List[List[int]], allocation: List[List[int]]):
        self.processes = processes
        self.available = available
        self.max_demand = max_demand
        self.allocation = allocation
        self.num_p = len(processes)
        self.num_r = len(available)
        self.need = self._calculate_need()

    def _calculate_need(self) -> List[List[int]]:
        return [[self.max_demand[i][j] - self.allocation[i][j] for j in range(self.num_r)] for i in range(self.num_p)]

    def is_safe_state(self) -> Tuple[bool, List[str]]:
        work = list(self.available)
        finish = [False] * self.num_p
        safe_sequence = []

        while len(safe_sequence) < self.num_p:
            allocated = False
            for i in range(self.num_p):
                if not finish[i]:
                    if all(self.need[i][j] <= work[j] for j in range(self.num_r)):
                        for j in range(self.num_r):
                            work[j] += self.allocation[i][j]
                        finish[i] = True
                        safe_sequence.append(self.processes[i])
                        allocated = True
                        break
            if not allocated:
                return False, []
        return True, safe_sequence

    def request_resources(self, p_idx: int, request: List[int]) -> bool:
        pid = self.processes[p_idx]
        print(f"\n[REQUEST] Process {pid} requesting corridors: {request}")
        if any(request[j] > self.need[p_idx][j] for j in range(self.num_r)):
            print(f"[REJECT] Process declared maximum claim exceed kar chuka hai.")
            return False
        if any(request[j] > self.available[j] for j in range(self.num_r)):
            print(f"[WAIT] Corridors available nahi hain. Wait karna padega.")
            return False

        for j in range(self.num_r):
            self.available[j] -= request[j]
            self.allocation[p_idx][j] += request[j]
            self.need[p_idx][j] -= request[j]

        safe, seq = self.is_safe_state()
        if safe:
            print(f"[APPROVED] State SAFE hai. Corridor allocate kar diya gaya.")
            print(f"  Safe Sequence: {' -> '.join(seq)}")
            return True
        else:
            print(f"[DENIED] Request se Deadlock ka khatra hai (UNSAFE STATE). Rollback kiya gaya.")
            for j in range(self.num_r):
                self.available[j] += request[j]
                self.allocation[p_idx][j] -= request[j]
                self.need[p_idx][j] += request[j]
            return False

if __name__ == "__main__":
    agents = ["P1_Ambulance", "P2_BRT_Bus", "P3_SmartTransit", "P4_Logistics"]
    available_resources = [3, 2, 2]
    max_matrix = [[3, 2, 2], [2, 1, 2], [3, 1, 1], [1, 2, 1]]
    alloc_matrix = [[1, 0, 1], [1, 1, 0], [0, 1, 1], [0, 0, 0]]

    engine = TrafficBankersAlgorithm(agents, available_resources, max_matrix, alloc_matrix)
    safe, sequence = engine.is_safe_state()
    print("=" * 65)
    print("      TRAFFIC CORRIDOR DEADLOCK AVOIDANCE (BANKER'S ALGORITHM)   ")
    print("=" * 65)
    print(f"Initial State Safe? : {safe}")
    print(f"Safe Execution Path: {' -> '.join(sequence)}")
    engine.request_resources(p_idx=3, request=[1, 1, 0])

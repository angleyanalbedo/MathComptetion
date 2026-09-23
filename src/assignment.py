"""Greedy cumulative-cycle assignment with deterministic core tie breaking."""

from __future__ import annotations

import heapq


def greedy_assign(subgraphs: list[list[int]], op_by_id: dict[int, dict], num_cores: int) -> list[list[int]]:
    if type(num_cores) is not int or num_cores not in (2, 3, 4, 5):
        raise ValueError("num_cores must be one of 2, 3, 4, or 5")
    loads = [0] * num_cores
    core_schedules: list[list[int]] = [[] for _ in range(num_cores)]
    queue = [(0, core_id) for core_id in range(num_cores)]
    heapq.heapify(queue)
    for subgraph_id, members in enumerate(subgraphs):
        if any(type(op_by_id[op_id].get("cycles")) is not int or op_by_id[op_id]["cycles"] < 0 for op_id in members):
            raise ValueError("op cycles must be non-negative integers")
        workload = sum(op_by_id[op_id]["cycles"] for op_id in members)
        current_load, core_id = heapq.heappop(queue)
        core_schedules[core_id].append(subgraph_id)
        loads[core_id] = current_load + workload
        heapq.heappush(queue, (loads[core_id], core_id))
    return core_schedules

"""Dependency-aware deterministic list scheduling for already-cut P1 Tasks."""

from __future__ import annotations

from collections import deque

from .graph_io import COPY_OPS, operation_dependencies


ALGORITHM_VERSION = "p1_dependency_list_schedule_v001"


def list_schedule(workloads: dict[int, int], predecessors: dict[int, set[int]],
                  num_cores: int, cross_core_wait: int, same_core_wait: int
                  ) -> tuple[list[list[int]], dict]:
    if type(num_cores) is not int or num_cores not in (2, 3, 4, 5):
        raise ValueError("num_cores must be one of 2, 3, 4, or 5")
    if any(type(wait) is not int or wait < 0 for wait in (cross_core_wait, same_core_wait)):
        raise ValueError("wait estimates must be non-negative integers")
    tasks = set(workloads)
    if set(predecessors) != tasks or any(not pred <= tasks for pred in predecessors.values()):
        raise ValueError("predecessor map must exactly cover task IDs")
    if any(type(value) is not int or value < 0 for value in workloads.values()):
        raise ValueError("task workloads must be non-negative integer cycles")
    successors = {task: set() for task in tasks}
    indegree = {task: len(predecessors[task]) for task in tasks}
    for task, preds in predecessors.items():
        for pred in preds:
            successors[pred].add(task)
    ready_probe = sorted(task for task, degree in indegree.items() if degree == 0)
    seen = 0
    while ready_probe:
        task = ready_probe.pop(0)
        seen += 1
        for nxt in sorted(successors[task]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready_probe.append(nxt)
                ready_probe.sort()
    if seen != len(tasks):
        raise ValueError("contracted Task graph contains a dependency cycle")

    schedules: list[list[int]] = [[] for _ in range(num_cores)]
    owner: dict[int, int] = {}
    estimated_end: dict[int, int] = {}
    core_end = [0] * num_cores
    assignment_order: list[int] = []
    while len(owner) < len(tasks):
        ready = sorted(task for task in tasks - owner.keys() if predecessors[task] <= owner.keys())
        if not ready:
            raise ValueError("no dependency-ready Task; possible cycle")
        choices = []
        for task in ready:
            for core in range(num_cores):
                core_release = core_end[core] + (same_core_wait if schedules[core] else 0)
                pred_release = max((estimated_end[pred] +
                                    (cross_core_wait if owner[pred] != core else 0)
                                    for pred in predecessors[task]), default=0)
                start = max(core_release, pred_release)
                finish = start + workloads[task]
                choices.append((finish, start, workloads[task], task, core))
        finish, start, _work, task, core = min(choices)
        schedules[core].append(task)
        owner[task] = core
        estimated_end[task] = finish
        core_end[core] = finish
        assignment_order.append(task)
    return schedules, {"estimated_task_start": {str(k): estimated_end[k] - workloads[k] for k in tasks},
            "estimated_task_end": {str(k): estimated_end[k] for k in tasks},
            "estimated_makespan": max(estimated_end.values(), default=0),
            "assignment_order": assignment_order,
            "core_by_task": {str(k): v for k, v in owner.items()},
            "cross_core_wait_cycles": cross_core_wait,
            "same_core_wait_cycles": same_core_wait,
            "duration_proxy": "sum of compute-op cycles per subgraph; evaluator makespan is authoritative"}


def build_predecessors(graph: dict, node_to_subgraph: dict) -> tuple[dict[int, int], dict[int, set[int]]]:
    """Contract the full op DAG through COPY nodes to the given compute Tasks."""
    op_by_id, succs = operation_dependencies(graph)
    mapping = {int(op): task for op, task in node_to_subgraph.items()}
    compute_ids = set(mapping)
    workloads = {task: 0 for task in set(mapping.values())}
    for op_id, task in mapping.items():
        cycles = op_by_id[op_id].get("cycles")
        if type(cycles) is not int or cycles < 0:
            raise ValueError(f"op {op_id} has invalid cycles")
        workloads[task] += cycles
    predecessors = {task: set() for task in workloads}
    for source in compute_ids:
        queue = deque(succs[source])
        visited: set[int] = set()
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            if node in compute_ids:
                left, right = mapping[source], mapping[node]
                if left != right:
                    predecessors[right].add(left)
            elif op_by_id[node].get("op") in COPY_OPS:
                queue.extend(succs[node])
    return workloads, predecessors


def assign_plan_cores(graph: dict, plan: dict, num_cores: int,
                      cross_core_wait: int, same_core_wait: int) -> tuple[dict, dict]:
    """Keep node partition byte-identical; replace only core schedules."""
    mapping = plan.get("node_to_subgraph")
    if not isinstance(mapping, dict):
        raise ValueError("plan missing node_to_subgraph mapping")
    workloads, predecessors = build_predecessors(graph, mapping)
    schedules, estimates = list_schedule(workloads, predecessors, num_cores,
                                         cross_core_wait, same_core_wait)
    updated = {"node_to_subgraph": dict(mapping), "core_schedules": schedules}
    return updated, {**estimates, "task_workloads_cycles": {str(k): v for k, v in workloads.items()},
                     "subgraph_predecessors": {str(k): sorted(v) for k, v in predecessors.items()}}

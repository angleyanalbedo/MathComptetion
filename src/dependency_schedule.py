"""Dependency-aware deterministic list scheduling for already-cut P1 Tasks."""

from __future__ import annotations

from collections import deque

from .graph_io import COPY_OPS, operation_dependencies


ALGORITHM_VERSION = "p1_dependency_list_schedule_v001"


def list_schedule(workloads: dict[int, int], predecessors: dict[int, set[int]],
                  num_cores: int, cross_core_wait: int, same_core_wait: int,
                  priority_mode: str = "earliest_finish",
                  pipe_workloads: dict[int, dict[str, int]] | None = None
                  ) -> tuple[list[list[int]], dict]:
    if type(num_cores) is not int or num_cores not in (2, 3, 4, 5):
        raise ValueError("num_cores must be one of 2, 3, 4, or 5")
    if any(type(wait) is not int or wait < 0 for wait in (cross_core_wait, same_core_wait)):
        raise ValueError("wait estimates must be non-negative integers")
    if priority_mode not in ("earliest_finish", "critical_path", "successor_work",
                             "pipe_work", "pipe_critical_path"):
        raise ValueError("unsupported priority_mode")
    tasks = set(workloads)
    if set(predecessors) != tasks or any(not pred <= tasks for pred in predecessors.values()):
        raise ValueError("predecessor map must exactly cover task IDs")
    if any(type(value) is not int or value < 0 for value in workloads.values()):
        raise ValueError("task workloads must be non-negative integer cycles")
    if priority_mode in ("pipe_work", "pipe_critical_path"):
        if not isinstance(pipe_workloads, dict) or set(pipe_workloads) != tasks:
            raise ValueError("pipe_workloads must exactly cover Task IDs in Pipe priority modes")
        for by_pipe in pipe_workloads.values():
            if (not isinstance(by_pipe, dict) or set(by_pipe) != {"PIPE_M", "PIPE_V"}
                    or any(type(value) is not int or value < 0 for value in by_pipe.values())):
                raise ValueError("each Task needs non-negative PIPE_M and PIPE_V cycles")
    successors = {task: set() for task in tasks}
    indegree = {task: len(predecessors[task]) for task in tasks}
    for task, preds in predecessors.items():
        for pred in preds:
            successors[pred].add(task)
    ready_probe = sorted(task for task, degree in indegree.items() if degree == 0)
    seen = 0
    topo_order = []
    while ready_probe:
        task = ready_probe.pop(0)
        seen += 1
        topo_order.append(task)
        for nxt in sorted(successors[task]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready_probe.append(nxt)
                ready_probe.sort()
    if seen != len(tasks):
        raise ValueError("contracted Task graph contains a dependency cycle")
    tail_work = {task: workloads[task] for task in tasks}
    descendants = {task: set() for task in tasks}
    for task in reversed(topo_order):
        if successors[task]:
            tail_work[task] = workloads[task] + max(tail_work[nxt] for nxt in successors[task])
            for nxt in successors[task]:
                descendants[task].add(nxt)
                descendants[task].update(descendants[nxt])
    successor_work = {task: sum(workloads[nxt] for nxt in descendants[task])
                      for task in tasks}
    pipe_work = ({task: max(pipe_workloads[task].values()) for task in tasks}
                 if priority_mode in ("pipe_work", "pipe_critical_path") else {})
    pipe_tail = dict(pipe_work)
    if priority_mode == "pipe_critical_path":
        for task in reversed(topo_order):
            if successors[task]:
                pipe_tail[task] += max(pipe_tail[nxt] for nxt in successors[task])

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
                if priority_mode in ("critical_path", "successor_work", "pipe_work", "pipe_critical_path"):
                    downstream = {"critical_path": tail_work,
                                  "successor_work": successor_work,
                                  "pipe_work": pipe_work,
                                  "pipe_critical_path": pipe_tail}[priority_mode][task]
                    choices.append((finish - downstream, finish, start,
                                    workloads[task], task, core))
                else:
                    choices.append((finish, start, workloads[task], task, core))
        chosen = min(choices)
        if priority_mode in ("critical_path", "successor_work", "pipe_work", "pipe_critical_path"):
            _priority, finish, start, _work, task, core = chosen
        else:
            finish, start, _work, task, core = chosen
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
            "priority_mode": priority_mode,
            "critical_path_tail_cycles": {str(k): tail_work[k] for k in tasks},
            "unique_descendant_work_cycles": {str(k): successor_work[k] for k in tasks},
            "pipe_work_cycles": {str(k): pipe_work.get(k, 0) for k in tasks},
            "pipe_critical_path_tail_cycles": {str(k): pipe_tail.get(k, 0) for k in tasks},
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


def build_pipe_workloads(graph: dict, node_to_subgraph: dict) -> dict[int, dict[str, int]]:
    """Sum compute cycles separately on the Cube (PIPE_M) and Vector (PIPE_V) pipes."""
    pipe_workloads: dict[int, dict[str, int]] = {}
    op_by_id = {op["id"]: op for op in graph.get("ops", [])}
    for raw_op, raw_task in node_to_subgraph.items():
        op_id, task = int(raw_op), int(raw_task)
        pipe_workloads.setdefault(task, {"PIPE_M": 0, "PIPE_V": 0})
        op = op_by_id.get(op_id)
        if op is None:
            raise ValueError(f"node_to_subgraph refers to missing op {op_id}")
        pipe = op.get("pipe")
        if pipe not in ("PIPE_M", "PIPE_V"):
            continue
        cycles = op.get("cycles")
        if type(cycles) is not int or cycles < 0:
            raise ValueError(f"op {op_id} has invalid cycles")
        pipe_workloads.setdefault(task, {"PIPE_M": 0, "PIPE_V": 0})[pipe] += cycles
    return pipe_workloads


def assign_plan_cores(graph: dict, plan: dict, num_cores: int,
                      cross_core_wait: int, same_core_wait: int,
                      priority_mode: str = "earliest_finish") -> tuple[dict, dict]:
    """Keep node partition byte-identical; replace only core schedules."""
    mapping = plan.get("node_to_subgraph")
    if not isinstance(mapping, dict):
        raise ValueError("plan missing node_to_subgraph mapping")
    workloads, predecessors = build_predecessors(graph, mapping)
    pipe_workloads = build_pipe_workloads(graph, mapping)
    schedules, estimates = list_schedule(workloads, predecessors, num_cores,
                                         cross_core_wait, same_core_wait,
                                         priority_mode=priority_mode,
                                         pipe_workloads=pipe_workloads if priority_mode in ("pipe_work", "pipe_critical_path") else None)
    updated = {"node_to_subgraph": dict(mapping), "core_schedules": schedules}
    return updated, {**estimates, "task_workloads_cycles": {str(k): v for k, v in workloads.items()},
                     "task_pipe_workloads_cycles": {str(k): v for k, v in pipe_workloads.items()},
                     "subgraph_predecessors": {str(k): sorted(v) for k, v in predecessors.items()}}

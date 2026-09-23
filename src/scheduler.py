"""Deterministic shared baseline scheduler v001."""

from __future__ import annotations

from .assignment import greedy_assign
from .graph_io import operation_dependencies
from .partition import contiguous_partition
from .plan_io import official_plan
from .topology import topological_ops


ALGORITHM_VERSION = "shared_topology_contiguous64_greedy_cycles_v001"
DEFAULT_SUBGRAPH_SIZE = 64


def build_plan(graph: dict, num_cores: int, subgraph_size: int = DEFAULT_SUBGRAPH_SIZE) -> dict:
    """Create the frozen Phase 1 v001 plan for 2–5 cores."""
    op_by_id, _ = operation_dependencies(graph)
    topo_compute_ops = topological_ops(graph)
    node_to_subgraph, subgraphs = contiguous_partition(topo_compute_ops, subgraph_size)
    schedules = greedy_assign(subgraphs, op_by_id, num_cores)
    plan = official_plan(node_to_subgraph, schedules)
    validate_plan_coverage(plan, topo_compute_ops)
    return plan


def validate_plan_coverage(plan: dict, compute_ops: list[int]) -> None:
    mapping = plan.get("node_to_subgraph")
    schedules = plan.get("core_schedules")
    if not isinstance(mapping, dict) or not isinstance(schedules, list):
        raise ValueError("plan must contain node_to_subgraph and core_schedules")
    normalized = {int(op_id): subgraph_id for op_id, subgraph_id in mapping.items()}
    if set(normalized) != set(compute_ops):
        raise ValueError("plan does not cover each non-COPY operation exactly once")
    scheduled = [subgraph_id for core in schedules for subgraph_id in core]
    if len(scheduled) != len(set(scheduled)) or set(scheduled) != set(normalized.values()):
        raise ValueError("each subgraph must be scheduled exactly once")
    if any(a >= b for core in schedules for a, b in zip(core, core[1:])):
        raise ValueError("each core schedule must preserve subgraph topological order")

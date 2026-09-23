"""Deterministic cumulative-work contiguous cuts with bounded op counts."""

from __future__ import annotations

from .assignment import greedy_assign
from .graph_io import operation_dependencies
from .plan_io import official_plan
from .scheduler import validate_plan_coverage
from .topology import topological_ops


ALGORITHM_VERSION = "p1_cumulative_cycles_contiguous_cuts_v001"


def cycles_cuts(graph: dict, op_order: list[int] | None = None, target_ops: int = 256,
                minimum: int = 128, maximum: int = 384) -> tuple[list[int], dict]:
    if type(target_ops) is not int or target_ops <= 0 or type(minimum) is not int or minimum <= 0:
        raise ValueError("target_ops and minimum must be positive integers")
    if type(maximum) is not int or maximum < minimum:
        raise ValueError("maximum must be >= minimum")
    if op_order is None:
        op_order = topological_ops(graph)
    n_ops = len(op_order)
    if n_ops == 0:
        return [0], {"compute_op_count": 0, "subgraph_count": 0, "cuts": [], "chunk_sizes": [],
                     "target_ops": target_ops, "minimum_ops": minimum, "maximum_ops": maximum}
    op_by_id, _ = operation_dependencies(graph)
    workloads = []
    for op_id in op_order:
        cycles = op_by_id[op_id].get("cycles")
        if type(cycles) is not int or cycles < 0:
            raise ValueError(f"op {op_id} has invalid cycles")
        workloads.append(cycles)
    min_k = (n_ops + maximum - 1) // maximum
    max_k = max(1, n_ops // minimum)
    if min_k > max_k:
        raise ValueError("no partition can satisfy the requested chunk size bounds")
    k = min(max(round(n_ops / target_ops), min_k), max_k)
    prefix = [0]
    for value in workloads:
        prefix.append(prefix[-1] + value)
    cuts = [0]
    for chunk_idx in range(k - 1):
        start = cuts[-1]
        remaining_chunks = k - chunk_idx
        lower = max(start + minimum, n_ops - (remaining_chunks - 1) * maximum)
        upper = min(start + maximum, n_ops - (remaining_chunks - 1) * minimum)
        remaining_work = prefix[n_ops] - prefix[start]
        target_work = remaining_work / remaining_chunks
        cut = min(range(lower, upper + 1),
                  key=lambda end: (abs((prefix[end] - prefix[start]) - target_work),
                                   abs((end - start) - target_ops), end))
        cuts.append(cut)
    cuts.append(n_ops)
    sizes = [b - a for a, b in zip(cuts, cuts[1:])]
    if any(size < minimum or size > maximum for size in sizes):
        raise AssertionError("internal error: cumulative-cycle partition violated size bounds")
    chunk_cycles = [prefix[b] - prefix[a] for a, b in zip(cuts, cuts[1:])]
    average_cycles = prefix[n_ops] / k
    deviation = sum(abs(value - average_cycles) for value in chunk_cycles)
    return cuts, {"compute_op_count": n_ops, "subgraph_count": k, "cuts": cuts[1:-1],
                  "chunk_sizes": sizes, "chunk_cycles": chunk_cycles,
                  "target_ops": target_ops, "minimum_ops": minimum, "maximum_ops": maximum,
                  "total_cycles": prefix[n_ops], "average_cycles_per_chunk": average_cycles,
                  "sum_absolute_cycle_deviation": deviation,
                  "cut_rule": "greedily choose feasible topological boundary closest to remaining-work/k; ties by target op length then lower boundary"}


def build_cycles_plan(graph: dict, num_cores: int, target_ops: int = 256,
                      minimum: int = 128, maximum: int = 384) -> tuple[dict, dict]:
    op_by_id, _ = operation_dependencies(graph)
    order = topological_ops(graph)
    cuts, parameters = cycles_cuts(graph, order, target_ops, minimum, maximum)
    subgraphs = [order[a:b] for a, b in zip(cuts, cuts[1:])]
    mapping = {op_id: subgraph_id for subgraph_id, members in enumerate(subgraphs) for op_id in members}
    plan = official_plan(mapping, greedy_assign(subgraphs, op_by_id, num_cores))
    validate_plan_coverage(plan, order)
    return plan, parameters

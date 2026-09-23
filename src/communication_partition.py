"""Bounded communication-aware cuts over the deterministic topological op order."""

from __future__ import annotations

from .assignment import greedy_assign
from .graph_io import COPY_OPS, operation_dependencies
from .plan_io import official_plan
from .scheduler import validate_plan_coverage
from .topology import topological_ops


ALGORITHM_VERSION = "p1_bounded_communication_cuts_v001"
TARGET_CHUNK_SIZE = 256
MIN_CHUNK_SIZE = 128
MAX_CHUNK_SIZE = 384
CUT_WINDOW = 32


def _boundary_costs(graph: dict, op_order: list[int]) -> list[int]:
    """Estimate distinct intermediate tensor bytes live across each cut.

    Only compute-op producer/consumer relationships are counted. Original
    COPY_IN/COPY_OUT edges are excluded; evaluator metrics remain authoritative.
    A tensor contributes once per crossed topological boundary.
    """
    op_by_id, _ = operation_dependencies(graph)
    position = {op_id: index for index, op_id in enumerate(op_order)}
    producers: dict[int, set[int]] = {}
    consumers: dict[int, set[int]] = {}
    tensor_by_id = {tensor["id"]: tensor for tensor in graph["tensors"]}
    for edge in graph["edges"]:
        source, target = edge["source"], edge["target"]
        if source in op_by_id and target in tensor_by_id:
            if op_by_id[source].get("op") not in COPY_OPS:
                producers.setdefault(target, set()).add(source)
        elif source in tensor_by_id and target in op_by_id:
            if op_by_id[target].get("op") not in COPY_OPS:
                consumers.setdefault(source, set()).add(target)

    diff = [0] * (len(op_order) + 2)
    for tensor_id in producers.keys() & consumers.keys():
        prod_positions = [position[op] for op in producers[tensor_id] if op in position]
        cons_positions = [position[op] for op in consumers[tensor_id] if op in position]
        if not prod_positions or not cons_positions:
            continue
        first_producer = min(prod_positions)
        last_consumer = max(cons_positions)
        if last_consumer <= first_producer:
            continue
        size = tensor_by_id[tensor_id].get("size", 0)
        if type(size) is not int or size < 0:
            raise ValueError(f"tensor {tensor_id} has invalid size")
        # A cut p separates indices [0,p) and [p,N).
        lo, hi = first_producer + 1, last_consumer
        diff[lo] += size
        diff[hi + 1] -= size
    costs = [0] * (len(op_order) + 1)
    running = 0
    for cut in range(1, len(op_order)):
        running += diff[cut]
        costs[cut] = running
    return costs


def communication_cuts(graph: dict, op_order: list[int] | None = None,
                       target: int = TARGET_CHUNK_SIZE,
                       minimum: int = MIN_CHUNK_SIZE,
                       maximum: int = MAX_CHUNK_SIZE,
                       window: int = CUT_WINDOW) -> tuple[list[int], dict]:
    """Find bounded cuts minimizing proxy bytes, with deterministic tie breaks.

    Candidate positions are within ``window`` ops of each equal-sized ideal
    cut. Dynamic programming minimizes (summed boundary bytes, summed distance
    from target chunk size, lexicographic cut tuple), subject to size bounds.
    """
    if type(target) is not int or target <= 0 or type(minimum) is not int or minimum <= 0:
        raise ValueError("target and minimum must be positive integers")
    if type(maximum) is not int or maximum < minimum or type(window) is not int or window < 0:
        raise ValueError("maximum must be >= minimum and window non-negative")
    if op_order is None:
        op_order = topological_ops(graph)
    n_ops = len(op_order)
    if n_ops == 0:
        return [0], {"compute_op_count": 0, "subgraph_count": 0, "cuts": [],
                     "estimated_boundary_bytes": 0, "target_chunk_size": target,
                     "min_chunk_size": minimum, "max_chunk_size": maximum,
                     "cut_window": window}
    min_k = (n_ops + maximum - 1) // maximum
    max_k = max(1, n_ops // minimum)
    if min_k > max_k:
        raise ValueError("no partition can satisfy the requested chunk size bounds")
    ideal_k = max(1, round(n_ops / target))
    k = min(max(ideal_k, min_k), max_k)
    costs = _boundary_costs(graph, op_order)

    # State maps the previous cut position to (communication, size deviation, cuts).
    states: dict[int, tuple[int, int, tuple[int, ...]]] = {0: (0, 0, ())}
    for cut_idx in range(1, k):
        ideal = round(cut_idx * n_ops / k)
        lower = max(cut_idx * minimum, n_ops - (k - cut_idx) * maximum,
                    ideal - window, 1)
        upper = min(cut_idx * maximum, n_ops - (k - cut_idx) * minimum,
                    ideal + window, n_ops - 1)
        candidates = range(lower, upper + 1)
        next_states: dict[int, tuple[int, int, tuple[int, ...]]] = {}
        for cut in candidates:
            best = None
            for previous, value in states.items():
                chunk_size = cut - previous
                if not minimum <= chunk_size <= maximum:
                    continue
                proposal = (value[0] + costs[cut],
                            value[1] + abs(chunk_size - target), value[2] + (cut,))
                if best is None or proposal < best:
                    best = proposal
            if best is not None:
                next_states[cut] = best
        states = next_states
        if not states:
            raise ValueError(f"no feasible bounded cut sequence at boundary {cut_idx}/{k}")

    best_final = None
    for previous, value in states.items():
        final_size = n_ops - previous
        if not minimum <= final_size <= maximum:
            continue
        proposal = (value[0], value[1] + abs(final_size - target), value[2])
        if best_final is None or proposal < best_final:
            best_final = proposal
    if best_final is None:
        if k == 1 and minimum <= n_ops <= maximum:
            best_final = (0, abs(n_ops - target), ())
        else:
            raise ValueError("no feasible final chunk")
    cuts = [0, *best_final[2], n_ops]
    chunk_sizes = [b - a for a, b in zip(cuts, cuts[1:])]
    if any(size < minimum or size > maximum for size in chunk_sizes):
        raise AssertionError("internal error: chunk bound violated")
    return cuts, {"compute_op_count": n_ops, "subgraph_count": len(chunk_sizes),
                  "cuts": cuts[1:-1], "chunk_sizes": chunk_sizes,
                  "estimated_boundary_bytes": best_final[0],
                  "chunk_size_deviation_from_target": best_final[1],
                  "target_chunk_size": target, "min_chunk_size": minimum,
                  "max_chunk_size": maximum, "cut_window": window,
                  "cut_cost_rule": "distinct intermediate tensor bytes crossing each candidate topological boundary; COPY ops excluded"}


def build_communication_plan(graph: dict, num_cores: int,
                             target: int = TARGET_CHUNK_SIZE,
                             minimum: int = MIN_CHUNK_SIZE,
                             maximum: int = MAX_CHUNK_SIZE,
                             window: int = CUT_WINDOW) -> tuple[dict, dict]:
    op_by_id, _ = operation_dependencies(graph)
    order = topological_ops(graph)
    cuts, parameters = communication_cuts(graph, order, target, minimum, maximum, window)
    subgraphs = [order[a:b] for a, b in zip(cuts, cuts[1:])]
    mapping = {op_id: subgraph_id for subgraph_id, members in enumerate(subgraphs) for op_id in members}
    schedules = greedy_assign(subgraphs, op_by_id, num_cores)
    plan = official_plan(mapping, schedules)
    validate_plan_coverage(plan, order)
    return plan, parameters

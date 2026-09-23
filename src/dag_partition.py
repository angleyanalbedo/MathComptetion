"""Strong-edge atom aggregation with an explicit global contracted-DAG check."""

from __future__ import annotations

from collections import deque

from .assignment import greedy_assign
from .graph_io import COPY_OPS, operation_dependencies
from .plan_io import official_plan
from .scheduler import validate_plan_coverage
from .topology import topological_ops


ALGORITHM_VERSION = "p1_dag_strong_edge_aggregation_v001"
ATOM_SIZE = 128
TARGET_SIZE = 256
MIN_CLUSTER_SIZE = 128
MAX_CLUSTER_SIZE = 384


def _atom_edges(graph: dict, order: list[int], atom_size: int) -> tuple[set[tuple[int, int]], dict[tuple[int, int], int]]:
    atom_of = {op_id: idx // atom_size for idx, op_id in enumerate(order)}
    atom_edges: set[tuple[int, int]] = set()
    op_by_id, succs = operation_dependencies(graph)
    compute = set(order)
    for source in order:
        queue = deque(succs[source])
        visited: set[int] = set()
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            if node in compute:
                a, b = atom_of[source], atom_of[node]
                if a != b:
                    atom_edges.add((a, b))
            elif op_by_id[node].get("op") in COPY_OPS:
                queue.extend(succs[node])

    tensor_by_id = {tensor["id"]: tensor for tensor in graph["tensors"]}
    producers: dict[int, set[int]] = {}
    consumers: dict[int, set[int]] = {}
    for edge in graph["edges"]:
        source, target = edge["source"], edge["target"]
        if source in op_by_id and target in tensor_by_id and source in compute:
            producers.setdefault(target, set()).add(source)
        elif source in tensor_by_id and target in op_by_id and target in compute:
            consumers.setdefault(source, set()).add(target)
    weights: dict[tuple[int, int], int] = {}
    for tensor_id in producers.keys() & consumers.keys():
        size = tensor_by_id[tensor_id].get("size", 0)
        if type(size) is not int or size < 0:
            raise ValueError(f"tensor {tensor_id} has invalid size")
        atom_pairs = {(atom_of[p], atom_of[c]) for p in producers[tensor_id]
                      for c in consumers[tensor_id] if atom_of[p] != atom_of[c]}
        for a, b in atom_pairs:
            key = (min(a, b), max(a, b))
            weights[key] = weights.get(key, 0) + size
    return atom_edges, weights


def _acyclic(clusters: dict[int, set[int]], atom_edges: set[tuple[int, int]]) -> bool:
    atom_cluster = {atom: cluster for cluster, atoms in clusters.items() for atom in atoms}
    succs = {cluster: set() for cluster in clusters}
    indegree = {cluster: 0 for cluster in clusters}
    for source, target in atom_edges:
        left, right = atom_cluster[source], atom_cluster[target]
        if left != right and right not in succs[left]:
            succs[left].add(right)
            indegree[right] += 1
    ready = deque(sorted(cluster for cluster, count in indegree.items() if count == 0))
    visited = 0
    while ready:
        current = ready.popleft()
        visited += 1
        for nxt in sorted(succs[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    return visited == len(clusters)


def dag_strong_edge_partition(graph: dict, atom_size: int = ATOM_SIZE,
                              target_size: int = TARGET_SIZE,
                              minimum: int = MIN_CLUSTER_SIZE,
                              maximum: int = MAX_CLUSTER_SIZE) -> tuple[dict[int, int], list[list[int]], dict]:
    if any(type(value) is not int or value <= 0 for value in (atom_size, target_size, minimum, maximum)):
        raise ValueError("partition sizes must be positive integers")
    if maximum < minimum:
        raise ValueError("maximum must be >= minimum")
    order = topological_ops(graph)
    n_ops = len(order)
    if n_ops == 0:
        return {}, [], {"compute_op_count": 0, "subgraph_count": 0, "merges": [], "dag_rejections": 0}
    min_k = (n_ops + maximum - 1) // maximum
    max_k = max(1, n_ops // minimum)
    if min_k > max_k:
        raise ValueError("no target partition can satisfy cluster-size bounds")
    target_k = min(max(round(n_ops / target_size), min_k), max_k)
    atom_members = [order[start:start + atom_size] for start in range(0, n_ops, atom_size)]
    atom_sizes = [len(members) for members in atom_members]
    atom_edges, edge_weights = _atom_edges(graph, order, atom_size)
    clusters: dict[int, set[int]] = {idx: {idx} for idx in range(len(atom_members))}
    cluster_sizes = {idx: atom_sizes[idx] for idx in range(len(atom_members))}
    cluster_min_order = {idx: idx * atom_size for idx in range(len(atom_members))}
    next_cluster_id = len(clusters)
    dag_rejections = 0
    merge_log = []

    while len(clusters) > target_k:
        cluster_ids = sorted(clusters, key=lambda cid: (cluster_min_order[cid], cid))
        candidates = []
        for i, left in enumerate(cluster_ids):
            for right in cluster_ids[i + 1:]:
                merged_size = cluster_sizes[left] + cluster_sizes[right]
                if merged_size > maximum:
                    continue
                if len(clusters) - 1 == target_k and merged_size < minimum:
                    continue
                weight = 0
                for a in clusters[left]:
                    for b in clusters[right]:
                        weight += edge_weights.get((min(a, b), max(a, b)), 0)
                candidates.append((-weight, cluster_min_order[left], cluster_min_order[right], left, right))
        candidates.sort()
        accepted = None
        for neg_weight, _left_order, _right_order, left, right in candidates:
            proposed = {cid: atoms for cid, atoms in clusters.items() if cid not in (left, right)}
            proposed[next_cluster_id] = clusters[left] | clusters[right]
            if not _acyclic(proposed, atom_edges):
                dag_rejections += 1
                continue
            accepted = (neg_weight, left, right, proposed)
            break
        if accepted is None:
            raise ValueError(f"no DAG-preserving merge satisfies size bounds at {len(clusters)} clusters")
        neg_weight, left, right, proposed = accepted
        merged_size = cluster_sizes[left] + cluster_sizes[right]
        merge_log.append({"left_cluster": left, "right_cluster": right,
                          "merged_cluster": next_cluster_id, "edge_strength_bytes": -neg_weight,
                          "merged_op_count": merged_size,
                          "minimum_topological_index": min(cluster_min_order[left], cluster_min_order[right])})
        old_min = min(cluster_min_order[left], cluster_min_order[right])
        del cluster_sizes[left], cluster_sizes[right]
        del cluster_min_order[left], cluster_min_order[right]
        cluster_sizes[next_cluster_id] = merged_size
        cluster_min_order[next_cluster_id] = old_min
        clusters = proposed
        next_cluster_id += 1

    if not _acyclic(clusters, atom_edges):
        raise AssertionError("internal error: final contracted graph is cyclic")
    ordered_clusters = sorted(clusters, key=lambda cid: (cluster_min_order[cid], cid))
    cluster_to_subgraph = {cluster: subgraph for subgraph, cluster in enumerate(ordered_clusters)}
    position = {op_id: idx for idx, op_id in enumerate(order)}
    node_to_subgraph: dict[int, int] = {}
    subgraphs: list[list[int]] = [[] for _ in ordered_clusters]
    for cluster in ordered_clusters:
        sid = cluster_to_subgraph[cluster]
        for atom in clusters[cluster]:
            for op_id in atom_members[atom]:
                node_to_subgraph[op_id] = sid
                subgraphs[sid].append(op_id)
        subgraphs[sid].sort(key=position.__getitem__)
    params = {"compute_op_count": n_ops, "target_subgraph_count": target_k,
              "actual_subgraph_count": len(subgraphs), "atom_size": atom_size,
              "target_size": target_size, "minimum_cluster_size": minimum,
              "maximum_cluster_size": maximum,
              "cluster_op_counts": [len(group) for group in subgraphs],
              "atom_directed_edge_count": len(atom_edges),
              "atom_communication_pair_count": len(edge_weights),
              "dag_rejected_merge_candidates": dag_rejections,
              "merge_log": merge_log,
              "merge_rule": "highest summed distinct-tensor bytes between atom groups; deterministic topo tie break; reject any merge making the entire contracted DAG cyclic"}
    return node_to_subgraph, subgraphs, params


def build_dag_partition_plan(graph: dict, num_cores: int,
                             atom_size: int = ATOM_SIZE,
                             target_size: int = TARGET_SIZE,
                             minimum: int = MIN_CLUSTER_SIZE,
                             maximum: int = MAX_CLUSTER_SIZE) -> tuple[dict, dict]:
    op_by_id, _ = operation_dependencies(graph)
    node_to_subgraph, subgraphs, params = dag_strong_edge_partition(
        graph, atom_size, target_size, minimum, maximum)
    schedules = greedy_assign(subgraphs, op_by_id, num_cores)
    plan = official_plan(node_to_subgraph, schedules)
    validate_plan_coverage(plan, topological_ops(graph))
    return plan, params

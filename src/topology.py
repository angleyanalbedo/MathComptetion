"""Stable operation-DAG topological ordering."""

from __future__ import annotations

import heapq

from .graph_io import COPY_OPS, GraphError, operation_dependencies


def topological_ops(graph: dict, *, include_copy: bool = False) -> list[int]:
    """Kahn sort with op ID as the deterministic ready-queue tie breaker."""
    op_by_id, succs = operation_dependencies(graph)
    indegree = {op_id: 0 for op_id in op_by_id}
    for successors in succs.values():
        for successor in successors:
            indegree[successor] += 1
    ready = [op_id for op_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        op_id = heapq.heappop(ready)
        order.append(op_id)
        for successor in sorted(succs[op_id]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                heapq.heappush(ready, successor)
    if len(order) != len(op_by_id):
        unresolved = sorted(op_id for op_id, degree in indegree.items() if degree)
        raise GraphError(f"operation dependency cycle; unresolved op ids={unresolved[:32]}")
    if include_copy:
        return order
    return [op_id for op_id in order if op_by_id[op_id].get("op") not in COPY_OPS]

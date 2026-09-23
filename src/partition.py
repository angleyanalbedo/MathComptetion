"""Contiguous fixed-size partitioning of topologically ordered compute ops."""

from __future__ import annotations


def contiguous_partition(op_order: list[int], subgraph_size: int = 64) -> tuple[dict[int, int], list[list[int]]]:
    if type(subgraph_size) is not int or subgraph_size <= 0:
        raise ValueError("subgraph_size must be a positive integer")
    node_to_subgraph: dict[int, int] = {}
    subgraphs: list[list[int]] = []
    for start in range(0, len(op_order), subgraph_size):
        subgraph_id = len(subgraphs)
        members = op_order[start:start + subgraph_size]
        subgraphs.append(members)
        for op_id in members:
            node_to_subgraph[op_id] = subgraph_id
    return node_to_subgraph, subgraphs

"""Read contest JSON and construct operation-level dependencies."""

from __future__ import annotations

import json
from pathlib import Path


COPY_OPS = {"COPY_IN", "COPY_OUT"}


class GraphError(ValueError):
    """Input graph cannot be represented as a valid operation DAG."""


def load_graph(path: str | Path) -> dict:
    path = Path(path)
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphError(f"cannot read graph {path}: {exc}") from exc
    if not isinstance(graph, dict):
        raise GraphError("graph root must be a JSON object")
    for name in ("ops", "tensors", "edges"):
        if not isinstance(graph.get(name), list):
            raise GraphError(f"graph.{name} must be a list")
    return graph


def operation_dependencies(graph: dict) -> tuple[dict[int, dict], dict[int, set[int]]]:
    """Build the complete op DAG, collapsing tensor edges but keeping COPY ops.

    For each tensor, every producing op precedes every consuming op. This retains
    paths that pass through tensor nodes and any COPY_IN/COPY_OUT operations.
    Direct op-to-op edges are also preserved.
    """
    ops = graph.get("ops")
    tensors = graph.get("tensors")
    edges = graph.get("edges")
    if not isinstance(ops, list) or not isinstance(tensors, list) or not isinstance(edges, list):
        raise GraphError("graph must contain ops, tensors, and edges lists")

    op_by_id: dict[int, dict] = {}
    tensor_ids: set[int] = set()
    all_ids: set[int] = set()
    for item in ops:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            raise GraphError("each op must be an object with an integer id")
        op_id = item["id"]
        if op_id < 0 or op_id in all_ids:
            raise GraphError(f"invalid or duplicate operation id: {op_id}")
        all_ids.add(op_id)
        op_by_id[op_id] = item
    for item in tensors:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            raise GraphError("each tensor must be an object with an integer id")
        tensor_id = item["id"]
        if tensor_id < 0 or tensor_id in all_ids:
            raise GraphError(f"invalid or duplicate tensor id: {tensor_id}")
        all_ids.add(tensor_id)
        tensor_ids.add(tensor_id)

    succs = {op_id: set() for op_id in op_by_id}
    producers: dict[int, set[int]] = {}
    consumers: dict[int, set[int]] = {}
    seen_edges: set[tuple[int, int]] = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise GraphError("each edge must be an object")
        source, target = edge.get("source"), edge.get("target")
        if type(source) is not int or type(target) is not int:
            raise GraphError("edge endpoints must be integer ids")
        if source not in all_ids or target not in all_ids:
            raise GraphError(f"edge references unknown id: {source} -> {target}")
        pair = (source, target)
        if pair in seen_edges:
            raise GraphError(f"duplicate edge: {source} -> {target}")
        seen_edges.add(pair)
        source_is_op = source in op_by_id
        target_is_op = target in op_by_id
        if source_is_op and target_is_op:
            succs[source].add(target)
        elif source_is_op and target in tensor_ids:
            producers.setdefault(target, set()).add(source)
        elif source in tensor_ids and target_is_op:
            consumers.setdefault(source, set()).add(target)
        else:
            raise GraphError(f"unsupported tensor-to-tensor edge: {source} -> {target}")

    for tensor_id in producers.keys() | consumers.keys():
        for producer in producers.get(tensor_id, ()):
            succs[producer].update(consumers.get(tensor_id, ()))
    for op_id, successors in succs.items():
        if op_id in successors:
            raise GraphError(f"self dependency at op {op_id}")
    return op_by_id, succs

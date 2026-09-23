#!/usr/bin/env python3
"""Profile contest DAG JSON cases and emit JSON/CSV workload summaries."""

from __future__ import annotations

import argparse
import csv
import heapq
import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


COPY_OPS = {"COPY_IN", "COPY_OUT"}
PIPES = ("PIPE_M", "PIPE_V", "PIPE_MTE2", "PIPE_MTE3")


def _topological_order(op_ids: list[int], predecessors: dict[int, set[int]],
                       successors: dict[int, set[int]]) -> list[int]:
    indegree = {op_id: len(predecessors[op_id]) for op_id in op_ids}
    ready = [op_id for op_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        op_id = heapq.heappop(ready)
        order.append(op_id)
        for nxt in successors[op_id]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) != len(op_ids):
        raise ValueError("operation dependency graph contains a cycle")
    return order


def analyze(path: Path) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    tensors = {int(item["id"]): item for item in graph["tensors"]}
    ops = {int(item["id"]): item for item in graph["ops"]}
    op_ids = sorted(ops)
    tensor_inputs: dict[int, list[int]] = defaultdict(list)
    tensor_outputs: dict[int, list[int]] = defaultdict(list)
    for edge in graph["edges"]:
        src, dst = int(edge["source"]), int(edge["target"])
        if src in tensors and dst in ops:
            tensor_inputs[dst].append(src)
        elif src in ops and dst in tensors:
            tensor_outputs[src].append(dst)
        else:
            raise ValueError(f"invalid edge endpoint types: {src} -> {dst}")

    consumers: dict[int, set[int]] = defaultdict(set)
    producer: dict[int, int] = {}
    for op_id, tids in tensor_inputs.items():
        for tid in tids:
            consumers[tid].add(op_id)
    for op_id, tids in tensor_outputs.items():
        for tid in tids:
            if tid in producer:
                raise ValueError(f"tensor {tid} has multiple producers")
            producer[tid] = op_id

    predecessors: dict[int, set[int]] = {op_id: set() for op_id in op_ids}
    successors: dict[int, set[int]] = {op_id: set() for op_id in op_ids}
    for tid, src_op in producer.items():
        for dst_op in consumers.get(tid, set()):
            if src_op != dst_op:
                successors[src_op].add(dst_op)
                predecessors[dst_op].add(src_op)
    order = _topological_order(op_ids, predecessors, successors)
    rank = {op_id: i for i, op_id in enumerate(order)}

    op_types = Counter(str(op.get("op", "UNKNOWN")) for op in ops.values())
    pipe_cycles = Counter()
    compute_cycles = 0
    copy_in_ops = copy_out_ops = 0
    original_copy_bytes = 0
    for op_id, op in ops.items():
        kind = str(op.get("op", "UNKNOWN"))
        cycles = int(op.get("cycles", 0))
        if kind not in COPY_OPS:
            pipe_cycles[str(op.get("pipe", "UNKNOWN"))] += cycles
            compute_cycles += cycles
        if kind == "COPY_IN":
            copy_in_ops += 1
            original_copy_bytes += sum(int(tensors[t]["size"]) for t in tensor_inputs[op_id]
                                       if str(tensors[t].get("pos", "")) == "DDR")
        elif kind == "COPY_OUT":
            copy_out_ops += 1
            original_copy_bytes += sum(int(tensors[t]["size"]) for t in tensor_outputs[op_id]
                                       if str(tensors[t].get("pos", "")) == "DDR")

    cp_cycles: dict[int, int] = {}
    cp_ops: dict[int, int] = {}
    for op_id in order:
        weight = int(ops[op_id].get("cycles", 0)) if str(ops[op_id].get("op")) not in COPY_OPS else 0
        cp_cycles[op_id] = weight + max((cp_cycles[p] for p in predecessors[op_id]), default=0)
        cp_ops[op_id] = 1 + max((cp_ops[p] for p in predecessors[op_id]), default=0)

    # Approximate storage occupancy along one deterministic topological order.
    starts: dict[int, int] = {}
    ends: dict[int, int] = {}
    for tid, tensor in tensors.items():
        if str(tensor.get("pos", "")) not in {"L1", "UB"}:
            continue
        if tid in producer:
            starts[tid] = rank[producer[tid]]
        elif consumers.get(tid):
            starts[tid] = min(rank[c] for c in consumers[tid])
        else:
            continue
        ends[tid] = max((rank[c] for c in consumers.get(tid, set())), default=starts[tid])
    live_peak = {"L1": 0, "UB": 0}
    for pos in live_peak:
        events: dict[int, int] = defaultdict(int)
        for tid, start in starts.items():
            if str(tensors[tid].get("pos")) == pos:
                size = int(tensors[tid]["size"])
                events[start] += size
                events[ends[tid] + 1] -= size
        current = 0
        for point in sorted(events):
            current += events[point]
            live_peak[pos] = max(live_peak[pos], current)

    fanout_tensors = [t for t in tensors if len(consumers.get(t, set())) > 1]
    reusable_bytes = sum(int(tensors[t]["size"]) for t in fanout_tensors)
    tensor_bytes = Counter()
    for tensor in tensors.values():
        tensor_bytes[str(tensor.get("pos", "UNKNOWN"))] += int(tensor["size"])

    return {
        "case": path.stem,
        "tensor_count": len(tensors),
        "op_count": len(ops),
        "compute_op_count": sum(count for kind, count in op_types.items() if kind not in COPY_OPS),
        "edge_count": len(graph["edges"]),
        "op_type_counts": dict(sorted(op_types.items())),
        "pipe_compute_cycles": {pipe: int(pipe_cycles.get(pipe, 0)) for pipe in PIPES},
        "compute_cycles_total": compute_cycles,
        "compute_only_critical_path_cycles": max(cp_cycles.values(), default=0),
        "op_dependency_depth": max(cp_ops.values(), default=0),
        "copy_in_ops": copy_in_ops,
        "copy_out_ops": copy_out_ops,
        "original_graph_copy_bytes": original_copy_bytes,
        "tensor_bytes_by_position": dict(sorted(tensor_bytes.items())),
        "multi_consumer_tensor_count": len(fanout_tensors),
        "multi_consumer_tensor_bytes": reusable_bytes,
        "topological_order_l1_live_bytes_estimate": live_peak["L1"],
        "topological_order_ub_live_bytes_estimate": live_peak["UB"],
        "analysis_limits": [
            "critical path excludes data-transfer time, pipe contention, sync waits, and spills",
            "live-byte peaks use one deterministic topological order and are not evaluator peaks",
            "fanout bytes indicate reuse opportunities, not guaranteed cache hits",
        ],
    }


def collect_inputs(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if source.is_dir():
        return sorted(source.glob("case_*.json"))
    raise FileNotFoundError(source)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="one contest graph JSON or a directory of case_*.json")
    parser.add_argument("--out-dir", type=Path, required=True, help="directory for profile.json and profile.csv")
    args = parser.parse_args()
    files = collect_inputs(args.input)
    if not files:
        parser.error(f"no case_*.json files found in {args.input}")
    profiles = [analyze(path) for path in files]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "profile.json").write_text(
        json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = [
        "case", "tensor_count", "op_count", "compute_op_count", "edge_count",
        "compute_cycles_total", "compute_only_critical_path_cycles", "op_dependency_depth",
        "copy_in_ops", "copy_out_ops", "original_graph_copy_bytes",
        "multi_consumer_tensor_count", "multi_consumer_tensor_bytes",
        "topological_order_l1_live_bytes_estimate", "topological_order_ub_live_bytes_estimate",
        *[f"{pipe}_compute_cycles" for pipe in PIPES],
    ]
    with (args.out_dir / "profile.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in profiles:
            row = {key: item.get(key) for key in columns if not key.endswith("_compute_cycles")}
            row.update({f"{pipe}_compute_cycles": item["pipe_compute_cycles"][pipe] for pipe in PIPES})
            writer.writerow(row)
    print(f"Analyzed {len(profiles)} case(s); wrote {args.out_dir / 'profile.csv'} and profile.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

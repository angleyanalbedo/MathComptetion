from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.communication_partition import (  # noqa: E402
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    build_communication_plan,
    communication_cuts,
)
from stub_multicore_cut_and_schedule import validate_multicore_plan  # noqa: E402


def chain_graph(count: int = 768) -> dict:
    ops = [{"id": i, "op": "Compute", "pipe": "PIPE_M", "cycles": 1}
           for i in range(count)]
    tensors = []
    edges = []

    def connect(tensor_id: int, source: int, target: int, size: int) -> None:
        tensors.append({"id": tensor_id, "size": size, "pos": "DDR"})
        edges.extend(({"source": source, "target": tensor_id},
                      {"source": tensor_id, "target": target}))

    for i in range(count - 1):
        connect(10000 + i, i, i + 1, 1)
    # High-byte intermediate values become dead just after the equal-size cuts.
    connect(20000, 100, 270, 10000)
    connect(20001, 300, 540, 20000)
    return {"ops": ops, "tensors": tensors, "edges": edges}


class CommunicationPartitionTests(unittest.TestCase):
    def test_cuts_are_deterministic_bounded_and_reduce_proxy_cost(self) -> None:
        graph = chain_graph()
        first, params = communication_cuts(graph)
        second, _ = communication_cuts(graph)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4)
        sizes = [b - a for a, b in zip(first, first[1:])]
        self.assertTrue(all(MIN_CHUNK_SIZE <= size <= MAX_CHUNK_SIZE for size in sizes))
        costs = __import__("src.communication_partition", fromlist=["_boundary_costs"])._boundary_costs
        boundary_costs = costs(graph, list(range(768)))
        self.assertLess(params["estimated_boundary_bytes"], boundary_costs[256] + boundary_costs[512])

    def test_built_plan_passes_official_structural_validation(self) -> None:
        graph = chain_graph(768)
        plan, params = build_communication_plan(graph, 4)
        validate_multicore_plan(graph, plan)
        self.assertEqual(params["subgraph_count"], len(set(plan["node_to_subgraph"].values())))

    def test_invalid_chunk_bounds_rejected(self) -> None:
        with self.assertRaises(ValueError):
            communication_cuts(chain_graph(), target=256, minimum=384, maximum=128)


if __name__ == "__main__":
    unittest.main()

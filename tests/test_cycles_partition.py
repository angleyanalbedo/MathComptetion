from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.cycles_partition import build_cycles_plan, cycles_cuts  # noqa: E402
from stub_multicore_cut_and_schedule import validate_multicore_plan  # noqa: E402


def workload_graph() -> dict:
    count = 768
    ops = [{"id": i, "op": "Compute", "pipe": "PIPE_M",
            "cycles": 40 if 250 <= i < 320 else (5 if 500 <= i < 570 else 1)}
           for i in range(count)]
    tensors, edges = [], []
    for i in range(count - 1):
        tensor_id = 10000 + i
        tensors.append({"id": tensor_id, "size": 4, "pos": "DDR"})
        edges.extend(({"source": i, "target": tensor_id},
                      {"source": tensor_id, "target": i + 1}))
    return {"ops": ops, "tensors": tensors, "edges": edges}


class CyclesPartitionTests(unittest.TestCase):
    def test_cuts_are_repeatable_bounded_and_balance_chunk_work(self) -> None:
        graph = workload_graph()
        cuts, params = cycles_cuts(graph)
        self.assertEqual(cuts, cycles_cuts(graph)[0])
        self.assertEqual(len(cuts), 4)
        self.assertTrue(all(128 <= size <= 384 for size in params["chunk_sizes"]))
        self.assertEqual(sum(params["chunk_cycles"]), params["total_cycles"])
        self.assertTrue(all(type(cut) is int for cut in cuts))

    def test_built_plan_passes_official_validation(self) -> None:
        graph = workload_graph()
        plan, _ = build_cycles_plan(graph, 4)
        validate_multicore_plan(graph, plan)


if __name__ == "__main__":
    unittest.main()

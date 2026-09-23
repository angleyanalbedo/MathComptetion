from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.dag_partition import build_dag_partition_plan, dag_strong_edge_partition  # noqa: E402
from stub_multicore_cut_and_schedule import validate_multicore_plan  # noqa: E402


def chain_with_long_edge() -> dict:
    ops = [{"id": i, "op": "Compute", "pipe": "PIPE_M", "cycles": 1} for i in range(12)]
    tensors = [{"id": 100, "size": 10000, "pos": "DDR"}]
    edges = [{"source": i, "target": i + 1} for i in range(11)]
    edges.extend(({"source": 0, "target": 100}, {"source": 100, "target": 4}))
    return {"ops": ops, "tensors": tensors, "edges": edges}


class DagPartitionTests(unittest.TestCase):
    def test_global_dag_check_rejects_merge_across_an_intervening_path(self) -> None:
        graph = chain_with_long_edge()
        mapping, groups, params = dag_strong_edge_partition(
            graph, atom_size=2, target_size=4, minimum=2, maximum=6)
        self.assertGreater(params["dag_rejected_merge_candidates"], 0)
        self.assertEqual(set(mapping), set(range(12)))
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(2 <= len(group) <= 6 for group in groups))
        self.assertEqual((mapping, groups), dag_strong_edge_partition(
            graph, atom_size=2, target_size=4, minimum=2, maximum=6)[:2])

    def test_plan_passes_official_validation(self) -> None:
        graph = chain_with_long_edge()
        plan, _ = build_dag_partition_plan(graph, 3, atom_size=2, target_size=4,
                                           minimum=2, maximum=6)
        validate_multicore_plan(graph, plan)


if __name__ == "__main__":
    unittest.main()

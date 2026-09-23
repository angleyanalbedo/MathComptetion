from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.scheduler import build_plan  # noqa: E402
from src.topology import topological_ops  # noqa: E402
from stub_multicore_cut_and_schedule import validate_multicore_plan  # noqa: E402


def make_graph(op_specs: list[tuple[int, str, int]], dependencies: list[tuple[int, int]]) -> dict:
    ops = [
        {"id": op_id, "op": kind, "pipe": "PIPE_M", "cycles": cycles}
        for op_id, kind, cycles in op_specs
    ]
    tensors = []
    edges = []
    for index, (source, target) in enumerate(dependencies):
        tensor_id = 1000 + index
        tensors.append({"id": tensor_id, "size": 4, "pos": "DDR"})
        edges.extend(({"source": source, "target": tensor_id},
                      {"source": tensor_id, "target": target}))
    return {"ops": ops, "tensors": tensors, "edges": edges}


class BaselineTests(unittest.TestCase):
    def test_copy_path_is_preserved_then_copy_ops_are_filtered(self) -> None:
        graph = make_graph(
            [(0, "COPY_IN", 0), (1, "Compute", 4), (2, "Compute", 8), (3, "COPY_OUT", 0)],
            [(0, 1), (1, 2), (2, 3)],
        )
        self.assertEqual(topological_ops(graph, include_copy=True), [0, 1, 2, 3])
        self.assertEqual(topological_ops(graph), [1, 2])

    def test_diamond_join_and_ready_tie_breaking(self) -> None:
        graph = make_graph(
            [(0, "Compute", 1), (1, "Compute", 1), (2, "Compute", 1),
             (3, "Compute", 1), (4, "Compute", 1)],
            [(0, 1), (0, 2), (1, 3), (2, 3)],
        )
        self.assertEqual(topological_ops(graph), [0, 1, 2, 3, 4])
        plan = build_plan(graph, 3, subgraph_size=2)
        validate_multicore_plan(graph, plan)
        self.assertEqual(plan["node_to_subgraph"], {"0": 0, "1": 0, "2": 1, "3": 1, "4": 2})
        self.assertEqual([core for core in plan["core_schedules"] if core], [[0], [1], [2]])

    def test_independent_ops_are_sorted_by_id_and_repeatable(self) -> None:
        graph = make_graph([(9, "Compute", 3), (2, "Compute", 4), (5, "Compute", 7)], [])
        self.assertEqual(topological_ops(graph), [2, 5, 9])
        for cores in (2, 3, 4, 5):
            first = build_plan(graph, cores, subgraph_size=1)
            second = build_plan(graph, cores, subgraph_size=1)
            self.assertEqual(first, second)
            validate_multicore_plan(graph, first)
            self.assertEqual(len(first["core_schedules"]), cores)

    def test_cycles_are_rejected(self) -> None:
        graph = make_graph([(0, "Compute", 1), (1, "Compute", 1)], [(0, 1), (1, 0)])
        with self.assertRaisesRegex(ValueError, "cycle"):
            topological_ops(graph)

    def test_tail_subgraph_and_greedy_core_load_tie(self) -> None:
        graph = make_graph(
            [(i, "Compute", cycles) for i, cycles in enumerate((5, 5, 4, 4, 1))],
            [(i, i + 1) for i in range(4)],
        )
        plan = build_plan(graph, 2, subgraph_size=2)
        validate_multicore_plan(graph, plan)
        self.assertEqual(plan["node_to_subgraph"], {"0": 0, "1": 0, "2": 1, "3": 1, "4": 2})
        self.assertEqual(plan["core_schedules"], [[0], [1, 2]])


if __name__ == "__main__":
    unittest.main()

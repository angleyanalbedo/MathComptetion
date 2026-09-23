from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.dependency_schedule import build_predecessors, list_schedule  # noqa: E402
from stub_multicore_cut_and_schedule import validate_multicore_plan  # noqa: E402


class DependencyScheduleTests(unittest.TestCase):
    def test_multiple_predecessors_use_max_release_not_sum(self) -> None:
        workloads = {0: 10, 1: 10, 2: 5, 3: 5}
        predecessors = {0: set(), 1: set(), 2: {0}, 3: {1}}
        first, estimate = list_schedule(workloads, predecessors, 2, cross_core_wait=100, same_core_wait=1)
        self.assertEqual(first, [[0, 2], [1, 3]])
        self.assertEqual(estimate["estimated_makespan"], 16)
        self.assertEqual(first, list_schedule(workloads, predecessors, 2, 100, 1)[0])

    def test_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cycle"):
            list_schedule({0: 1, 1: 1}, {0: {1}, 1: {0}}, 2, 0, 0)

    def test_copy_nodes_are_contracted_between_compute_tasks(self) -> None:
        graph = {"ops": [
                    {"id": 0, "op": "Compute", "pipe": "PIPE_M", "cycles": 10},
                    {"id": 1, "op": "COPY_OUT", "pipe": "PIPE_MTE3", "cycles": 1},
                    {"id": 2, "op": "Compute", "pipe": "PIPE_M", "cycles": 5}],
                 "tensors": [],
                 "edges": [{"source": 0, "target": 1}, {"source": 1, "target": 2}]}
        workloads, preds = build_predecessors(graph, {"0": 0, "2": 1})
        self.assertEqual(workloads, {0: 10, 1: 5})
        self.assertEqual(preds, {0: set(), 1: {0}})
        schedules, _ = list_schedule(workloads, preds, 2, 4, 1)
        plan = {"node_to_subgraph": {"0": 0, "2": 1}, "core_schedules": schedules}
        validate_multicore_plan(graph, plan)


if __name__ == "__main__":
    unittest.main()

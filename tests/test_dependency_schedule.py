from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "official" / "code"))

from src.dependency_schedule import build_pipe_workloads, build_predecessors, list_schedule  # noqa: E402
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

    def test_critical_path_priority_is_deterministic_and_prioritizes_long_tail(self) -> None:
        workloads = {0: 1, 1: 50, 2: 1, 3: 100, 4: 1, 5: 1}
        predecessors = {0: set(), 1: set(), 2: set(), 3: {0}, 4: {1}, 5: {2}}
        schedules, estimate = list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="critical_path")
        again, again_estimate = list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="critical_path")
        self.assertEqual(schedules, again)
        self.assertEqual(estimate, again_estimate)
        self.assertEqual(estimate["assignment_order"][0], 0)
        self.assertEqual(estimate["critical_path_tail_cycles"]["0"], 101)

    def test_successor_work_priority_counts_unique_descendants_and_differs_from_critical_path(self) -> None:
        workloads = {0: 1, 1: 1, 2: 60, 3: 60, 4: 100}
        predecessors = {0: set(), 1: set(), 2: {0}, 3: {0}, 4: {1}}
        cp_order = list_schedule(workloads, predecessors, 2, 0, 0,
                                 priority_mode="critical_path")[1]["assignment_order"]
        sw_schedules, sw_meta = list_schedule(workloads, predecessors, 2, 0, 0,
                                              priority_mode="successor_work")
        self.assertEqual(cp_order[0], 1)
        self.assertEqual(sw_meta["assignment_order"][0], 0)
        self.assertEqual(sw_meta["unique_descendant_work_cycles"]["0"], 120)
        self.assertEqual(sw_schedules, list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="successor_work")[0])

    def test_pipe_priority_accounts_for_cube_vector_overlap_and_is_deterministic(self) -> None:
        workloads = {0: 200, 1: 120, 2: 100}
        predecessors = {0: set(), 1: set(), 2: {0}}
        pipe_work = {0: {"PIPE_M": 100, "PIPE_V": 100},
                     1: {"PIPE_M": 120, "PIPE_V": 0},
                     2: {"PIPE_M": 100, "PIPE_V": 0}}
        cp_order = list_schedule(workloads, predecessors, 2, 0, 0,
                                 priority_mode="critical_path")[1]["assignment_order"]
        pipe_schedules, pipe_meta = list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="pipe_critical_path",
            pipe_workloads=pipe_work)
        self.assertEqual(cp_order[0], 0)
        self.assertEqual(pipe_meta["assignment_order"][0], 1)
        self.assertEqual(pipe_meta["pipe_critical_path_tail_cycles"]["0"], 200)
        self.assertEqual(pipe_schedules, list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="pipe_critical_path",
            pipe_workloads=pipe_work)[0])

    def test_pipe_work_ablation_uses_only_current_task_not_successor_pipe_tail(self) -> None:
        workloads = {0: 200, 1: 120, 2: 100}
        predecessors = {0: set(), 1: set(), 2: {0}}
        pipe_work = {0: {"PIPE_M": 100, "PIPE_V": 100},
                     1: {"PIPE_M": 120, "PIPE_V": 0},
                     2: {"PIPE_M": 100, "PIPE_V": 0}}
        schedules, meta = list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="pipe_work",
            pipe_workloads=pipe_work)
        self.assertEqual(meta["assignment_order"][0], 1)
        self.assertEqual(meta["pipe_work_cycles"]["0"], 100)
        self.assertEqual(meta["pipe_critical_path_tail_cycles"]["0"], 100)
        self.assertEqual(schedules, list_schedule(
            workloads, predecessors, 2, 0, 0, priority_mode="pipe_work",
            pipe_workloads=pipe_work)[0])

    def test_pipe_workload_builder_sums_compute_cycles_by_pipe(self) -> None:
        graph = {"ops": [{"id": 0, "op": "MATMUL", "pipe": "PIPE_M", "cycles": 7},
                         {"id": 1, "op": "ADD", "pipe": "PIPE_V", "cycles": 11},
                         {"id": 2, "op": "COPY_IN", "pipe": "PIPE_MTE2", "cycles": 3}],
                 "tensors": [], "edges": []}
        self.assertEqual(build_pipe_workloads(graph, {"0": 0, "1": 0}),
                         {0: {"PIPE_M": 7, "PIPE_V": 11}})

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

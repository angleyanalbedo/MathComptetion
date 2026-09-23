import unittest

from scripts.run_phase2_round1 import ledger_for_plan


class CommunicationLedgerTests(unittest.TestCase):
    def test_copy_boundaries_and_shared_input_are_deduplicated_by_task(self):
        graph = {
            "ops": [
                {"id": 1, "op": "COPY_IN"},
                {"id": 2, "op": "A"},
                {"id": 3, "op": "B"},
                {"id": 4, "op": "C"},
                {"id": 5, "op": "COPY_OUT"},
                {"id": 6, "op": "COPY_OUT"},
                {"id": 7, "op": "COPY_IN"},
            ],
            "tensors": [
                {"id": 100, "pos": "DDR", "size": 10},
                {"id": 101, "pos": "UB", "size": 10},
                {"id": 102, "pos": "L1", "size": 20},
                {"id": 103, "pos": "UB", "size": 5},
                {"id": 104, "pos": "DDR", "size": 8},
                {"id": 105, "pos": "DDR", "size": 7},
                {"id": 106, "pos": "DDR", "size": 5},
            ],
            "edges": [
                {"source": 100, "target": 1}, {"source": 1, "target": 101},
                {"source": 101, "target": 2}, {"source": 2, "target": 102},
                {"source": 102, "target": 3}, {"source": 103, "target": 3},
                {"source": 3, "target": 104}, {"source": 104, "target": 5},
                {"source": 102, "target": 4}, {"source": 103, "target": 4},
                {"source": 4, "target": 105}, {"source": 105, "target": 6},
                {"source": 106, "target": 7}, {"source": 7, "target": 103},
            ],
        }
        plan = {"node_to_subgraph": {"2": 0, "3": 1, "4": 2}}

        ledger = ledger_for_plan(graph, plan)

        self.assertEqual(ledger["boundary_read_bytes"], 60)
        self.assertEqual(ledger["boundary_write_bytes"], 35)
        self.assertEqual(ledger["shared_input_repeated_read_bytes"], 25)
        self.assertEqual(ledger["boundary_read_task_count"], 5)
        self.assertEqual(ledger["boundary_write_task_count"], 3)
        self.assertEqual(ledger["shared_input_tensor_count"], 2)
        self.assertEqual(ledger["per_tensor_reads"][102], {1, 2})
        self.assertEqual(ledger["per_tensor_reads"][103], {1, 2})
        self.assertEqual(ledger["per_tensor_writes"][102], {0})


if __name__ == "__main__":
    unittest.main()

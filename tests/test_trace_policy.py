from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import experiment_runner


class TraceRetentionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_context = tempfile.TemporaryDirectory(
            prefix=".trace-policy-test-", dir=experiment_runner.ROOT / "experiments")
        self.temp_root = Path(self.temp_context.name)
        self.graph = self.temp_root / "case_test.json"
        self.graph.write_text('{"ops":[],"tensors":[],"edges":[]}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_context.cleanup()

    def fake_success(self, command, **_kwargs):
        result = Path(command[command.index("-o") + 1])
        trace = Path(command[command.index("--trace-output") + 1])
        log = Path(command[command.index("--log-output") + 1])
        result.write_text(json.dumps({"makespan": 123, "data_movement_bytes": {}}), encoding="utf-8")
        trace.write_text('{"traceEvents":[]}\n', encoding="utf-8")
        log.write_text("makespan=123\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "success", "")

    def _run(self, *, retain_trace: bool, force: bool = False, fake=None):
        return experiment_runner.run_one_evaluator(
            graph_path=self.graph, plan_path=None, problem="singlecore", cores=1,
            case_dir=self.temp_root / "results" / "case_test", timeout_seconds=10,
            input_hash=experiment_runner.sha256_file(self.graph), generation_seconds=None,
            force=force, integrity_scope="none", retain_trace=retain_trace)

    @patch("scripts.experiment_runner.subprocess.run")
    def test_successful_batch_trace_is_discarded_and_not_hashed(self, run_mock) -> None:
        run_mock.side_effect = self.fake_success
        record = self._run(retain_trace=False)
        self.assertEqual(record["status"], "success")
        self.assertEqual(record["trace_status"], "generated_discarded")
        self.assertFalse(record["trace_retained"])
        self.assertFalse(any(Path(path).name == "trace.json" for path in record["output_paths"]))
        self.assertFalse(any(path.endswith("/trace.json") for path in record["output_sha256"]))
        self.assertIn("<TEMP_TRACE_PATH>", record["command"])

    @patch("scripts.experiment_runner.subprocess.run")
    def test_explicit_trace_retention_saves_and_hashes_trace(self, run_mock) -> None:
        run_mock.side_effect = self.fake_success
        record = self._run(retain_trace=True)
        self.assertEqual(record["trace_status"], "retained_requested")
        trace_paths = [experiment_runner.ROOT / path for path in record["output_paths"]
                       if Path(path).name == "trace.json"]
        self.assertEqual(len(trace_paths), 1)
        self.assertTrue(trace_paths[0].is_file())
        self.assertIn(trace_paths[0].relative_to(experiment_runner.ROOT).as_posix(),
                      record["output_sha256"])

    @patch("scripts.experiment_runner.subprocess.run")
    def test_failed_run_discards_trace_unless_explicitly_requested(self, run_mock) -> None:
        def failing(command, **_kwargs):
            trace = Path(command[command.index("--trace-output") + 1])
            trace.write_text('{"traceEvents":[]}\n', encoding="utf-8")
            return subprocess.CompletedProcess(command, 2, "", "[EVALUATION ERROR] invalid plan")

        run_mock.side_effect = failing
        record = self._run(retain_trace=False)
        self.assertEqual(record["status"], "illegal")
        self.assertEqual(record["trace_status"], "generated_discarded")
        self.assertFalse(record["trace_retained"])
        self.assertFalse(any(Path(path).name == "trace.json" for path in record["output_paths"]))


if __name__ == "__main__":
    unittest.main()

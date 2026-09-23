"""Restore the compacted canonical P1 round8 full artifacts from frozen inputs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common  # noqa: E402
from src.communication_partition import build_communication_plan  # noqa: E402
from src.dependency_schedule import ALGORITHM_VERSION, assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

BASE = ROOT / "experiments" / "phase2_problem1"
OUT = BASE / "round8_cube_vector_pipe_full"
FINAL = BASE / "final"
VERSION = "p1_cube_vector_pipe_priority_round8_v001"
CANDIDATE = {
    "name": "comm_partition_cube_vector_pipe_priority",
    "kind": "fixed_partition_cube_vector_pipe_priority",
    "partition": "p1_bounded_communication_cuts_v001",
    "duration_proxy": "sum_compute_cycles_for_release_estimates",
    "priority_mode": "pipe_critical_path",
    "priority_rule": "estimated_finish_minus_pipe_tail;pipe_task_work=max(PIPE_M_cycles,PIPE_V_cycles);finish;start;workload;task;core",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def preflight() -> list[dict]:
    expected_plans = {
        (row["case"], int(row["cores"])): row["plan_sha256"]
        for row in read_rows(FINAL / "plan_index.csv")
        if row["variant"] == "round8_final"
    }
    archived_rows = {
        (row["case"], int(row["cores"])): row
        for row in read_rows(OUT / "all_per_case.csv")
    }
    if len(expected_plans) != 400 or len(archived_rows) != 400:
        raise RuntimeError("round8 archive must contain exactly 400 plan and result index rows")

    case_paths = common.official_cases()
    if len(case_paths) != 100:
        raise RuntimeError(f"expected 100 official cases, found {len(case_paths)}")
    code_dir = str(common.OFFICIAL / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config

    waits = read_scene_a_config(common.CONFIG)
    tasks = []
    with tempfile.TemporaryDirectory(prefix="round8-plan-preflight-") as temp_dir:
        temp_root = Path(temp_dir)
        for case in sorted(case_paths):
            graph_path = case_paths[case]
            graph = load_graph(graph_path)
            graph_sha = common.sha256_file(graph_path)
            for cores in (2, 3, 4, 5):
                started = time.perf_counter()
                plan, partition_params = build_communication_plan(graph, cores)
                plan, schedule_params = assign_plan_cores(
                    graph, plan, cores,
                    waits["task_cross_core_wait_cycles"],
                    waits["task_same_core_wait_cycles"],
                    priority_mode="pipe_critical_path")
                generation_seconds = time.perf_counter() - started
                plan_file = temp_root / case / f"cores_{cores}.json"
                common.atomic_json(plan_file, plan)
                plan_sha = common.sha256_file(plan_file)
                key = (case, cores)
                if plan_sha != expected_plans.get(key):
                    raise RuntimeError(
                        f"deterministic plan mismatch for {case} cores={cores}: "
                        f"expected={expected_plans.get(key)} actual={plan_sha}")
                result_row = archived_rows.get(key)
                if not result_row or result_row["status"] != "success":
                    raise RuntimeError(f"missing successful archived result row: {case} cores={cores}")
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / CANDIDATE["name"]
                tasks.append({
                    "case": case, "cores": cores, "spec": CANDIDATE,
                    "parameters": {**partition_params, "assignment": schedule_params,
                                   "fixed_partition_source": "communication_cut_current_best"},
                    "graph_path": graph_path, "graph_sha": graph_sha,
                    "plan": plan, "plan_path": candidate_dir / "plan.json",
                    "plan_sha": plan_sha,
                    "generation_seconds": generation_seconds,
                    "candidate_dir": candidate_dir,
                    "fingerprint": common.make_fingerprint(
                        case, cores, plan_sha, CANDIDATE, graph_sha),
                    "archived_makespan": float(result_row["makespan"]),
                })
    return tasks


def update_plan_index(tasks: list[dict]) -> None:
    path = FINAL / "plan_index.csv"
    rows = read_rows(path)
    task_by_key = {(task["case"], task["cores"]): task for task in tasks}
    for row in rows:
        if row["variant"] != "round8_final":
            continue
        task = task_by_key[(row["case"], int(row["cores"]))]
        plan_path = task["candidate_dir"] / "plan.json"
        record_path = task["candidate_dir"] / "record.json"
        row["plan_path"] = plan_path.relative_to(ROOT).as_posix()
        row["record_path"] = record_path.relative_to(ROOT).as_posix()
        row["plan_sha256"] = common.sha256_file(plan_path)
        row["record_sha256"] = common.sha256_file(record_path)
    common.write_csv(path, rows, list(rows[0]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="after all 400 historical plan hashes match, rerun P1 evaluators")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")

    common.VERSION = VERSION
    tasks = preflight()
    print(f"Preflight passed: {len(tasks)}/400 regenerated plan hashes match the archived index.",
          flush=True)
    if not args.execute:
        print("Dry run only; no evaluator calls were made. Use --execute to restore full outputs.",
              flush=True)
        return 0

    for task in tasks:
        task["candidate_dir"].mkdir(parents=True, exist_ok=True)
        common.atomic_json(task["candidate_dir"] / "plan.json", task["plan"])
        common.atomic_json(task["candidate_dir"] / "plan_manifest.json", {
            "case": task["case"], "problem": "1", "cores": task["cores"],
            "candidate": CANDIDATE, "algorithm_version": VERSION,
            "scheduler_module_version": ALGORITHM_VERSION,
            "parameters": task["parameters"],
            "plan_path": (task["candidate_dir"] / "plan.json").relative_to(ROOT).as_posix(),
            "plan_sha256": task["plan_sha"], "fingerprint": task["fingerprint"],
            "generation_seconds": task["generation_seconds"],
        })

    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(common.run_eval, task, args.timeout_seconds): task
                   for task in tasks}
        for future in as_completed(futures):
            records.append(future.result())

    by_key = {(record["case"], record["cores"]): record for record in records}
    comparisons = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"])]
        result = record.get("result", {})
        makespan = result.get("makespan")
        comparisons.append({
            "case": task["case"], "cores": task["cores"],
            "status": record["status"], "archived_makespan": task["archived_makespan"],
            "restored_makespan": makespan,
            "matches_archived_makespan": makespan == task["archived_makespan"],
            "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix(),
        })
    common.write_csv(OUT / "round8_restore_comparison.csv", comparisons)
    if all(record.get("status") == "success" for record in records):
        update_plan_index(tasks)
    success = sum(record.get("status") == "success" for record in records)
    match_count = sum(row["matches_archived_makespan"] for row in comparisons)
    print(f"Restored evaluator records: {success}/400 successful; "
          f"{match_count}/400 Makespans match the archived report.", flush=True)
    if success != 400:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

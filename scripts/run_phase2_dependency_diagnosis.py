"""Fixed-partition P1 comparison of greedy and dependency-aware core schedules."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common
from src.communication_partition import build_communication_plan  # noqa: E402
from src.dependency_schedule import ALGORITHM_VERSION, assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_schedule"
COMM = ROOT / "experiments" / "phase2_problem1" / "round2_communication"
SAMPLES = ROOT / "experiments" / "phase2_problem1" / "round1" / "sample_groups.json"
VERSION = "p1_dependency_list_schedule_round4_v001"


def hash_src_excluding_new_modules() -> str:
    digest = hashlib.sha256()
    excluded = {"cycles_partition.py", "dependency_schedule.py"}
    for path in sorted((ROOT / "src").glob("*.py")):
        if path.name not in excluded:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def prior_comm_record(task: dict) -> tuple[Path, dict] | None:
    path = COMM / "cases" / task["case"] / f"cores_{task['cores']}" / "comm_256_w32_b128_384" / "record.json"
    expected = dict(task["fingerprint"])
    expected["candidate"] = {"name": "comm_256_w32_b128_384", "kind": "communication",
                             "target": 256, "minimum": 128, "maximum": 384, "window": 32}
    expected["plan_sha256"] = common.sha256_file(path.parent / "plan.json")
    expected["algorithm_sha256"] = hash_src_excluding_new_modules()
    record = common.valid_existing_record(path, expected)
    return (path, record) if record else None


def make_tasks(timeout: float) -> list[dict]:
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))
    case_paths = common.official_cases()
    code_dir = str(common.OFFICIAL / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config
    waits = read_scene_a_config(common.CONFIG)
    cross_wait, same_wait = waits["task_cross_core_wait_cycles"], waits["task_same_core_wait_cycles"]
    tasks = []
    candidate = {"name": "comm_partition_dependency_list", "kind": "fixed_partition_dependency_list",
                 "target": 256, "minimum": 128, "maximum": 384, "window": 32,
                 "duration_proxy": "sum_compute_cycles", "cross_core_wait_cycles": cross_wait,
                 "same_core_wait_cycles": same_wait}
    for sample in samples["diagnosis"]:
        case = sample["case"]
        graph_path = case_paths[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            started = time.perf_counter()
            plan, partition_params = build_communication_plan(graph, cores)
            plan, assignment_params = assign_plan_cores(
                graph, plan, cores, cross_wait, same_wait)
            generation_seconds = time.perf_counter() - started
            parameters = {**partition_params, "partition_fixed_to": "p1_bounded_communication_cuts_v001",
                          "assignment": assignment_params}
            candidate_dir = OUT / "cases" / case / f"cores_{cores}" / candidate["name"]
            candidate_dir.mkdir(parents=True, exist_ok=True)
            plan_path = candidate_dir / "plan.json"
            encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
            if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != encoded:
                plan_path.write_text(encoded, encoding="utf-8")
            plan_sha = common.sha256_file(plan_path)
            from stub_multicore_cut_and_schedule import validate_multicore_plan
            validate_multicore_plan(graph, plan)
            spec = {**candidate}
            fingerprint = common.make_fingerprint(case, cores, plan_sha, spec, graph_sha)
            task = {"case": case, "cores": cores, "spec": spec, "parameters": parameters,
                    "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                    "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                    "candidate_dir": candidate_dir, "fingerprint": fingerprint,
                    "timeout_seconds": timeout}
            common.atomic_json(candidate_dir / "plan_manifest.json", {
                "case": case, "problem": "1", "cores": cores, "candidate": spec,
                "algorithm_version": VERSION, "algorithm_module_version": ALGORITHM_VERSION,
                "parameters": parameters, "plan_path": plan_path.relative_to(ROOT).as_posix(),
                "plan_sha256": plan_sha, "fingerprint": fingerprint,
                "generation_seconds": generation_seconds})
            tasks.append(task)
    return tasks


def run_task(task: dict, timeout: float) -> dict:
    common.VERSION = VERSION
    return common.run_eval(task, timeout)


def compile_report(tasks: list[dict], records: list[dict]) -> None:
    phase1, _ = common.phase1_lookup()
    prior = common.read_csv(COMM / "diagnosis_per_case.csv")
    prior_by_key = {(r["case"], int(r["cores"])): r for r in prior
                    if r["candidate"] == "comm_256_w32_b128_384"}
    by_key = {(r["case"], r["cores"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"])]
        result = record.get("result", {})
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        old = prior_by_key[(task["case"], task["cores"])]
        ms = result.get("makespan")
        movement = result.get("data_movement_bytes", {})
        old_ms = float(old["makespan"])
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": ms, "greedy_comm_makespan": old_ms,
                     "v001_makespan": float(base["makespan"]),
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / ms if ms else None,
                     "makespan_change_vs_greedy_comm_percent": 100 * (ms / old_ms - 1) if ms else None,
                     "makespan_change_vs_v001_percent": 100 * (ms / float(base["makespan"]) - 1) if ms else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                     "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "plan_sha256": task["plan_sha"],
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    common.write_csv(OUT / "diagnosis_per_case.csv", rows)
    groups = []
    for cores in (2, 3, 4, 5):
        subset = [r for r in rows if r["cores"] == cores]
        good = [r for r in subset if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
        groups.append({"candidate": tasks[0]["spec"]["name"], "cores": cores,
                       "success": len(good), "illegal": sum(r["status"] == "illegal" for r in subset),
                       "failed": sum(r["status"] == "failed" for r in subset),
                       "timeout": sum(r["status"] == "timeout" for r in subset),
                       "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                       "mean_makespan_change_vs_greedy_comm_percent": sum(r["makespan_change_vs_greedy_comm_percent"] for r in good) / len(good) if good else None,
                       "improved_cases_vs_greedy_comm": sum(r["makespan_change_vs_greedy_comm_percent"] < 0 for r in good),
                       "regressed_or_tied_cases_vs_greedy_comm": sum(r["makespan_change_vs_greedy_comm_percent"] >= 0 for r in good),
                       "worst_change_vs_greedy_comm_percent": max((r["makespan_change_vs_greedy_comm_percent"] for r in good), default=None),
                       "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                       "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                       "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    mean = sum(g["average_speedup"] for g in groups) / 4
    for group in groups:
        group["equal_weight_mean_speedup_2_to_5"] = mean
    common.write_csv(OUT / "diagnosis_summary.csv", groups)
    lines = ["# Phase 2 P1 — fixed communication partition, dependency-aware list scheduling", "",
             "The communication-aware partition is byte-identical to the current P1 best; only core assignment/order changes. Task workload proxy is sum(op cycles). For a task/core pair, estimated release is the maximum of core availability plus same-core wait and each predecessor finish plus cross-core wait only when that predecessor is assigned to another core. Multiple predecessor waits are combined by max, not summed. Candidate pair is selected by earliest estimated finish, then start, workload, Task ID and core ID. Official evaluator metrics remain authoritative.", "",
             "| cores | success/10 | mean speedup | mean makespan change vs communication-greedy | improved | regressed/tied | worst regression |", "|---:|---:|---:|---:|---:|---:|---:|"]
    for group in groups:
        lines.append(f"| {group['cores']} | {group['success']}/10 | {group['average_speedup']:.5f} | {group['mean_makespan_change_vs_greedy_comm_percent']:+.3f}% | {group['improved_cases_vs_greedy_comm']} | {group['regressed_or_tied_cases_vs_greedy_comm']} | {group['worst_change_vs_greedy_comm_percent']:+.3f}% |")
    lines += ["", f"Equal-weight mean speedup across 2–5 cores: {mean:.5f}. Per-case evaluator results, transfer/spill and timings: `diagnosis_per_case.csv`; group summary: `diagnosis_summary.csv`.", ""]
    (OUT / "diagnosis_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = make_tasks(args.timeout_seconds)
    manifest = {"phase": 2, "round": "fixed_comm_partition_dependency_list_schedule_diagnosis",
                "scope": "P1 diagnosis 10 cases × 4 core counts", "algorithm_version": VERSION,
                "scheduler_module_version": ALGORITHM_VERSION,
                "partition_version": "p1_bounded_communication_cuts_v001",
                "task_count": len(tasks), "candidate_evaluator_calls": len(tasks),
                "reused_control_records": len(tasks), "reused_candidate_records": 0,
                "timeout_seconds": args.timeout_seconds, "official_full_manifest_scan": False}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    common.write_csv(OUT / "plan_manifest.csv", [
        {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
         "parameters": json.dumps(t["parameters"], sort_keys=True),
         "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
         "generation_seconds": t["generation_seconds"]} for t in tasks])
    # The old greedy schedules are read as comparison controls; the list-schedule
    # plans differ and therefore every candidate requires a fresh evaluator call.
    manifest["fresh_evaluator_calls"] = len(tasks)
    manifest["reused_records"] = 0
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"Prepared {len(tasks)} fixed-partition plans; {len(tasks)-fresh} greedy controls reusable; {fresh} new list-scheduling evaluator calls.", flush=True)
    common.VERSION = VERSION
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_task, task, args.timeout_seconds) for task in tasks]
        for future in as_completed(futures):
            records.append(future.result())
    compile_report(tasks, records)
    manifest["status_counts"] = {s: sum(r.get("status") == s for r in records)
                                 for s in ("success", "illegal", "failed", "timeout")}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"DONE: {len(records)} P1 dependency-schedule diagnosis records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

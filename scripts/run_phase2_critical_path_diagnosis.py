"""Compare deterministic ready-task priorities on the frozen P1 best partition."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common  # noqa: E402
from src.communication_partition import build_communication_plan  # noqa: E402
from src.dependency_schedule import ALGORITHM_VERSION, assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "round6_critical_path"
BEST = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_full"
DEPENDENCY_BEST = BEST
CRITICAL_PATH_BEST = ROOT / "experiments" / "phase2_problem1" / "round6_critical_path_full"
SAMPLES = ROOT / "experiments" / "phase2_problem1" / "round1" / "sample_groups.json"
VERSION = "p1_critical_path_list_schedule_round6_v001"
CANDIDATE = {"name": "comm_partition_critical_path_priority",
             "kind": "fixed_partition_critical_path_priority",
             "partition": "p1_bounded_communication_cuts_v001",
             "duration_proxy": "sum_compute_cycles",
             "priority_rule": "estimated_finish_minus_downstream_tail;finish;start;workload;task;core"}
PRIORITY_MODE = "critical_path"
BEST_CANDIDATE_NAME = "comm_partition_dependency_list"


def stored_control(case: str, cores: int) -> tuple[dict, str]:
    path = BEST / "cases" / case / f"cores_{cores}" / BEST_CANDIDATE_NAME / "record.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("status") != "success" or record.get("integrity_status") not in (
            "verified", "not_scanned_readonly_git_hook"):
        raise RuntimeError(f"current-best control is not a successful evaluator record: {path}")
    for rel, expected in record.get("output_sha256", {}).items():
        output = ROOT / rel
        if not output.is_file() or common.sha256_file(output) != expected:
            raise RuntimeError(f"stored control output hash mismatch: {output}")
    plan_path = path.parent / "plan.json"
    if common.sha256_file(plan_path) != record.get("plan_sha256"):
        raise RuntimeError(f"stored control plan hash mismatch: {plan_path}")
    return record, path.relative_to(ROOT).as_posix()


def make_tasks(timeout: float, sample_group: str) -> list[dict]:
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))
    cases = common.official_cases()
    code_dir = str(common.OFFICIAL / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config
    waits = read_scene_a_config(common.CONFIG)
    cross_wait, same_wait = waits["task_cross_core_wait_cycles"], waits["task_same_core_wait_cycles"]
    tasks = []
    controls = {}
    selected_cases = ([{"case": case} for case in sorted(cases)] if sample_group == "all"
                      else samples[sample_group])
    for sample in selected_cases:
        case = sample["case"]
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            started = time.perf_counter()
            plan, partition_params = build_communication_plan(graph, cores)
            plan, schedule_params = assign_plan_cores(
                graph, plan, cores, cross_wait, same_wait,
                priority_mode=CANDIDATE["priority_mode"])
            generation = time.perf_counter() - started

            # The only plan difference from the frozen best is core_schedules.
            old_plan = json.loads((BEST / "cases" / case / f"cores_{cores}" /
                                   BEST_CANDIDATE_NAME / "plan.json").read_text(encoding="utf-8"))
            if plan["node_to_subgraph"] != old_plan["node_to_subgraph"]:
                raise RuntimeError(f"partition changed for {case}, {cores} cores")

            candidate_dir = OUT / "cases" / case / f"cores_{cores}" / CANDIDATE["name"]
            candidate_dir.mkdir(parents=True, exist_ok=True)
            plan_path = candidate_dir / "plan.json"
            common.atomic_json(plan_path, plan)
            plan_sha = common.sha256_file(plan_path)
            from stub_multicore_cut_and_schedule import validate_multicore_plan
            validate_multicore_plan(graph, plan)
            parameters = {**partition_params, "assignment": schedule_params,
                          "fixed_partition_source": "communication_cut_current_best"}
            fingerprint = common.make_fingerprint(case, cores, plan_sha, CANDIDATE, graph_sha)
            task = {"case": case, "cores": cores, "spec": CANDIDATE, "parameters": parameters,
                    "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                    "plan_sha": plan_sha, "generation_seconds": generation,
                    "candidate_dir": candidate_dir, "fingerprint": fingerprint,
                    "timeout_seconds": timeout}
            common.atomic_json(candidate_dir / "plan_manifest.json", {
                "case": case, "problem": "1", "cores": cores, "candidate": CANDIDATE,
                "algorithm_version": VERSION, "scheduler_module_version": ALGORITHM_VERSION,
                "parameters": parameters, "plan_path": plan_path.relative_to(ROOT).as_posix(),
                "plan_sha256": plan_sha, "fingerprint": fingerprint,
                "generation_seconds": generation})
            controls[(case, cores)] = stored_control(case, cores)
            tasks.append(task)
    common.atomic_json(OUT / "controls.json", {
        f"{case}:cores_{cores}": {"record_path": path, "plan_sha256": record["plan_sha256"],
                                  "fingerprint": record["fingerprint"]}
        for (case, cores), (record, path) in controls.items()})
    return tasks


def compile_report(tasks: list[dict], records: list[dict], sample_group: str) -> None:
    phase1, _ = common.phase1_lookup()
    by_key = {(r["case"], r["cores"]): r for r in records}
    rows = []
    for task in tasks:
        case, cores = task["case"], task["cores"]
        record = by_key[(case, cores)]
        control, control_path = stored_control(case, cores)
        result, old_result = record.get("result", {}), control.get("result", {})
        ms, old_ms = result.get("makespan"), old_result.get("makespan")
        base = phase1[case][f"problem_1:{cores}"]
        movement = result.get("data_movement_bytes", {})
        rows.append({"case": case, "problem": "1", "cores": cores,
                     "candidate": CANDIDATE["name"], "status": record.get("status"),
                     "makespan": ms, "current_best_makespan": old_ms,
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / ms if ms else None,
                     "makespan_change_vs_current_best_percent": 100 * (ms / old_ms - 1) if ms and old_ms else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "current_best_record": control_path,
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    common.write_csv(OUT / f"{sample_group}_per_case.csv", rows)
    groups = []
    for cores in (2, 3, 4, 5):
        subset = [r for r in rows if r["cores"] == cores]
        good = [r for r in subset if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
        groups.append({"cores": cores, "success": len(good),
                       "illegal": sum(r["status"] == "illegal" for r in subset),
                       "failed": sum(r["status"] == "failed" for r in subset),
                       "timeout": sum(r["status"] == "timeout" for r in subset),
                       "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                       "current_best_average_speedup": sum(
                           r["speedup_vs_singlecore"] * r["makespan"] / r["current_best_makespan"]
                           for r in good) / len(good) if good else None,
                       "mean_makespan_change_vs_current_best_percent": sum(r["makespan_change_vs_current_best_percent"] for r in good) / len(good) if good else None,
                       "improved": sum(r["makespan_change_vs_current_best_percent"] < 0 for r in good),
                       "regressed_or_tied": sum(r["makespan_change_vs_current_best_percent"] >= 0 for r in good),
                       "worst_regression_percent": max((r["makespan_change_vs_current_best_percent"] for r in good), default=None),
                       "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                       "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    mean_speedup = sum(g["average_speedup"] for g in groups if g["average_speedup"] is not None) / 4
    control_mean_speedup = sum(g["current_best_average_speedup"] for g in groups
                               if g["current_best_average_speedup"] is not None) / 4
    for group in groups:
        group["equal_weight_mean_speedup_2_to_5"] = mean_speedup
        group["current_best_equal_weight_mean_speedup_2_to_5"] = control_mean_speedup
    common.write_csv(OUT / f"{sample_group}_summary.csv", groups)
    label = "full benchmark" if sample_group == "all" else sample_group
    case_count = len(rows) // 4
    scope_label = f"{case_count}-case" if case_count != 1 else "1-case"
    priority_desc = {
        "critical_path": "estimated finish minus downstream critical-path tail (own task work plus longest successor tail)",
        "successor_work": "estimated finish minus summed work of unique reachable successor Tasks",
        "pipe_critical_path": "estimated finish minus a Cube/Vector-aware path tail (per-Task max of PIPE_M and PIPE_V cycles plus longest successor tail)",
    }[CANDIDATE["priority_mode"]]
    lines = [f"# Phase 2 P1 — {CANDIDATE['priority_mode']} priority {label}", "",
             f"The current-best communication-cut partition and estimated release equations are held fixed. Only ready-task priority changes: minimize {priority_desc}, then estimated finish, start, workload, Task ID and core ID. Official evaluator Makespan is authoritative; controls are stored successful full-run records whose plan/output hashes were rechecked.", "",
             f"The {scope_label} equal-weight mean speedup is {mean_speedup:.5f} versus {control_mean_speedup:.5f} for the current best ({100 * (mean_speedup / control_mean_speedup - 1):+.3f}%). Since the partition is unchanged, only core assignment/order differs. Per-case regressions are preserved in the CSV.", "",
             f"| cores | success/{case_count} | candidate mean speedup | current-best mean speedup | mean Makespan change | improved | tied/regressed | worst regression |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g in groups:
        lines.append(f"| {g['cores']} | {g['success']}/{case_count} | {g['average_speedup']:.5f} | {g['current_best_average_speedup']:.5f} | {g['mean_makespan_change_vs_current_best_percent']:+.3f}% | {g['improved']} | {g['regressed_or_tied']} | {g['worst_regression_percent']:+.3f}% |")
    lines += ["", f"Equal-weight mean speedup across 2–5 cores: candidate {mean_speedup:.5f}; current best {control_mean_speedup:.5f}.",
              (f"This is the full formal-case benchmark; diagnosis/validation records reused only after exact fingerprint and output-hash validation. Retain all case-level regressions in `all_per_case.csv`."
               if sample_group == "all" else
               f"This is the fixed {sample_group} screening group only, not a formal full benchmark. Retain case-level regressions in `{sample_group}_per_case.csv`."), ""]
    (OUT / f"{sample_group}_report.md").write_text("\n".join(lines), encoding="utf-8")


def run_or_reuse(task: dict, timeout: float) -> dict:
    # Reuse only exact fingerprint matches with every recorded output hash intact.
    base_folder = OUT.name.removesuffix("_full").removesuffix("_validation")
    for folder in (base_folder, base_folder + "_validation"):
        path = (ROOT / "experiments" / "phase2_problem1" / folder / "cases" /
                task["case"] / f"cores_{task['cores']}" / CANDIDATE["name"] / "record.json")
        prior = common.valid_existing_record(path, task["fingerprint"])
        if prior:
            copied = {**prior, "reused": True, "source_record": path.relative_to(ROOT).as_posix()}
            common.atomic_json(task["candidate_dir"] / "record.json", copied)
            return {**copied, "record_path": str(task["candidate_dir"] / "record.json")}
    return common.run_eval(task, timeout)


def main() -> int:
    global OUT, BEST, CANDIDATE, PRIORITY_MODE, VERSION, BEST_CANDIDATE_NAME
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--sample-group", choices=("diagnosis", "validation", "all"), default="diagnosis")
    parser.add_argument("--priority-mode", choices=("critical_path", "successor_work", "cube_vector"),
                        default="critical_path")
    parser.add_argument("--report-only", action="store_true",
                        help="rebuild report from existing candidate records without evaluator calls")
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    PRIORITY_MODE = args.priority_mode
    if PRIORITY_MODE == "critical_path":
        BEST = DEPENDENCY_BEST
        BEST_CANDIDATE_NAME = "comm_partition_dependency_list"
        VERSION = "p1_critical_path_list_schedule_round6_v001"
        CANDIDATE = {"name": "comm_partition_critical_path_priority",
                     "kind": "fixed_partition_critical_path_priority",
                     "partition": "p1_bounded_communication_cuts_v001",
                     "duration_proxy": "sum_compute_cycles",
                     "priority_mode": PRIORITY_MODE,
                     "priority_rule": "estimated_finish_minus_downstream_tail;finish;start;workload;task;core"}
        prefix = "round6_critical_path"
    elif PRIORITY_MODE == "successor_work":
        BEST = CRITICAL_PATH_BEST
        BEST_CANDIDATE_NAME = "comm_partition_critical_path_priority"
        VERSION = "p1_successor_work_priority_round7_v001"
        CANDIDATE = {"name": "comm_partition_successor_work_priority",
                     "kind": "fixed_partition_successor_work_priority",
                     "partition": "p1_bounded_communication_cuts_v001",
                     "duration_proxy": "sum_compute_cycles",
                     "priority_mode": PRIORITY_MODE,
                     "priority_rule": "estimated_finish_minus_unique_descendant_sum_cycles;finish;start;workload;task;core"}
        prefix = "round7_successor_work"
    else:
        BEST = CRITICAL_PATH_BEST
        BEST_CANDIDATE_NAME = "comm_partition_critical_path_priority"
        VERSION = "p1_cube_vector_pipe_priority_round8_v001"
        CANDIDATE = {"name": "comm_partition_cube_vector_pipe_priority",
                     "kind": "fixed_partition_cube_vector_pipe_priority",
                     "partition": "p1_bounded_communication_cuts_v001",
                     "duration_proxy": "sum_compute_cycles_for_release_estimates",
                     "priority_mode": "pipe_critical_path",
                     "priority_rule": "estimated_finish_minus_pipe_tail;pipe_task_work=max(PIPE_M_cycles,PIPE_V_cycles);finish;start;workload;task;core"}
        prefix = "round8_cube_vector_pipe"
    output_dir = ROOT / "experiments" / "phase2_problem1" / (
        prefix if args.sample_group == "diagnosis" else
        prefix + ("_validation" if args.sample_group == "validation" else "_full"))
    OUT = output_dir
    OUT.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        tasks, records = [], []
        for record_path in sorted((OUT / "cases").rglob("record.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("candidate", {}).get("name") != CANDIDATE["name"]:
                continue
            tasks.append({"case": record["case"], "cores": record["cores"],
                          "candidate_dir": record_path.parent})
            records.append(record)
        compile_report(tasks, records, args.sample_group)
        print(f"Rebuilt report from {len(records)} existing records at {OUT}", flush=True)
        return 0
    tasks = make_tasks(args.timeout_seconds, args.sample_group)
    manifest = {"phase": 2, "round": f"{PRIORITY_MODE}_priority_{args.sample_group}",
                "scope": f"P1 fixed {args.sample_group} group × 2/3/4/5 cores",
                "algorithm_version": VERSION, "scheduler_module_version": ALGORITHM_VERSION,
                "candidate": CANDIDATE, "task_count": len(tasks),
                "fresh_evaluator_calls": len(tasks), "timeout_seconds": args.timeout_seconds,
                "official_full_manifest_scan": False}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    common.write_csv(OUT / "plan_manifest.csv", [
        {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
         "parameters": json.dumps(t["parameters"], sort_keys=True),
         "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
         "generation_seconds": t["generation_seconds"]} for t in tasks])
    common.VERSION = VERSION
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_or_reuse, task, args.timeout_seconds) for task in tasks]
        for future in as_completed(futures):
            records.append(future.result())
    compile_report(tasks, records, args.sample_group)
    manifest["status_counts"] = {s: sum(r.get("status") == s for r in records)
                                 for s in ("success", "illegal", "failed", "timeout")}
    manifest["exact_records_reused"] = sum(bool(r.get("reused")) for r in records)
    manifest["fresh_evaluator_calls"] = len(records) - manifest["exact_records_reused"]
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"DONE: {len(records)} P1 {PRIORITY_MODE} {args.sample_group} records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

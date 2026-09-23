"""Validation/full P1 benchmark for the frozen dependency-aware schedule candidate."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common
from src.communication_partition import build_communication_plan  # noqa: E402
from src.dependency_schedule import assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

ROUND4 = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_schedule"
COMM_VALIDATION = ROOT / "experiments" / "phase2_problem1" / "round2_communication_validation"
COMM_FULL = ROOT / "experiments" / "phase2_problem1" / "round2_communication_full"
OUT = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_validation"
FULL_OUT = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_full"
VERSION = "p1_dependency_list_schedule_round4_v001"


def prepare_tasks(case_ids: list[str], candidate: dict, out: Path) -> list[dict]:
    cases = common.official_cases()
    code_dir = str(common.OFFICIAL / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config
    waits = read_scene_a_config(common.CONFIG)
    cross_wait, same_wait = waits["task_cross_core_wait_cycles"], waits["task_same_core_wait_cycles"]
    tasks = []
    for case in case_ids:
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            started = time.perf_counter()
            plan, part_params = build_communication_plan(
                graph, cores, candidate["target"], candidate["minimum"],
                candidate["maximum"], candidate["window"])
            plan, schedule_params = assign_plan_cores(graph, plan, cores, cross_wait, same_wait)
            generation_seconds = time.perf_counter() - started
            params = {**part_params, "partition_fixed_to": "p1_bounded_communication_cuts_v001",
                      "schedule": schedule_params}
            candidate_dir = out / "cases" / case / f"cores_{cores}" / candidate["name"]
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
            task = {"case": case, "cores": cores, "spec": spec, "parameters": params,
                    "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                    "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                    "candidate_dir": candidate_dir, "fingerprint": fingerprint}
            common.atomic_json(candidate_dir / "plan_manifest.json", {
                "case": case, "problem": "1", "cores": cores, "candidate": spec,
                "algorithm_version": VERSION, "parameters": params,
                "plan_path": plan_path.relative_to(ROOT).as_posix(), "plan_sha256": plan_sha,
                "fingerprint": fingerprint, "generation_seconds": generation_seconds})
            tasks.append(task)
    return tasks


def compare_control(scope: str) -> dict[tuple[str, int], dict]:
    control_path = COMM_VALIDATION / "validation_per_case.csv" if scope == "validation" else COMM_FULL / "full_per_case.csv"
    rows = common.read_csv(control_path)
    return {(r["case"], int(r["cores"])): r for r in rows if r["candidate"] == "comm_256_w32_b128_384"}


def compile_report(scope: str, out: Path, tasks: list[dict], records: list[dict]) -> list[dict]:
    phase1, _ = common.phase1_lookup()
    controls = compare_control(scope)
    by_key = {(r["case"], r["cores"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"])]
        result = record.get("result", {})
        ms = result.get("makespan")
        control = controls[(task["case"], task["cores"])]
        control_ms = float(control["makespan"])
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        v001_ms = float(base["makespan"])
        movement = result.get("data_movement_bytes", {})
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": ms, "communication_greedy_makespan": control_ms,
                     "v001_makespan": v001_ms,
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / ms if ms else None,
                     "makespan_change_vs_greedy_percent": 100 * (ms / control_ms - 1) if ms else None,
                     "makespan_change_vs_v001_percent": 100 * (ms / v001_ms - 1) if ms else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                     "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "plan_sha256": task["plan_sha"],
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    prefix = "validation" if scope == "validation" else "full"
    common.write_csv(out / f"{prefix}_per_case.csv", rows)
    summary = []
    for cores in (2, 3, 4, 5):
        selected = [r for r in rows if r["cores"] == cores]
        good = [r for r in selected if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
        summary.append({"candidate": tasks[0]["spec"]["name"], "cores": cores,
                        "success": len(good), "illegal": sum(r["status"] == "illegal" for r in selected),
                        "failed": sum(r["status"] == "failed" for r in selected),
                        "timeout": sum(r["status"] == "timeout" for r in selected),
                        "average_makespan": sum(r["makespan"] for r in good) / len(good) if good else None,
                        "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                        "mean_makespan_change_vs_greedy_percent": sum(r["makespan_change_vs_greedy_percent"] for r in good) / len(good) if good else None,
                        "mean_makespan_change_vs_v001_percent": sum(r["makespan_change_vs_v001_percent"] for r in good) / len(good) if good else None,
                        "improved_cases_vs_greedy": sum(r["makespan_change_vs_greedy_percent"] < 0 for r in good),
                        "regressed_or_tied_cases_vs_greedy": sum(r["makespan_change_vs_greedy_percent"] >= 0 for r in good),
                        "worst_change_vs_greedy_percent": max((r["makespan_change_vs_greedy_percent"] for r in good), default=None),
                        "slower_than_singlecore_cases": sum(r["speedup_vs_singlecore"] < 1 for r in good),
                        "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                        "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                        "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    overall = sum(r["average_speedup"] for r in summary) / 4
    for r in summary:
        r["equal_weight_mean_speedup_2_to_5"] = overall
    common.write_csv(out / f"{prefix}_summary.csv", summary)
    expected = 10 if scope == "validation" else 100
    lines = [("# Phase 2 P1 — dependency-aware schedule validation" if scope == "validation"
              else "# Phase 2 P1 — dependency-aware schedule full benchmark"), "",
             ("Candidate parameters and partition were frozen before validation." if scope == "validation"
              else "Full 100-case comparison; diagnosis/validation records reused only on exact fingerprints."), "",
             f"| cores | success/{expected} | mean speedup | mean Makespan change vs greedy | improved | regressed/tied | worst regression | slower than single-core |",
             "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in summary:
        lines.append(f"| {r['cores']} | {r['success']}/{expected} | {r['average_speedup']:.5f} | {r['mean_makespan_change_vs_greedy_percent']:+.3f}% | {r['improved_cases_vs_greedy']} | {r['regressed_or_tied_cases_vs_greedy']} | {r['worst_change_vs_greedy_percent']:+.3f}% | {r['slower_than_singlecore_cases']} |")
    lines += ["", f"Equal-weight mean speedup: {overall:.6f}. Per-case result, copy/spill split, timings and plan hashes are in `{prefix}_per_case.csv`; grouped metrics are in `{prefix}_summary.csv`.", ""]
    (out / f"{prefix}_report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("validation", "full"), default="validation")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    parser.add_argument("--retain-trace-cases", default="",
                        help="comma-separated cases whose successful Trace files should be kept")
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    frozen = json.loads((ROUND4 / "frozen_validation_candidate.json").read_text(encoding="utf-8"))
    if frozen.get("status") not in ("frozen_before_validation", "validation_completed"):
        raise RuntimeError("candidate is not frozen for validation")
    out = OUT if args.scope == "validation" else FULL_OUT
    case_ids = frozen["validation_case_ids"] if args.scope == "validation" else sorted(common.official_cases())
    retain_trace_cases = {name.strip() for name in args.retain_trace_cases.split(",") if name.strip()}
    if retain_trace_cases - set(case_ids):
        parser.error(f"Trace retention requested for cases outside this run: {sorted(retain_trace_cases - set(case_ids))}")
    out.mkdir(parents=True, exist_ok=True)
    tasks = prepare_tasks(case_ids, frozen["candidate"], out)
    for task in tasks:
        task["retain_trace"] = task["case"] in retain_trace_cases
    common.VERSION = VERSION
    records = []
    eval_tasks = []
    reused = 0
    if args.scope == "full":
        for task in tasks:
            sources = [ROUND4 / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json",
                       OUT / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json"]
            for src in sources:
                record = common.valid_existing_record(
                    src, task["fingerprint"], require_trace=bool(task.get("retain_trace", False)))
                if record:
                    record = {**record, "reused": True, "source_record": src.relative_to(ROOT).as_posix()}
                    common.atomic_json(task["candidate_dir"] / "record.json", record)
                    records.append({**record, "case": task["case"], "cores": task["cores"],
                                    "candidate": task["spec"]})
                    reused += 1
                    break
            else:
                eval_tasks.append(task)
    else:
        eval_tasks = tasks
    common.atomic_json(out / "round_manifest.json", {
        "phase": 2, "scope": args.scope, "algorithm_version": VERSION,
        "candidate": frozen["candidate"], "case_count": len(case_ids),
        "record_count": len(tasks), "reused_fingerprint_records": reused,
        "new_evaluator_calls": len(eval_tasks), "timeout_seconds": args.timeout_seconds,
        "trace_policy": {"default": "temporary_then_discard",
                         "retained_cases": sorted(retain_trace_cases),
                         "failures": "discard_unless_explicitly_requested"},
        "full_official_manifest_scan": False})
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(common.run_eval, task, args.timeout_seconds): task for task in eval_tasks}
        for future in as_completed(futures):
            records.append(future.result())
    summary = compile_report(args.scope, out, tasks, records)
    if args.scope == "validation":
        frozen["status"] = "validation_completed"
        frozen["validation_records"] = len(records)
        frozen["validation_equal_weight_mean_speedup"] = summary[0]["equal_weight_mean_speedup_2_to_5"]
        frozen["validation_status_counts"] = {s: sum(r.get("status") == s for r in records)
                                              for s in ("success", "illegal", "failed", "timeout")}
        frozen["validation_result_dir"] = out.relative_to(ROOT).as_posix()
        common.atomic_json(ROUND4 / "frozen_validation_candidate.json", frozen)
    print(f"DONE: {len(records)} dependency-list {args.scope} P1 records; {reused} reused", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

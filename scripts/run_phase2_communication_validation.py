"""Validate the frozen communication-cut candidate on the untouched fixed validation set."""

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
from src.graph_io import load_graph  # noqa: E402

DIAG = ROOT / "experiments" / "phase2_problem1" / "round2_communication"
ROUND1 = ROOT / "experiments" / "phase2_problem1" / "round1"
FULL = ROOT / "experiments" / "phase2_problem1" / "full_v001"
OUT = ROOT / "experiments" / "phase2_problem1" / "round2_communication_validation"
VALIDATION_OUT = OUT
FULL_OUT = ROOT / "experiments" / "phase2_problem1" / "round2_communication_full"
VERSION = "p1_bounded_communication_cuts_round2_v001"


def prepare_tasks(candidate: dict, case_ids: list[str]) -> list[dict]:
    cases = common.official_cases()
    tasks = []
    for case in case_ids:
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            started = time.perf_counter()
            plan, parameters = build_communication_plan(
                graph, cores, target=candidate["target"], minimum=candidate["minimum"],
                maximum=candidate["maximum"], window=candidate["window"])
            generation_seconds = time.perf_counter() - started
            candidate_dir = OUT / "cases" / case / f"cores_{cores}" / candidate["name"]
            candidate_dir.mkdir(parents=True, exist_ok=True)
            plan_path = candidate_dir / "plan.json"
            encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
            if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != encoded:
                plan_path.write_text(encoded, encoding="utf-8")
            plan_sha = common.sha256_file(plan_path)
            official_code = str(common.OFFICIAL / "code")
            if official_code not in sys.path:
                sys.path.insert(0, official_code)
            from stub_multicore_cut_and_schedule import validate_multicore_plan
            validate_multicore_plan(graph, plan)
            spec = {"name": candidate["name"], "kind": "communication", "target": candidate["target"],
                    "minimum": candidate["minimum"], "maximum": candidate["maximum"],
                    "window": candidate["window"]}
            fingerprint = common.make_fingerprint(case, cores, plan_sha, spec, graph_sha)
            task = {"case": case, "cores": cores, "spec": spec, "parameters": parameters,
                    "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                    "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                    "candidate_dir": candidate_dir, "fingerprint": fingerprint}
            common.atomic_json(candidate_dir / "plan_manifest.json", {
                "case": case, "problem": "1", "cores": cores, "candidate": spec,
                "algorithm_version": VERSION, "parameters": parameters,
                "plan_path": plan_path.relative_to(ROOT).as_posix(), "plan_sha256": plan_sha,
                "fingerprint": fingerprint, "generation_seconds": generation_seconds})
            tasks.append(task)
    return tasks


def summarize(tasks: list[dict], records: list[dict]) -> list[dict]:
    phase1, _ = common.phase1_lookup()
    prior_rows = common.read_csv(FULL / "full_per_case.csv")
    fixed256 = {(r["case"], int(r["cores"])): r for r in prior_rows if r["candidate"] == "fixed_256"}
    by_key = {(r["case"], r["cores"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"])]
        result = record.get("result", {})
        makespan = result.get("makespan")
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        old = fixed256[(task["case"], task["cores"])]
        old_ms = float(old["makespan"])
        v001 = float(base["makespan"])
        speedup = float(base["singlecore_makespan"]) / makespan if makespan else None
        movement = result.get("data_movement_bytes", {})
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": makespan, "v001_makespan": v001, "fixed256_makespan": old_ms,
                     "speedup_vs_singlecore": speedup,
                     "makespan_change_vs_v001_percent": 100 * (makespan / v001 - 1) if makespan else None,
                     "makespan_change_vs_fixed256_percent": 100 * (makespan / old_ms - 1) if makespan else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                     "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "plan_sha256": task["plan_sha"],
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    scope_prefix = "validation" if OUT.name == "round2_communication_validation" else "full"
    common.write_csv(OUT / f"{scope_prefix}_per_case.csv", rows)
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
                        "mean_makespan_change_vs_v001_percent": sum(r["makespan_change_vs_v001_percent"] for r in good) / len(good) if good else None,
                        "mean_makespan_change_vs_fixed256_percent": sum(r["makespan_change_vs_fixed256_percent"] for r in good) / len(good) if good else None,
                        "improved_cases_vs_fixed256": sum(r["makespan_change_vs_fixed256_percent"] < 0 for r in good),
                        "regressed_or_tied_cases_vs_fixed256": sum(r["makespan_change_vs_fixed256_percent"] >= 0 for r in good),
                        "slower_than_singlecore_cases": sum(r["speedup_vs_singlecore"] < 1 for r in good),
                        "worst_change_vs_fixed256_percent": max((r["makespan_change_vs_fixed256_percent"] for r in good), default=None),
                        "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                        "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                        "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    summary[0]["equal_weight_mean_speedup_2_to_5"] = sum(x["average_speedup"] for x in summary) / 4
    common.write_csv(OUT / f"{scope_prefix}_summary.csv", summary)
    expected = 10 if scope_prefix == "validation" else 100
    title = "# Phase 2 P1 — communication-cut candidate validation" if scope_prefix == "validation" else "# Phase 2 P1 — communication-cut full benchmark"
    lines = [title, "",
             ("The communication-cut rule and parameters were frozen after diagnosis; no validation-driven tuning was performed." if scope_prefix == "validation" else "All 100 official cases × 4 core counts; only fingerprint-matched diagnosis/validation records were reused."), "",
             f"| cores | success/{expected} | mean speedup | mean makespan change vs fixed-256 | improved | regressed/tied | worst regression | avg added-copy bytes incl spill | slower than single-core |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        lines.append(f"| {row['cores']} | {row['success']}/{expected} | {row['average_speedup']:.5f} | {row['mean_makespan_change_vs_fixed256_percent']:+.3f}% | {row['improved_cases_vs_fixed256']} | {row['regressed_or_tied_cases_vs_fixed256']} | {row['worst_change_vs_fixed256_percent']:+.3f}% | {row['average_added_copy_bytes_including_spill']:.0f} | {row['slower_than_singlecore_cases']} |" if row["success"] else f"| {row['cores']} | 0/{expected} | NA | NA | 0 | 0 | NA | NA | NA |")
    lines += ["", f"Equal-weight mean speedup across core counts: {summary[0]['equal_weight_mean_speedup_2_to_5']:.5f}. Per-case rows and raw results are in `{scope_prefix}_per_case.csv` and `cases/`; grouped results are in `{scope_prefix}_summary.csv`.", ""]
    if scope_prefix == "validation":
        lines += ["Validation is a screening step. A full 100-case comparison is required before changing the P1 best.", ""]
    (OUT / f"{scope_prefix}_report.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("validation", "full"), default="validation")
    parser.add_argument("--summarize-existing", action="store_true",
                        help="rebuild full-scope reports from saved records without evaluator calls")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    frozen_path = DIAG / "frozen_validation_candidate.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if frozen.get("status") not in ("frozen_before_validation", "validation_completed"):
        raise RuntimeError("communication candidate is not frozen for validation")
    global OUT
    OUT = OUT if args.scope == "validation" else FULL_OUT
    case_ids = (frozen["validation_case_ids"] if args.scope == "validation"
                else sorted(common.official_cases()))
    OUT.mkdir(parents=True, exist_ok=True)
    common.VERSION = VERSION
    records = []
    evaluation_tasks = []
    if args.summarize_existing:
        if args.scope != "full":
            parser.error("--summarize-existing requires --scope full")
        tasks = []
        for case in case_ids:
            for cores in (2, 3, 4, 5):
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / frozen["candidate"]["name"]
                manifest = json.loads((candidate_dir / "plan_manifest.json").read_text(encoding="utf-8"))
                record = json.loads((candidate_dir / "record.json").read_text(encoding="utf-8"))
                tasks.append({"case": case, "cores": cores, "spec": frozen["candidate"],
                              "plan_sha": manifest["plan_sha256"], "candidate_dir": candidate_dir})
                records.append(record)
        if len(records) != 400 or any(record.get("status") != "success" for record in records):
            raise RuntimeError("saved full records are incomplete or contain unsuccessful outcomes")
    else:
        tasks = prepare_tasks(frozen["candidate"], case_ids)
        common.write_csv(OUT / "plan_manifest.csv", [
            {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
             "parameters": json.dumps(t["parameters"], sort_keys=True),
             "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
             "generation_seconds": t["generation_seconds"]} for t in tasks])
    if not args.summarize_existing and args.scope == "full":
        for task in tasks:
            sources = [
                DIAG / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json",
                VALIDATION_OUT / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json",
            ]
            for source_path in sources:
                record = common.valid_existing_record(source_path, task["fingerprint"])
                if record:
                    record = {**record, "reused": True, "source_record": source_path.relative_to(ROOT).as_posix()}
                    common.atomic_json(task["candidate_dir"] / "record.json", record)
                    records.append({**record, "case": task["case"], "cores": task["cores"],
                                    "candidate": task["spec"]})
                    break
            else:
                evaluation_tasks.append(task)
    elif not args.summarize_existing:
        evaluation_tasks = tasks
    if not args.summarize_existing:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(common.run_eval, task, args.timeout_seconds): task for task in evaluation_tasks}
            for future in as_completed(futures):
                records.append(future.result())
    summary = summarize(tasks, records)
    if args.scope == "validation":
        frozen["status"] = "validation_completed"
        frozen["validation_records"] = len(records)
        frozen["validation_status_counts"] = {s: sum(r.get("status") == s for r in records)
                                              for s in ("success", "illegal", "failed", "timeout")}
        frozen["validation_result_dir"] = OUT.relative_to(ROOT).as_posix()
        frozen["validation_equal_weight_mean_speedup"] = summary[0]["equal_weight_mean_speedup_2_to_5"]
        common.atomic_json(frozen_path, frozen)
    print(f"DONE: {len(records)} communication-candidate {args.scope} records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

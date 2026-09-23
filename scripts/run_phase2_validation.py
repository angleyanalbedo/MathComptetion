"""Evaluate the frozen Phase 2 P1 granularity candidates on the fixed validation set."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_phase2_round1 as round1

OUT = ROOT / "experiments" / "phase2_problem1" / "validation_v001"
ROUND1 = ROOT / "experiments" / "phase2_problem1" / "round1"
VALIDATION_OUT = OUT


def prepare_tasks(samples: list[str], candidates: list[dict]) -> list[dict]:
    cases = round1.official_cases()
    tasks = []
    for case in samples:
        graph_path = cases[case]
        graph = round1.load_graph(graph_path)
        graph_sha = round1.sha256_file(graph_path)
        for candidate in candidates:
            spec = candidate["parameters"]
            cores = (2, 3, 4, 5)
            for core_count in cores:
                started = time.perf_counter()
                plan, parameters = round1.make_plan(graph, spec, core_count)
                generation_seconds = time.perf_counter() - started
                candidate_dir = OUT / "cases" / case / f"cores_{core_count}" / candidate["candidate"]
                candidate_dir.mkdir(parents=True, exist_ok=True)
                plan_path = candidate_dir / "plan.json"
                serialized = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != serialized:
                    plan_path.write_text(serialized, encoding="utf-8")
                plan_sha = round1.sha256_file(plan_path)
                code_path = str(round1.OFFICIAL / "code")
                if code_path not in sys.path:
                    sys.path.insert(0, code_path)
                from stub_multicore_cut_and_schedule import validate_multicore_plan

                validate_multicore_plan(graph, plan)
                spec = {"name": candidate["candidate"], **spec}
                fingerprint = round1.make_fingerprint(case, core_count, plan_sha, spec, graph_sha)
                manifest = {"case": case, "problem": "1", "cores": core_count,
                            "candidate": candidate["candidate"], "parameters": parameters,
                            "plan_path": plan_path.relative_to(ROOT).as_posix(),
                            "plan_sha256": plan_sha, "fingerprint": fingerprint,
                            "generation_seconds": generation_seconds}
                round1.atomic_json(candidate_dir / "plan_manifest.json", manifest)
                tasks.append({"case": case, "cores": core_count, "spec": spec,
                              "parameters": parameters, "graph_path": graph_path,
                              "graph_sha": graph_sha, "plan_path": plan_path,
                              "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                              "candidate_dir": candidate_dir, "fingerprint": fingerprint})
    return tasks


def compile_report(tasks: list[dict], records: list[dict]) -> list[dict]:
    phase1, _ = round1.phase1_lookup()
    by_key = {(r["case"], r["cores"], r["candidate"]["name"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"], task["spec"]["name"])]
        result = record.get("result", {})
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        makespan = result.get("makespan")
        movement = result.get("data_movement_bytes", {})
        baseline_ms = float(base["makespan"])
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": makespan, "v001_makespan": baseline_ms,
                     "singlecore_makespan": float(base["singlecore_makespan"]),
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / makespan if makespan else None,
                     "makespan_change_vs_v001_percent": 100 * (makespan / baseline_ms - 1) if makespan else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                     "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    scope_prefix = "validation" if OUT.name == "validation_v001" else "full"
    round1.write_csv(OUT / f"{scope_prefix}_per_case.csv", rows)
    summary = []
    for candidate in sorted({r["candidate"] for r in rows}):
        for cores in (2, 3, 4, 5):
            selected = [r for r in rows if r["candidate"] == candidate and r["cores"] == cores]
            good = [r for r in selected if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
            deltas = [r["makespan_change_vs_v001_percent"] for r in good]
            summary.append({"candidate": candidate, "cores": cores, "success": len(good),
                            "illegal": sum(r["status"] == "illegal" for r in selected),
                            "failed": sum(r["status"] == "failed" for r in selected),
                            "timeout": sum(r["status"] == "timeout" for r in selected),
                            "average_makespan": sum(r["makespan"] for r in good) / len(good) if good else None,
                            "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                            "mean_makespan_change_vs_v001_percent": sum(deltas) / len(deltas) if deltas else None,
                            "improved_cases": sum(d < 0 for d in deltas),
                            "regressed_or_tied_cases": sum(d >= 0 for d in deltas),
                            "slower_than_singlecore_cases": sum(r["speedup_vs_singlecore"] < 1 for r in good),
                            "worst_change_vs_v001_percent": max(deltas) if deltas else None,
                            "average_added_copy_bytes_including_spill":
                                sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                            "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                            "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    for row in summary:
        core_rows = [r for r in summary if r["candidate"] == row["candidate"]]
        means = [r["average_speedup"] for r in core_rows if r["average_speedup"] is not None]
        row["equal_weight_mean_speedup_2_to_5"] = sum(means) / len(means) if len(means) == 4 else None
    round1.write_csv(OUT / f"{scope_prefix}_summary.csv", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("validation", "full"), default="validation")
    parser.add_argument("--summarize-existing", action="store_true",
                        help="rebuild tables from already saved plans and records without evaluator calls")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    frozen_path = ROUND1 / "frozen_validation_candidates.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    if frozen.get("status") not in ("frozen_after_diagnosis_not_yet_evaluated_on_validation",
                                     "validation_completed"):
        raise RuntimeError(f"unexpected frozen-candidate status: {frozen.get('status')}")
    samples = frozen["validation_case_ids"] if args.scope == "validation" else sorted(round1.official_cases())
    candidates = frozen["candidates"]
    if (args.scope == "validation" and len(samples) != 10) or len(samples) != (10 if args.scope == "validation" else 100) or len(candidates) != 2:
        raise RuntimeError("expected fixed validation (10) or full benchmark (100) and exactly two candidates")
    global OUT
    OUT = ROOT / "experiments" / "phase2_problem1" / ("validation_v001" if args.scope == "validation" else "full_v001")
    OUT.mkdir(parents=True, exist_ok=True)
    invocation = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": args.scope, "problem": "P1 only",
                  "cases": samples, "candidates": candidates,
                  "workers": args.workers, "timeout_seconds": args.timeout_seconds,
                  "full_official_manifest_scans": False}
    round1.atomic_json(OUT / "last_invocation.json", invocation)
    results = []
    if args.summarize_existing:
        if args.scope != "full":
            parser.error("--summarize-existing is currently available for --scope full only")
        tasks = []
        for case in samples:
            for candidate in candidates:
                for core_count in (2, 3, 4, 5):
                    candidate_dir = OUT / "cases" / case / f"cores_{core_count}" / candidate["candidate"]
                    manifest = json.loads((candidate_dir / "plan_manifest.json").read_text(encoding="utf-8"))
                    record = json.loads((candidate_dir / "record.json").read_text(encoding="utf-8"))
                    spec = candidate["parameters"]
                    tasks.append({"case": case, "cores": core_count,
                                  "spec": {"name": candidate["candidate"], **spec},
                                  "parameters": manifest["parameters"],
                                  "plan_path": ROOT / manifest["plan_path"],
                                  "plan_sha": manifest["plan_sha256"],
                                  "generation_seconds": manifest["generation_seconds"],
                                  "candidate_dir": candidate_dir})
                    results.append(record)
        if len(results) != 800 or any(r.get("status") != "success" for r in results):
            raise RuntimeError("existing full records are incomplete or include non-success status")
    else:
        tasks = prepare_tasks(samples, candidates)
        round1.write_csv(OUT / "plan_manifest.csv", [
            {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
             "parameters": json.dumps(t["parameters"], sort_keys=True),
             "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
             "generation_seconds": t["generation_seconds"]} for t in tasks])
        evaluation_tasks = []
    if not args.summarize_existing and args.scope == "full":
        for task in tasks:
            possible_sources = [
                VALIDATION_OUT / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json",
                ROUND1 / "cases" / task["case"] / f"cores_{task['cores']}" / task["spec"]["name"] / "record.json",
            ]
            reused = None
            for source_path in possible_sources:
                reused = round1.valid_existing_record(source_path, task["fingerprint"])
                if reused:
                    reused = {**reused, "reused": True, "source_record": source_path.relative_to(ROOT).as_posix()}
                    round1.atomic_json(task["candidate_dir"] / "record.json", reused)
                    results.append({**reused, "case": task["case"], "cores": task["cores"],
                                    "candidate": task["spec"], "record_path": str(task["candidate_dir"] / "record.json")})
                    break
            if not reused:
                evaluation_tasks.append(task)
    elif not args.summarize_existing:
        evaluation_tasks = tasks
    if not args.summarize_existing:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(round1.run_eval, task, args.timeout_seconds): task for task in evaluation_tasks}
            for future in as_completed(futures):
                results.append(future.result())
    summary = compile_report(tasks, results)
    invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
    invocation["records"] = len(results)
    invocation["status_counts"] = {s: sum(r.get("status") == s for r in results)
                                    for s in ("success", "illegal", "failed", "timeout")}
    round1.atomic_json(OUT / "last_invocation.json", invocation)
    if args.scope == "validation":
        frozen["status"] = "validation_completed"
        frozen["validation_runs_completed"] = len(results)
        frozen["validation_result_dir"] = OUT.relative_to(ROOT).as_posix()
        frozen["validation_status_counts"] = invocation["status_counts"]
        round1.atomic_json(frozen_path, frozen)
    title = "# Phase 2 P1 frozen-candidate validation" if args.scope == "validation" else "# Phase 2 P1 full 100-case benchmark"
    scope_prefix = "validation" if args.scope == "validation" else "full"
    lines = [title, "",
             ("The 10-case validation set and two candidates were frozen before evaluator calls. No parameters were changed using validation outcomes." if args.scope == "validation" else "All 100 official cases, four core counts and both frozen candidates. Fingerprint-matched diagnosis/validation records were reused; all remaining items were evaluated."), "",
             "| candidate | cores | success/10 | mean speedup | mean makespan change vs v001 | improved | regressed/tied | worst regression |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary:
        expected = 10 if args.scope == "validation" else 100
        lines.append(f"| {row['candidate']} | {row['cores']} | {row['success']}/{expected} | {row['average_speedup']:.5f} | {row['mean_makespan_change_vs_v001_percent']:+.3f}% | {row['improved_cases']} | {row['regressed_or_tied_cases']} | {row['worst_change_vs_v001_percent']:+.3f}% |" if row["success"] else f"| {row['candidate']} | {row['cores']} | 0/{expected} | NA | NA | 0 | 0 | NA |")
    lines += ["", f"Per-case measurements and raw evaluator records are in `{OUT.name}/{scope_prefix}_per_case.csv` and `cases/`; summary is in `{OUT.name}/{scope_prefix}_summary.csv`.", ""]
    (OUT / ("validation_report.md" if args.scope == "validation" else "full_report.md")).write_text("\n".join(lines), encoding="utf-8")
    print(f"DONE: {len(results)} frozen P1 validation records; outputs at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

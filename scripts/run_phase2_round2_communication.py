"""Diagnosis comparison for bounded communication-aware contiguous cuts (P1 only)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common

from src.communication_partition import (  # noqa: E402
    ALGORITHM_VERSION as COMM_VERSION,
    MAX_CHUNK_SIZE,
    MIN_CHUNK_SIZE,
    TARGET_CHUNK_SIZE,
    CUT_WINDOW,
    build_communication_plan,
)
from src.graph_io import load_graph  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "round2_communication"
PREVIOUS = ROOT / "experiments" / "phase2_problem1" / "round1"
FULL = ROOT / "experiments" / "phase2_problem1" / "full_v001"
CURRENT_VERSION = "p1_bounded_communication_cuts_round2_v001"


def historical_baseline_source_hash() -> str:
    """Fingerprint the exact source set used by completed v001/fixed-256 runs."""
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src").glob("*.py")):
        if path.name == "communication_partition.py":
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def make_tasks(timeout: float) -> list[dict]:
    samples = json.loads((PREVIOUS / "sample_groups.json").read_text(encoding="utf-8"))
    cases = common.official_cases()
    candidates = [
        {"name": "fixed_064", "kind": "fixed", "size": 64},
        {"name": "fixed_256", "kind": "fixed", "size": 256},
        {"name": "comm_256_w32_b128_384", "kind": "communication", "target": TARGET_CHUNK_SIZE,
         "window": CUT_WINDOW, "minimum": MIN_CHUNK_SIZE, "maximum": MAX_CHUNK_SIZE},
    ]
    tasks = []
    for sample in samples["diagnosis"]:
        case = sample["case"]
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            for spec in candidates:
                started = time.perf_counter()
                if spec["kind"] == "communication":
                    plan, params = build_communication_plan(
                        graph, cores, target=spec["target"], minimum=spec["minimum"],
                        maximum=spec["maximum"], window=spec["window"])
                    algorithm = COMM_VERSION
                else:
                    plan, params = common.make_plan(graph, spec, cores)
                    algorithm = common.ALGORITHM_VERSION
                generation_seconds = time.perf_counter() - started
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / spec["name"]
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
                fingerprint_spec = dict(spec)
                fingerprint = common.make_fingerprint(case, cores, plan_sha, fingerprint_spec, graph_sha)
                if spec["kind"] != "communication":
                    fingerprint["algorithm_sha256"] = historical_baseline_source_hash()
                task = {"case": case, "cores": cores, "spec": spec, "parameters": params,
                        "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                        "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                        "candidate_dir": candidate_dir, "fingerprint": fingerprint,
                        "timeout_seconds": timeout, "algorithm_version": algorithm}
                common.atomic_json(candidate_dir / "plan_manifest.json", {
                    "case": case, "problem": "1", "cores": cores, "candidate": spec,
                    "algorithm_version": algorithm, "parameters": params,
                    "plan_path": plan_path.relative_to(ROOT).as_posix(),
                    "plan_sha256": plan_sha, "fingerprint": fingerprint,
                    "generation_seconds": generation_seconds})
                tasks.append(task)
    return tasks


def source_record(task: dict) -> tuple[Path, dict] | None:
    name = task["spec"]["name"]
    paths = []
    if name in ("fixed_064", "fixed_256"):
        paths += [PREVIOUS / "cases" / task["case"] / f"cores_{task['cores']}" / name / "record.json"]
    if name == "fixed_256":
        paths += [FULL / "cases" / task["case"] / f"cores_{task['cores']}" / name / "record.json"]
    for path in paths:
        record = common.valid_existing_record(path, task["fingerprint"])
        if record:
            return path, record
    return None


def run_task(task: dict, timeout: float) -> dict:
    common.VERSION = CURRENT_VERSION
    cached = source_record(task)
    record_path = task["candidate_dir"] / "record.json"
    if cached:
        source_path, record = cached
        record = {**record, "reused": True, "source_record": source_path.relative_to(ROOT).as_posix(),
                  "generation_seconds": task["generation_seconds"]}
        common.atomic_json(record_path, record)
        return {**record, "case": task["case"], "cores": task["cores"],
                "candidate": task["spec"], "record_path": str(record_path)}
    return common.run_eval(task, timeout)


def save_reports(tasks: list[dict], records: list[dict]) -> None:
    phase1, _ = common.phase1_lookup()
    by_key = {(r["case"], r["cores"], r["candidate"]["name"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"], task["spec"]["name"])]
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        result = record.get("result", {})
        movement = result.get("data_movement_bytes", {})
        makespan = result.get("makespan")
        v001 = float(base["makespan"])
        speedup = float(base["singlecore_makespan"]) / makespan if makespan else None
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": makespan, "v001_makespan": v001,
                     "speedup_vs_singlecore": speedup,
                     "makespan_change_vs_v001_percent": 100 * (makespan / v001 - 1) if makespan else None,
                     "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                     "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                     "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                     "generation_seconds": record.get("generation_seconds"),
                     "evaluator_seconds": record.get("evaluator_seconds"),
                     "plan_sha256": task["plan_sha"],
                     "record_path": (task["candidate_dir"] / "record.json").relative_to(ROOT).as_posix()})
    common.write_csv(OUT / "diagnosis_per_case.csv", rows)
    groups = []
    for candidate in sorted({row["candidate"] for row in rows}):
        for cores in (2, 3, 4, 5):
            selected = [r for r in rows if r["candidate"] == candidate and r["cores"] == cores]
            good = [r for r in selected if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
            groups.append({"candidate": candidate, "cores": cores, "success": len(good),
                           "illegal": sum(r["status"] == "illegal" for r in selected),
                           "failed": sum(r["status"] == "failed" for r in selected),
                           "timeout": sum(r["status"] == "timeout" for r in selected),
                           "average_makespan": sum(r["makespan"] for r in good) / len(good) if good else None,
                           "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                           "mean_makespan_change_vs_v001_percent": sum(r["makespan_change_vs_v001_percent"] for r in good) / len(good) if good else None,
                           "improved_vs_v001": sum(r["makespan_change_vs_v001_percent"] < 0 for r in good),
                           "regressed_or_tied_vs_v001": sum(r["makespan_change_vs_v001_percent"] >= 0 for r in good),
                           "worst_change_vs_v001_percent": max((r["makespan_change_vs_v001_percent"] for r in good), default=None),
                           "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                           "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                           "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    for row in groups:
        peers = [r["average_speedup"] for r in groups if r["candidate"] == row["candidate"] and r["average_speedup"] is not None]
        row["equal_weight_mean_speedup_2_to_5"] = sum(peers) / len(peers) if len(peers) == 4 else None
    common.write_csv(OUT / "diagnosis_summary.csv", groups)
    lines = ["# Phase 2 Problem 1 — bounded communication-cut diagnosis", "",
             "P1 only. Topological op order and greedy cumulative-cycle core assignment are held fixed. The single changed factor is the contiguous partition boundary selection. Candidate rule and parameters were fixed before evaluation: target 256 ops, chunk bounds 128–384, candidate cut within ±32 of equal-sized ideal cuts; minimize summed distinct intermediate-tensor bytes crossing each boundary, then total distance from target 256, then lexicographic cuts. COPY_IN/COPY_OUT-only tensors are excluded from the proxy. These graph-derived bytes are a heuristic signal, not evaluator traffic or Makespan.", "",
             "| candidate | equal-weight mean speedup (2–5) | core speedups (2/3/4/5) | mean makespan change vs v001 | success records |", "|---|---:|---|---:|---:|"]
    for name in sorted({g["candidate"] for g in groups}):
        gs = sorted((g for g in groups if g["candidate"] == name), key=lambda x: x["cores"])
        score = gs[0]["equal_weight_mean_speedup_2_to_5"]
        core_means = "/".join(f"{g['average_speedup']:.4f}" for g in gs)
        delta = sum(g["mean_makespan_change_vs_v001_percent"] for g in gs) / len(gs)
        lines.append(f"| {name} | {score:.5f} | {core_means} | {delta:+.3f}% | {sum(g['success'] for g in gs)}/40 |")
    lines += ["", "Detailed case/core outcomes, transfer/spill split, generation/evaluator timings and plan hashes are in `diagnosis_per_case.csv`; grouped metrics are in `diagnosis_summary.csv`. Diagnosis only: this is not a full-benchmark conclusion. Validation and full evaluation are required before adopting the communication candidate.", ""]
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
    manifest = {"phase": "2", "round": "communication_aware_contiguous_cuts_diagnosis",
                "scope": "P1 diagnosis 10 cases × 4 core counts", "algorithm_version": CURRENT_VERSION,
                "communication_algorithm_version": COMM_VERSION,
                "parameters": {"target_chunk_size": TARGET_CHUNK_SIZE, "minimum_chunk_size": MIN_CHUNK_SIZE,
                               "maximum_chunk_size": MAX_CHUNK_SIZE, "cut_window": CUT_WINDOW,
                               "core_assignment": "unchanged greedy cumulative cycles"},
                "candidates": ["fixed_064", "fixed_256", "comm_256_w32_b128_384"],
                "task_count": len(tasks), "timeout_seconds": args.timeout_seconds,
                "official_full_manifest_scan": False}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    common.write_csv(OUT / "plan_manifest.csv", [
        {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
         "parameters": json.dumps(t["parameters"], sort_keys=True),
         "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
         "generation_seconds": t["generation_seconds"]} for t in tasks])
    fresh = [t for t in tasks if source_record(t) is None]
    reused = len(tasks) - len(fresh)
    print(f"Prepared {len(tasks)} plans; {reused} exact-fingerprint records reusable; {len(fresh)} evaluator calls required.", flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_task, task, args.timeout_seconds): task for task in tasks}
        for future in as_completed(futures):
            records.append(future.result())
    save_reports(tasks, records)
    manifest["status_counts"] = {status: sum(r.get("status") == status for r in records)
                                 for status in ("success", "illegal", "failed", "timeout")}
    manifest["reused_records"] = reused
    manifest["fresh_evaluator_calls"] = len(fresh)
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"DONE: {len(records)} P1 diagnosis records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

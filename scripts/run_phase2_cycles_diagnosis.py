"""Compare an independent cumulative-cycles cut rule against P1 controls."""

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
from src.cycles_partition import ALGORITHM_VERSION as CYCLES_VERSION, build_cycles_plan  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "round3_cycles"
ROUND1 = ROOT / "experiments" / "phase2_problem1" / "round1"
COMM = ROOT / "experiments" / "phase2_problem1" / "round2_communication"
VERSION = "p1_cumulative_cycles_cuts_round3_v001"


def source_hash_excluding(excluded: set[str]) -> str:
    h = hashlib.sha256()
    for path in sorted((ROOT / "src").glob("*.py")):
        if path.name not in excluded:
            h.update(path.name.encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def make_tasks(timeout: float) -> list[dict]:
    samples = json.loads((ROUND1 / "sample_groups.json").read_text(encoding="utf-8"))
    cases = common.official_cases()
    candidates = [
        {"name": "fixed_256", "kind": "fixed", "size": 256},
        {"name": "comm_256_w32_b128_384", "kind": "communication", "target": 256,
         "minimum": 128, "maximum": 384, "window": 32},
        {"name": "cycles_256_b128_384", "kind": "cycles", "target": 256,
         "minimum": 128, "maximum": 384},
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
                if spec["kind"] == "cycles":
                    plan, parameters = build_cycles_plan(graph, cores, spec["target"], spec["minimum"], spec["maximum"])
                    algorithm = CYCLES_VERSION
                elif spec["kind"] == "communication":
                    from src.communication_partition import build_communication_plan
                    plan, parameters = build_communication_plan(graph, cores, spec["target"],
                                                                  spec["minimum"], spec["maximum"], spec["window"])
                    algorithm = "p1_bounded_communication_cuts_v001"
                else:
                    plan, parameters = common.make_plan(graph, spec, cores)
                    algorithm = common.ALGORITHM_VERSION
                generation_seconds = time.perf_counter() - started
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / spec["name"]
                candidate_dir.mkdir(parents=True, exist_ok=True)
                plan_path = candidate_dir / "plan.json"
                encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != encoded:
                    plan_path.write_text(encoded, encoding="utf-8")
                plan_sha = common.sha256_file(plan_path)
                code_dir = str(common.OFFICIAL / "code")
                if code_dir not in sys.path:
                    sys.path.insert(0, code_dir)
                from stub_multicore_cut_and_schedule import validate_multicore_plan
                validate_multicore_plan(graph, plan)
                fingerprint = common.make_fingerprint(case, cores, plan_sha, spec, graph_sha)
                if spec["kind"] == "fixed":
                    fingerprint["algorithm_sha256"] = source_hash_excluding(
                        {"communication_partition.py", "cycles_partition.py"})
                elif spec["kind"] == "communication":
                    fingerprint["algorithm_sha256"] = source_hash_excluding({"cycles_partition.py"})
                task = {"case": case, "cores": cores, "spec": spec, "parameters": parameters,
                        "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                        "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                        "candidate_dir": candidate_dir, "fingerprint": fingerprint,
                        "algorithm_version": algorithm, "timeout_seconds": timeout}
                common.atomic_json(candidate_dir / "plan_manifest.json", {
                    "case": case, "problem": "1", "cores": cores, "candidate": spec,
                    "algorithm_version": algorithm, "parameters": parameters,
                    "plan_path": plan_path.relative_to(ROOT).as_posix(), "plan_sha256": plan_sha,
                    "fingerprint": fingerprint, "generation_seconds": generation_seconds})
                tasks.append(task)
    return tasks


def find_source(task: dict) -> tuple[Path, dict] | None:
    name = task["spec"]["name"]
    if name == "fixed_256":
        sources = [ROUND1 / "cases" / task["case"] / f"cores_{task['cores']}" / name / "record.json",
                   ROOT / "experiments" / "phase2_problem1" / "full_v001" / "cases" / task["case"] / f"cores_{task['cores']}" / name / "record.json"]
    elif name == "comm_256_w32_b128_384":
        sources = [COMM / "cases" / task["case"] / f"cores_{task['cores']}" / name / "record.json"]
    else:
        sources = []
    for source in sources:
        record = common.valid_existing_record(source, task["fingerprint"])
        if record:
            return source, record
    return None


def run_task(task: dict, timeout: float) -> dict:
    common.VERSION = VERSION
    old = find_source(task)
    record_path = task["candidate_dir"] / "record.json"
    if old:
        source, record = old
        record = {**record, "reused": True, "source_record": source.relative_to(ROOT).as_posix(),
                  "generation_seconds": task["generation_seconds"]}
        common.atomic_json(record_path, record)
        return {**record, "case": task["case"], "cores": task["cores"],
                "candidate": task["spec"], "record_path": str(record_path)}
    return common.run_eval(task, timeout)


def compile_reports(tasks: list[dict], records: list[dict]) -> None:
    phase1, _ = common.phase1_lookup()
    by_key = {(r["case"], r["cores"], r["candidate"]["name"]): r for r in records}
    rows = []
    for task in tasks:
        record = by_key[(task["case"], task["cores"], task["spec"]["name"])]
        result = record.get("result", {})
        movement = result.get("data_movement_bytes", {})
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        makespan = result.get("makespan")
        v001 = float(base["makespan"])
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": task["spec"]["name"], "status": record.get("status"),
                     "makespan": makespan, "v001_makespan": v001,
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / makespan if makespan else None,
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
    for name in sorted({r["candidate"] for r in rows}):
        for cores in (2, 3, 4, 5):
            group = [r for r in rows if r["candidate"] == name and r["cores"] == cores]
            good = [r for r in group if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
            groups.append({"candidate": name, "cores": cores, "success": len(good),
                           "illegal": sum(r["status"] == "illegal" for r in group),
                           "failed": sum(r["status"] == "failed" for r in group),
                           "timeout": sum(r["status"] == "timeout" for r in group),
                           "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                           "mean_makespan_change_vs_v001_percent": sum(r["makespan_change_vs_v001_percent"] for r in good) / len(good) if good else None,
                           "improved_vs_v001": sum(r["makespan_change_vs_v001_percent"] < 0 for r in good),
                           "worst_change_vs_v001_percent": max((r["makespan_change_vs_v001_percent"] for r in good), default=None),
                           "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                           "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                           "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    for group in groups:
        means = [g["average_speedup"] for g in groups if g["candidate"] == group["candidate"] and g["average_speedup"] is not None]
        group["equal_weight_mean_speedup_2_to_5"] = sum(means) / len(means) if len(means) == 4 else None
    common.write_csv(OUT / "diagnosis_summary.csv", groups)
    lines = ["# Phase 2 P1 — independent cumulative-cycles cut diagnosis", "",
             "Only partitioning changes. All candidates use the same topological op order and greedy cumulative-cycles core assignment. The cycles candidate chooses each contiguous cut nearest to the remaining average cycle workload, subject to 128–384 ops per chunk; target chunk count is the nearest feasible count to N/256. Ties prefer a chunk length nearer 256 and then the lower cut index. This is a deterministic greedy heuristic, not an evaluator-time estimate.", "",
             "| candidate | equal-weight mean speedup 2–5 | core means 2/3/4/5 | mean makespan change vs v001 | successful records |", "|---|---:|---|---:|---:|"]
    for name in sorted({g["candidate"] for g in groups}):
        gs = sorted((g for g in groups if g["candidate"] == name), key=lambda x: x["cores"])
        lines.append(f"| {name} | {gs[0]['equal_weight_mean_speedup_2_to_5']:.5f} | "
                     + "/".join(f"{g['average_speedup']:.4f}" for g in gs)
                     + f" | {sum(g['mean_makespan_change_vs_v001_percent'] for g in gs)/4:+.3f}% | {sum(g['success'] for g in gs)}/40 |")
    lines += ["", "See `diagnosis_per_case.csv` and `diagnosis_summary.csv` for the exact metrics, including failure counts, transfer/spill, and timings. This fixed 10-case diagnosis set screens the candidate only; it is not the full-case conclusion.", ""]
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
    manifest = {"phase": 2, "round": "independent_cumulative_cycles_partition_diagnosis",
                "scope": "P1 diagnosis 10 cases × 4 core counts", "algorithm_version": VERSION,
                "cycles_partition_version": CYCLES_VERSION,
                "parameters": {"target_ops": 256, "minimum_ops": 128, "maximum_ops": 384,
                               "core_assignment": "unchanged greedy cumulative cycles"},
                "candidate_count": 3, "task_count": len(tasks), "timeout_seconds": args.timeout_seconds,
                "full_official_manifest_scan": False}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    common.write_csv(OUT / "plan_manifest.csv", [
        {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
         "parameters": json.dumps(t["parameters"], sort_keys=True),
         "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
         "generation_seconds": t["generation_seconds"]} for t in tasks])
    fresh = sum(find_source(t) is None for t in tasks)
    common.VERSION = VERSION
    print(f"Prepared {len(tasks)} plans; exact-fingerprint prior outcomes leave {fresh} fresh evaluator calls.", flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_task, t, args.timeout_seconds) for t in tasks]
        for future in as_completed(futures):
            records.append(future.result())
    compile_reports(tasks, records)
    manifest["reused_records"] = len(tasks) - fresh
    manifest["fresh_evaluator_calls"] = fresh
    manifest["status_counts"] = {s: sum(r.get("status") == s for r in records)
                                 for s in ("success", "illegal", "failed", "timeout")}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"DONE: {len(records)} P1 cycle-cut diagnosis records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

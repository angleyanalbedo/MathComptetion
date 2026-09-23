"""Diagnosis of strong-edge atom aggregation with fixed dependency scheduling."""

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
from src.dag_partition import (ALGORITHM_VERSION as DAG_VERSION,
                               build_dag_partition_plan)  # noqa: E402
from src.dependency_schedule import assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "round5_dag_partition"
ROUND2 = ROOT / "experiments" / "phase2_problem1" / "round2_communication"
ROUND4 = ROOT / "experiments" / "phase2_problem1" / "round4_dependency_schedule"
SAMPLE_PATH = ROOT / "experiments" / "phase2_problem1" / "round1" / "sample_groups.json"
VERSION = "p1_strong_edge_dag_partition_round5_v001"


def source_hash_excluding(excluded: set[str]) -> str:
    h = hashlib.sha256()
    for path in sorted((ROOT / "src").glob("*.py")):
        if path.name not in excluded:
            h.update(path.name.encode("utf-8"))
            h.update(path.read_bytes())
    return h.hexdigest()


def build_tasks(timeout: float) -> list[dict]:
    samples = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    cases = common.official_cases()
    code_dir = str(common.OFFICIAL / "code")
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config
    waits = read_scene_a_config(common.CONFIG)
    cross_wait, same_wait = waits["task_cross_core_wait_cycles"], waits["task_same_core_wait_cycles"]
    tasks = []
    candidates = [
        {"name": "comm_256_w32_b128_384", "kind": "communication", "target": 256,
         "minimum": 128, "maximum": 384, "window": 32},
        {"name": "comm_partition_dependency_list", "kind": "fixed_partition_dependency_list",
         "target": 256, "minimum": 128, "maximum": 384, "window": 32,
         "duration_proxy": "sum_compute_cycles", "cross_core_wait_cycles": cross_wait,
         "same_core_wait_cycles": same_wait},
        {"name": "dag_strong_atom128_target256_max384", "kind": "dag_strong_edge",
         "atom_size": 128, "target_size": 256, "minimum": 128, "maximum": 384,
         "assignment": "fixed_dependency_list_schedule_v001",
         "cross_core_wait_cycles": cross_wait, "same_core_wait_cycles": same_wait},
    ]
    for sample in samples["diagnosis"]:
        case = sample["case"]
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in (2, 3, 4, 5):
            for spec in candidates:
                started = time.perf_counter()
                if spec["kind"] == "dag_strong_edge":
                    plan, partition_params = build_dag_partition_plan(
                        graph, cores, atom_size=spec["atom_size"], target_size=spec["target_size"],
                        minimum=spec["minimum"], maximum=spec["maximum"])
                    plan, schedule_params = assign_plan_cores(graph, plan, cores, cross_wait, same_wait)
                    parameters = {**partition_params, "schedule": schedule_params}
                    algo = DAG_VERSION
                elif spec["kind"] == "fixed_partition_dependency_list":
                    # Rebuild exactly the current-best partition, then retain the
                    # same dependency-aware schedule; this is a reproducibility control.
                    from src.communication_partition import build_communication_plan
                    from src.dependency_schedule import assign_plan_cores
                    plan, partition_params = build_communication_plan(graph, cores)
                    plan, schedule_params = assign_plan_cores(graph, plan, cores, cross_wait, same_wait)
                    parameters = {**partition_params, "schedule": schedule_params}
                    algo = "p1_dependency_list_schedule_v001"
                else:
                    from src.communication_partition import build_communication_plan
                    plan, parameters = build_communication_plan(graph, cores)
                    algo = "p1_bounded_communication_cuts_v001"
                generation = time.perf_counter() - started
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / spec["name"]
                candidate_dir.mkdir(parents=True, exist_ok=True)
                plan_path = candidate_dir / "plan.json"
                encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != encoded:
                    plan_path.write_text(encoded, encoding="utf-8")
                plan_sha = common.sha256_file(plan_path)
                from stub_multicore_cut_and_schedule import validate_multicore_plan
                validate_multicore_plan(graph, plan)
                fingerprint = common.make_fingerprint(case, cores, plan_sha, spec, graph_sha)
                if spec["kind"] == "communication":
                    fingerprint["algorithm_sha256"] = source_hash_excluding(
                        {"cycles_partition.py", "dependency_schedule.py", "dag_partition.py"})
                elif spec["kind"] == "fixed_partition_dependency_list":
                    fingerprint["candidate"] = {"name": "comm_partition_dependency_list",
                        "kind": "fixed_partition_dependency_list", "target": 256, "minimum": 128,
                        "maximum": 384, "window": 32, "duration_proxy": "sum_compute_cycles",
                        "cross_core_wait_cycles": cross_wait, "same_core_wait_cycles": same_wait}
                    fingerprint["algorithm_sha256"] = source_hash_excluding({"dag_partition.py"})
                task = {"case": case, "cores": cores, "spec": spec, "parameters": parameters,
                        "graph_path": graph_path, "graph_sha": graph_sha, "plan_path": plan_path,
                        "plan_sha": plan_sha, "generation_seconds": generation,
                        "candidate_dir": candidate_dir, "fingerprint": fingerprint,
                        "algorithm_version": algo, "timeout_seconds": timeout}
                common.atomic_json(candidate_dir / "plan_manifest.json", {
                    "case": case, "problem": "1", "cores": cores, "candidate": spec,
                    "algorithm_version": algo, "parameters": parameters,
                    "plan_path": plan_path.relative_to(ROOT).as_posix(),
                    "plan_sha256": plan_sha, "fingerprint": fingerprint,
                    "generation_seconds": generation})
                tasks.append(task)
    return tasks


def source_control(task: dict) -> tuple[Path, dict] | None:
    name = task["spec"]["name"]
    folder = "comm_partition_dependency_list" if name == "comm_partition_dependency_list" else name
    parent = ROUND4 if name == "comm_partition_dependency_list" else ROUND2
    path = parent / "cases" / task["case"] / f"cores_{task['cores']}" / folder / "record.json"
    record = common.valid_existing_record(path, task["fingerprint"])
    return (path, record) if record else None


def run_one(task: dict, timeout: float) -> dict:
    common.VERSION = VERSION
    if task["spec"]["kind"] != "dag_strong_edge":
        old = source_control(task)
        if old:
            path, record = old
            copied = {**record, "reused": True, "source_record": path.relative_to(ROOT).as_posix(),
                      "generation_seconds": task["generation_seconds"]}
            record_path = task["candidate_dir"] / "record.json"
            common.atomic_json(record_path, copied)
            return {**copied, "case": task["case"], "cores": task["cores"],
                    "candidate": task["spec"], "record_path": str(record_path)}
    return common.run_eval(task, timeout)


def compile_reports(tasks: list[dict], records: list[dict]) -> None:
    phase1, _ = common.phase1_lookup()
    by_key = {(r["case"], r["cores"], r["candidate"]["name"]): r for r in records}
    rows = []
    for task in tasks:
        name = task["spec"]["name"]
        record = by_key[(task["case"], task["cores"], name)]
        result = record.get("result", {})
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        movement = result.get("data_movement_bytes", {})
        makespan = result.get("makespan")
        rows.append({"case": task["case"], "problem": "1", "cores": task["cores"],
                     "candidate": name, "status": record.get("status"), "makespan": makespan,
                     "speedup_vs_singlecore": float(base["singlecore_makespan"]) / makespan if makespan else None,
                     "makespan_change_vs_v001_percent": 100 * (makespan / float(base["makespan"]) - 1) if makespan else None,
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
            selected = [r for r in rows if r["candidate"] == name and r["cores"] == cores]
            good = [r for r in selected if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
            groups.append({"candidate": name, "cores": cores, "success": len(good),
                           "illegal": sum(r["status"] == "illegal" for r in selected),
                           "failed": sum(r["status"] == "failed" for r in selected),
                           "timeout": sum(r["status"] == "timeout" for r in selected),
                           "average_speedup": sum(r["speedup_vs_singlecore"] for r in good) / len(good) if good else None,
                           "mean_makespan_change_vs_v001_percent": sum(r["makespan_change_vs_v001_percent"] for r in good) / len(good) if good else None,
                           "worst_change_vs_v001_percent": max((r["makespan_change_vs_v001_percent"] for r in good), default=None),
                           "average_added_copy_bytes_including_spill": sum(r["added_copy_bytes_including_spill"] or 0 for r in good) / len(good) if good else None,
                           "average_generation_seconds": sum(r["generation_seconds"] or 0 for r in good) / len(good) if good else None,
                           "average_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in good) / len(good) if good else None})
    for group in groups:
        means = [g["average_speedup"] for g in groups if g["candidate"] == group["candidate"] and g["average_speedup"] is not None]
        group["equal_weight_mean_speedup_2_to_5"] = sum(means) / len(means) if len(means) == 4 else None
    common.write_csv(OUT / "diagnosis_summary.csv", groups)
    lines = ["# Phase 2 P1 — DAG strong-edge partition diagnosis", "",
             "The communication-cut partition is the current best control; the second control holds both partition and dependency-list schedule fixed. The DAG candidate starts from contiguous 128-op atoms, greedily merges the pair with greatest summed distinct-tensor byte strength, targets approximately 256 ops, limits clusters to 128–384 compute ops, and uses the current dependency-list assignment unchanged. Every proposed merge is checked against the complete contracted atom DAG; cyclic merges are rejected. No local search or tuning is used.", "",
             "| candidate | equal-weight mean speedup (2–5) | core means (2/3/4/5) | mean Makespan vs v001 | success |", "|---|---:|---|---:|---:|"]
    for name in sorted({g["candidate"] for g in groups}):
        gs = sorted((g for g in groups if g["candidate"] == name), key=lambda x: x["cores"])
        lines.append(f"| {name} | {gs[0]['equal_weight_mean_speedup_2_to_5']:.5f} | "
                     + "/".join(f"{g['average_speedup']:.4f}" for g in gs)
                     + f" | {sum(g['mean_makespan_change_vs_v001_percent'] for g in gs)/4:+.3f}% | {sum(g['success'] for g in gs)}/40 |")
    lines += ["", "Case-level results and raw evaluator artifacts are in `diagnosis_per_case.csv` and `cases/`; grouped results are in `diagnosis_summary.csv`. Diagnosis is only a screening stage.", ""]
    (OUT / "diagnosis_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(args.timeout_seconds)
    controls = sum(task["spec"]["kind"] != "dag_strong_edge" for task in tasks)
    manifest = {"phase": 2, "round": "dag_strong_edge_partition_diagnosis",
                "scope": "P1 fixed diagnosis group × 2/3/4/5 cores", "version": VERSION,
                "partition_algorithm": DAG_VERSION, "candidate_rule": {
                    "atom_size": 128, "target_size": 256, "minimum": 128, "maximum": 384,
                    "merge_order": "maximum summed tensor-byte strength; topo tie break",
                    "dag_guard": "rebuild and topologically validate entire contracted atom DAG after each proposed merge",
                    "core_assignment": "frozen dependency-list schedule"},
                "task_count": len(tasks), "control_count": controls,
                "new_candidate_evaluator_calls": len(tasks) - controls,
                "timeout_seconds": args.timeout_seconds, "full_official_manifest_scan": False}
    common.atomic_json(OUT / "round_manifest.json", manifest)
    common.write_csv(OUT / "plan_manifest.csv", [
        {"case": t["case"], "cores": t["cores"], "candidate": t["spec"]["name"],
         "parameters": json.dumps(t["parameters"], sort_keys=True),
         "plan_path": t["plan_path"].relative_to(ROOT).as_posix(), "plan_sha256": t["plan_sha"],
         "generation_seconds": t["generation_seconds"]} for t in tasks])
    common.VERSION = VERSION
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, task, args.timeout_seconds) for task in tasks]
        for future in as_completed(futures):
            records.append(future.result())
    compile_reports(tasks, records)
    manifest["status_counts"] = {s: sum(r.get("status") == s for r in records)
                                 for s in ("success", "illegal", "failed", "timeout")}
    manifest["exact_fingerprint_controls_reused"] = sum(r.get("reused", False) for r in records)
    common.atomic_json(OUT / "round_manifest.json", manifest)
    print(f"DONE: {len(records)} P1 DAG partition diagnosis records at {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

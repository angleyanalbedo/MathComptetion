"""Run only the two missing, frozen full-P1 removal ablations."""

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
from run_phase2_dependency_benchmark import VERSION as DEPENDENCY_VERSION  # noqa: E402
from src.communication_partition import build_communication_plan  # noqa: E402
from src.dependency_schedule import assign_plan_cores  # noqa: E402
from src.graph_io import load_graph  # noqa: E402
from src.scheduler import build_plan  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "final"
CORES = (2, 3, 4, 5)
VARIANTS = {
    "no_critical_path_pipe_work": {
        "name": "no_critical_path_pipe_work",
        "kind": "final_removal_ablation",
        "partition": "p1_bounded_communication_cuts_v001",
        "schedule": "dependency-aware release; priority by estimated finish minus current Task max(PIPE_M,PIPE_V) work; no successor critical-path tail",
        "priority_mode": "pipe_work",
    },
    "no_communication_fixed256_pipe_cp": {
        "name": "no_communication_fixed256_pipe_cp",
        "kind": "final_removal_ablation",
        "partition": "topological contiguous fixed 256 compute ops",
        "schedule": "same dependency-aware release and Cube/Vector pipe critical-path priority as round8",
        "priority_mode": "pipe_critical_path",
    },
}


def prepare_tasks(variant: dict) -> list[dict]:
    cases = common.official_cases()
    official_code = str(common.OFFICIAL / "code")
    if official_code not in sys.path:
        sys.path.insert(0, official_code)
    from multicore_cut_evaluate_problem_1 import read_scene_a_config
    from stub_multicore_cut_and_schedule import validate_multicore_plan

    waits = read_scene_a_config(common.CONFIG)
    cross_wait = waits["task_cross_core_wait_cycles"]
    same_wait = waits["task_same_core_wait_cycles"]
    tasks = []
    for case in sorted(cases):
        graph_path = cases[case]
        graph = load_graph(graph_path)
        graph_sha = common.sha256_file(graph_path)
        for cores in CORES:
            started = time.perf_counter()
            if variant["name"] == "no_communication_fixed256_pipe_cp":
                plan = build_plan(graph, cores, 256)
                partition_params = {"partition": "topological_contiguous", "chunk_size": 256}
            else:
                plan, partition_params = build_communication_plan(graph, cores)
            plan, schedule_params = assign_plan_cores(
                graph, plan, cores, cross_wait, same_wait,
                priority_mode=variant["priority_mode"])
            generation_seconds = time.perf_counter() - started
            validate_multicore_plan(graph, plan)
            candidate_dir = OUT / "ablations" / variant["name"] / "cases" / case / f"cores_{cores}"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            plan_path = candidate_dir / "plan.json"
            encoded = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
            if not plan_path.is_file() or plan_path.read_text(encoding="utf-8") != encoded:
                plan_path.write_text(encoded, encoding="utf-8")
            plan_sha = common.sha256_file(plan_path)
            spec = {**variant}
            fingerprint = common.make_fingerprint(case, cores, plan_sha, spec, graph_sha)
            params = {**partition_params, "cross_core_wait_cycles": cross_wait,
                      "same_core_wait_cycles": same_wait, "schedule": schedule_params,
                      "algorithm_source_sha256": common.source_fingerprint(),
                      "algorithm_version": "p1_final_ablation_v001"}
            task = {"case": case, "cores": cores, "spec": spec,
                    "parameters": params, "graph_path": graph_path,
                    "graph_sha": graph_sha, "plan_path": plan_path,
                    "plan_sha": plan_sha, "generation_seconds": generation_seconds,
                    "candidate_dir": candidate_dir, "fingerprint": fingerprint}
            common.atomic_json(candidate_dir / "plan_manifest.json", {
                "case": case, "problem": "1", "cores": cores,
                "candidate": spec, "algorithm_version": "p1_final_ablation_v001",
                "scheduler_module_version": DEPENDENCY_VERSION,
                "parameters": params,
                "plan_path": plan_path.relative_to(ROOT).as_posix(),
                "plan_sha256": plan_sha, "fingerprint": fingerprint,
                "generation_seconds": generation_seconds})
            tasks.append(task)
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=(*VARIANTS, "all"), default="all")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    selected = list(VARIANTS) if args.variant == "all" else [args.variant]
    invocation = {"phase": "P1 closeout only", "variants": selected,
                  "case_count": 100, "cores": list(CORES),
                  "workers": args.workers, "timeout_seconds": args.timeout_seconds,
                  "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "full_official_manifest_scan": False}
    common.atomic_json(OUT / "ablation_invocation.json", invocation)
    for name in selected:
        variant = VARIANTS[name]
        tasks = prepare_tasks(variant)
        pending = []
        reused = 0
        for task in tasks:
            record_path = task["candidate_dir"] / "record.json"
            cached = common.valid_existing_record(record_path, task["fingerprint"])
            if cached:
                reused += 1
            else:
                pending.append(task)
        records = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(common.run_eval, task, args.timeout_seconds): task
                       for task in pending}
            for future in as_completed(futures):
                records.append(future.result())
        counts = {status: sum(
            json.loads((task["candidate_dir"] / "record.json").read_text(encoding="utf-8")).get("status") == status
            for task in tasks) for status in ("success", "illegal", "failed", "timeout")}
        invocation.setdefault("variants_done", {})[name] = {
            "records": len(tasks), "exact_fingerprint_reused": reused,
            "new_evaluator_calls": len(pending), "status_counts": counts}
        common.atomic_json(OUT / "ablation_invocation.json", invocation)
        print(f"DONE {name}: {len(tasks)} rows; reused={reused}; fresh={len(pending)}; {counts}", flush=True)
    invocation["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    common.atomic_json(OUT / "ablation_invocation.json", invocation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

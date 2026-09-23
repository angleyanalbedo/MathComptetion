"""Run representative or full Phase 1 v001 evaluation with durable checkpoints."""

from __future__ import annotations

import argparse
import csv
import os
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from experiment_runner import (  # noqa: E402
    ALGORITHM_VERSION, CONFIG, CORE_COUNTS, PARAMETERS, PROBLEMS,
    atomic_json, generate_case_plan, run_one_evaluator, sha256_file, source_fingerprint,
)
from summarize_benchmark import summarize  # noqa: E402


def representative_cases(profile_path: Path, case_paths: list[Path]) -> tuple[list[Path], dict[str, list[str]]]:
    with profile_path.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 100:
        raise ValueError(f"expected a 100-case graph profile, found {len(rows)} rows")
    by_name = {path.stem: path for path in case_paths}
    tags: dict[str, list[str]] = {}

    def add(row: dict, tag: str) -> None:
        name = row["case"]
        if name not in by_name:
            raise ValueError(f"profile references missing official case {name}")
        tags.setdefault(name, []).append(tag)

    add(min(rows, key=lambda row: int(row["op_count"])), "smallest_op_count")
    add(max(rows, key=lambda row: int(row["op_count"])), "largest_op_count")
    add(max(rows, key=lambda row: int(row["original_graph_copy_bytes"])), "highest_estimated_graph_copy_bytes")
    add(max(rows, key=lambda row: int(row["topological_order_ub_live_bytes_estimate"])), "highest_estimated_UB_live_bytes")
    add(max(rows, key=lambda row: int(row["multi_consumer_tensor_bytes"])), "highest_multi_consumer_tensor_bytes")
    selected = [by_name[name] for name in tags]
    return selected, tags


def ensure_experiment_manifest(output_root: Path, case_paths: list[Path], timeout: float) -> None:
    manifest = {
        "algorithm_version": ALGORITHM_VERSION,
        "algorithm_sha256": source_fingerprint(),
        "parameters": PARAMETERS,
        "official_config": "official/data/config.txt",
        "config_sha256": sha256_file(CONFIG),
        "official_manifest_sha256": sha256_file(ROOT / "protection" / "official-files.sha256"),
        "cases": {path.stem: sha256_file(path) for path in case_paths},
        "core_counts": list(CORE_COUNTS),
        "problems": list(PROBLEMS),
        "timeout_seconds": timeout,
    }
    path = output_root / "experiment_manifest.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        for key in ("algorithm_version", "algorithm_sha256", "parameters", "config_sha256",
                    "cases", "core_counts", "problems"):
            if existing.get(key) != manifest.get(key):
                raise RuntimeError(f"existing experiment manifest differs at {key}: {path}")
        return
    atomic_json(path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("representative", "full"), required=True)
    parser.add_argument("--output-root", type=Path,
                        default=ROOT / "experiments" / "phase1_baseline" / "v001")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--workers", type=int, default=min(4, max(1, (os.cpu_count() or 2) - 1)),
                        help="parallel evaluator processes; default reserves CPU capacity")
    parser.add_argument("--retain-trace-cases", default="",
                        help="comma-separated case IDs to retain Trace for; successful others are discarded")
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")
    retain_trace_cases = {name.strip() for name in args.retain_trace_cases.split(",") if name.strip()}

    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(ROOT):
        parser.error("--output-root must stay inside the project workspace")
    output_root.mkdir(parents=True, exist_ok=True)
    case_paths = sorted((ROOT / "official" / "data").glob("case_*.json"))
    if len(case_paths) != 100:
        raise RuntimeError(f"expected exactly 100 official graph files; found {len(case_paths)}")
    unknown_trace_cases = retain_trace_cases - {path.stem for path in case_paths}
    if unknown_trace_cases:
        parser.error(f"unknown case IDs in --retain-trace-cases: {sorted(unknown_trace_cases)}")
    ensure_experiment_manifest(output_root, case_paths, args.timeout_seconds)

    if args.mode == "representative":
        profile_path = ROOT / "experiments" / "phase0" / "graph-profile-v1" / "profile.csv"
        selected, tags = representative_cases(profile_path, case_paths)
        atomic_json(output_root / "reports" / "representative_cases.json", {
            "selection_source": "Phase 0 graph profile; labels are selection criteria only, not evaluator measurements",
            "cases": {name: labels for name, labels in tags.items()},
        })
    else:
        selected = case_paths
        rep_file = output_root / "reports" / "representative_cases.json"
        if not rep_file.exists():
            _selected, tags = representative_cases(
                ROOT / "experiments" / "phase0" / "graph-profile-v1" / "profile.csv", case_paths)
            atomic_json(rep_file, {
                "selection_source": "Phase 0 graph profile; labels are selection criteria only, not evaluator measurements",
                "cases": {name: labels for name, labels in tags.items()},
            })
    unselected_trace_cases = retain_trace_cases - {path.stem for path in selected}
    if unselected_trace_cases:
        parser.error(f"Trace retention requested for cases outside this run: {sorted(unselected_trace_cases)}")

    invocation = {
        "mode": args.mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timeout_seconds": args.timeout_seconds,
        "workers": args.workers,
        "selected_cases": [path.stem for path in selected],
        "trace_policy": {"default": "temporary_then_discard",
                         "retained_cases": sorted(retain_trace_cases),
                         "failures": "discard_unless_explicitly_requested"},
    }
    atomic_json(output_root / "last_invocation.json", invocation)
    print(f"START mode={args.mode} cases={len(selected)} timeout={args.timeout_seconds}s "
          f"algorithm={ALGORITHM_VERSION}", flush=True)

    # Official full-manifest scans are disabled by project policy; official/
    # is user-set read-only and protected by the repository Git hook.
    single_records: list[dict] = []
    singles_to_run = []
    for graph_path in selected:
        singles_to_run.append((graph_path, output_root / "cases" / graph_path.stem,
                               sha256_file(graph_path)))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_one_evaluator,
                graph_path=graph_path, plan_path=None, problem="singlecore", cores=1,
                case_dir=case_dir, timeout_seconds=args.timeout_seconds,
                input_hash=graph_hash, generation_seconds=None,
                integrity_scope="none",
                retain_trace=graph_path.stem in retain_trace_cases,
            ): graph_path.stem
            for graph_path, case_dir, graph_hash in singles_to_run
        }
        for index, future in enumerate(as_completed(futures), 1):
            record = future.result()
            if not record.get("reused"):
                single_records.append(record)
            print(f"CHECKPOINT singlecore {index}/{len(futures)} case={futures[future]}", flush=True)
    summarize(output_root, case_paths)

    # Prepare deterministic plans; no full official manifest scan is performed.
    multi_tasks = []
    for graph_path in selected:
        case_dir = output_root / "cases" / graph_path.stem
        graph_hash = sha256_file(graph_path)
        for cores in CORE_COUNTS:
            plan_path, generation_seconds, plan_hash = generate_case_plan(graph_path, case_dir, cores)
            print(f"PLAN {graph_path.stem} cores={cores} sha256={plan_hash} "
                  f"generation_seconds={generation_seconds:.6f}", flush=True)
            for problem in PROBLEMS:
                multi_tasks.append((graph_path, plan_path, problem, cores, case_dir,
                                    graph_hash, generation_seconds))
    multi_records: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                run_one_evaluator,
                graph_path=graph_path, plan_path=plan_path, problem=str(problem), cores=cores,
                case_dir=case_dir, timeout_seconds=args.timeout_seconds,
                input_hash=graph_hash, generation_seconds=generation_seconds,
                integrity_scope="none",
                retain_trace=graph_path.stem in retain_trace_cases,
            ): (graph_path.stem, problem, cores)
            for graph_path, plan_path, problem, cores, case_dir, graph_hash, generation_seconds in multi_tasks
        }
        for index, future in enumerate(as_completed(futures), 1):
            record = future.result()
            if not record.get("reused"):
                multi_records.append(record)
            case, problem, cores = futures[future]
            print(f"CHECKPOINT multi {index}/{len(futures)} case={case} P{problem} cores={cores}", flush=True)
    summarize(output_root, case_paths)

    invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output_root / "last_invocation.json", invocation)
    print(f"DONE mode={args.mode}; reports refreshed under {output_root / 'reports'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

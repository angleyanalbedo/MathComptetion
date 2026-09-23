"""Run representative or full Phase 1 v001 evaluation with durable checkpoints."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from experiment_runner import (  # noqa: E402
    ALGORITHM_VERSION, CONFIG, CORE_COUNTS, PARAMETERS, PROBLEMS,
    IntegrityError, atomic_json, evaluator_fingerprint, run_one_evaluator,
    sha256_file, source_fingerprint,
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
                    "official_manifest_sha256", "cases", "core_counts", "problems"):
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
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    output_root = args.output_root.resolve()
    if not output_root.is_relative_to(ROOT):
        parser.error("--output-root must stay inside the project workspace")
    output_root.mkdir(parents=True, exist_ok=True)
    case_paths = sorted((ROOT / "official" / "data").glob("case_*.json"))
    if len(case_paths) != 100:
        raise RuntimeError(f"expected exactly 100 official graph files; found {len(case_paths)}")
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

    invocation = {
        "mode": args.mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timeout_seconds": args.timeout_seconds,
        "selected_cases": [path.stem for path in selected],
    }
    atomic_json(output_root / "last_invocation.json", invocation)
    print(f"START mode={args.mode} cases={len(selected)} timeout={args.timeout_seconds}s "
          f"algorithm={ALGORITHM_VERSION}", flush=True)

    # Run one single-core reference for each case before multi-core comparisons.
    for index, graph_path in enumerate(selected, 1):
        case_dir = output_root / "cases" / graph_path.stem
        try:
            run_one_evaluator(
                graph_path=graph_path, plan_path=None, problem="singlecore", cores=1,
                case_dir=case_dir, timeout_seconds=args.timeout_seconds,
                input_hash=sha256_file(graph_path), generation_seconds=None,
            )
        except IntegrityError:
            raise
        if index % 10 == 0 or index == len(selected):
            print(f"CHECKPOINT singlecore {index}/{len(selected)}", flush=True)
    summarize(output_root, case_paths)

    evaluations_per_case = len(CORE_COUNTS) * len(PROBLEMS)
    completed = 0
    for index, graph_path in enumerate(selected, 1):
        case_dir = output_root / "cases" / graph_path.stem
        graph_hash = sha256_file(graph_path)
        for cores in CORE_COUNTS:
            from experiment_runner import generate_case_plan
            plan_path, generation_seconds, plan_hash = generate_case_plan(graph_path, case_dir, cores)
            print(f"PLAN {graph_path.stem} cores={cores} sha256={plan_hash} "
                  f"generation_seconds={generation_seconds:.6f}", flush=True)
            for problem in PROBLEMS:
                try:
                    run_one_evaluator(
                        graph_path=graph_path, plan_path=plan_path, problem=str(problem), cores=cores,
                        case_dir=case_dir, timeout_seconds=args.timeout_seconds,
                        input_hash=graph_hash, generation_seconds=generation_seconds,
                    )
                except IntegrityError:
                    raise
                completed += 1
        summarize(output_root, case_paths)
        print(f"CHECKPOINT multi {index}/{len(selected)} "
              f"evaluations={completed}/{len(selected) * evaluations_per_case}", flush=True)

    invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(output_root / "last_invocation.json", invocation)
    print(f"DONE mode={args.mode}; reports refreshed under {output_root / 'reports'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

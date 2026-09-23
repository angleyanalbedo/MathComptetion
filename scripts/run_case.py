"""Generate one deterministic baseline plan and invoke selected evaluators."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from experiment_runner import (  # noqa: E402
    CORE_COUNTS, PROBLEMS, generate_case_plan, run_one_evaluator, sha256_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="official graph JSON")
    parser.add_argument("--cores", type=int, choices=CORE_COUNTS, default=2)
    parser.add_argument("--problems", type=str, default="1,2,3",
                        help="comma-separated problem ids, default: 1,2,3")
    parser.add_argument("--singlecore", action="store_true",
                        help="also run the official single-core reference")
    parser.add_argument("--output-root", type=Path,
                        default=ROOT / "experiments" / "phase1_baseline" / "v001")
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    args = parser.parse_args()

    graph_path = args.case.resolve()
    output_root = args.output_root.resolve()
    if not graph_path.is_file():
        parser.error(f"case file not found: {graph_path}")
    try:
        problems = tuple(dict.fromkeys(int(value) for value in args.problems.split(",") if value.strip()))
    except ValueError:
        parser.error("--problems must be a comma-separated subset of 1,2,3")
    if not problems or any(problem not in PROBLEMS for problem in problems):
        parser.error("--problems must be a comma-separated subset of 1,2,3")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    case_dir = output_root / "cases" / graph_path.stem
    input_hash = sha256_file(graph_path)
    if args.singlecore:
        run_one_evaluator(
            graph_path=graph_path, plan_path=None, problem="singlecore", cores=1,
            case_dir=case_dir, timeout_seconds=args.timeout_seconds,
            input_hash=input_hash, generation_seconds=None, integrity_scope="none",
        )
    plan_path, generation_seconds, plan_hash = generate_case_plan(graph_path, case_dir, args.cores)
    print(f"PLAN {graph_path.stem} cores={args.cores} sha256={plan_hash} "
          f"generation_seconds={generation_seconds:.6f}", flush=True)
    for problem in problems:
        run_one_evaluator(
            graph_path=graph_path, plan_path=plan_path, problem=str(problem), cores=args.cores,
            case_dir=case_dir, timeout_seconds=args.timeout_seconds,
            input_hash=input_hash, generation_seconds=generation_seconds, integrity_scope="none",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

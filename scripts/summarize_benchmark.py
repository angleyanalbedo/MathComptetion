"""Build case-level CSV, 12-group statistics, initial-best index, and analysis."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path

from experiment_runner import (ALGORITHM_VERSION, CONFIG, CORE_COUNTS, PROBLEMS,
                               ROOT, sha256_file, source_fingerprint)


FIELDS = [
    "case", "problem", "cores", "version", "status", "makespan",
    "singlecore_makespan", "speedup", "added_copy_bytes",
    "generation_seconds", "evaluator_seconds", "failure_reason",
    "cache_hits", "cache_accesses", "cache_hit_bytes", "cache_miss_bytes",
    "cache_hit_rate",
]


def _read_record(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _is_current_record(record: dict, case_path: Path, case_hash: str,
                       config_hash: str, code_hash: str) -> bool:
    fp = record.get("fingerprint", {})
    if (fp.get("case") != case_path.stem or fp.get("input_sha256") != case_hash
            or fp.get("config_sha256") != config_hash):
        return False
    if record.get("problem") == "singlecore":
        return record.get("version") == "official_singlecore_v1"
    params = fp.get("parameters", {})
    return (record.get("version") == ALGORITHM_VERSION
            and params.get("algorithm_version") == ALGORITHM_VERSION
            and params.get("algorithm_sha256") == code_hash)


def _latest_records(output_root: Path, case_paths: list[Path]) -> dict[tuple[str, str, int], dict]:
    by_case = {path.stem: path for path in case_paths}
    case_hashes = {path.stem: sha256_file(path) for path in case_paths}
    config_hash = sha256_file(CONFIG)
    code_hash = source_fingerprint()
    latest: dict[tuple[str, str, int], dict] = {}
    for record_path in (output_root / "cases").rglob("record.json"):
        record = _read_record(record_path)
        if not record or record.get("case") not in by_case:
            continue
        if not _is_current_record(record, by_case[record["case"]],
                                  case_hashes[record["case"]], config_hash, code_hash):
            continue
        key = (record["case"], record["problem"], int(record["cores"]))
        old = latest.get(key)
        if old is None or record.get("started_at", "") > old.get("started_at", ""):
            latest[key] = record
    return latest


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def _mean(values: list[float | int]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _stats_row(problem: int, cores: int, rows: list[dict], singles: dict[str, dict]) -> dict:
    group = [row for row in rows if row["problem"] == f"problem_{problem}" and row["cores"] == cores]
    successful = [row for row in group if row["status"] == "success"]
    speedups = [row["speedup"] for row in successful if isinstance(row.get("speedup"), (int, float))]
    added = [row["added_copy_bytes"] for row in successful if isinstance(row.get("added_copy_bytes"), (int, float))]
    statuses = {state: sum(row["status"] == state for row in group)
                for state in ("success", "illegal", "failed", "timeout")}
    statuses["not_run"] = max(0, 100 - sum(statuses.values()))
    result = {
        "problem": problem,
        "cores": cores,
        **statuses,
        "average_makespan": _mean([row["makespan"] for row in successful if row.get("makespan") is not None]),
        "average_speedup": _mean(speedups),
        "worst_speedup": min(speedups) if speedups else None,
        "slower_than_singlecore_cases": sum(
            row.get("makespan") is not None
            and singles.get(row["case"], {}).get("result", {}).get("makespan") is not None
            and row["makespan"] > singles[row["case"]]["result"]["makespan"]
            for row in successful),
        "average_added_copy_bytes": _mean(added),
        "average_generation_seconds": _mean([row["generation_seconds"] for row in successful
                                                if row.get("generation_seconds") is not None]),
        "average_evaluator_seconds": _mean([row["evaluator_seconds"] for row in successful
                                               if row.get("evaluator_seconds") is not None]),
        "cache_mean_case_hit_rate": None,
        "cache_weighted_hit_rate": None,
        "cache_total_hits": None,
        "cache_total_accesses": None,
        "cache_total_hit_bytes": None,
    }
    if problem == 3:
        cache_rows = [row for row in successful if row.get("cache_accesses") is not None]
        result.update({
            "cache_mean_case_hit_rate": _mean([row["cache_hit_rate"] for row in cache_rows
                                                if row.get("cache_hit_rate") is not None]),
            "cache_weighted_hit_rate": (
                sum(row["cache_hits"] for row in cache_rows) / sum(row["cache_accesses"] for row in cache_rows)
                if sum(row["cache_accesses"] for row in cache_rows) else None
            ),
            "cache_total_hits": sum(row["cache_hits"] for row in cache_rows),
            "cache_total_accesses": sum(row["cache_accesses"] for row in cache_rows),
            "cache_total_hit_bytes": sum(row["cache_hit_bytes"] for row in cache_rows),
        })
    return result


def _as_csv_row(case: str, problem: str, cores: int, record: dict | None,
                singlecore_makespan: int | float | None) -> dict:
    result = (record or {}).get("result", {})
    makespan = result.get("makespan") if record and record.get("status") == "success" else None
    speedup = (singlecore_makespan / makespan
               if problem != "singlecore" and makespan and singlecore_makespan else None)
    return {
        "case": case,
        "problem": problem,
        "cores": cores,
        "version": (record or {}).get("version", ALGORITHM_VERSION if problem != "singlecore" else "official_singlecore_v1"),
        "status": (record or {}).get("status", "not_run"),
        "makespan": makespan,
        "singlecore_makespan": singlecore_makespan,
        "speedup": speedup,
        "added_copy_bytes": result.get("added_copy_bytes"),
        "generation_seconds": (record or {}).get("generation_seconds"),
        "evaluator_seconds": (record or {}).get("evaluator_seconds"),
        "failure_reason": (record or {}).get("error"),
        "cache_hits": result.get("cache_hits"),
        "cache_accesses": result.get("cache_accesses"),
        "cache_hit_bytes": result.get("cache_hit_bytes"),
        "cache_miss_bytes": result.get("cache_miss_bytes"),
        "cache_hit_rate": result.get("cache_hit_rate"),
    }


def summarize(output_root: Path, case_paths: list[Path]) -> dict:
    latest = _latest_records(output_root, case_paths)
    singles = {case: record for (case, problem, _cores), record in latest.items()
               if problem == "singlecore"}
    rows: list[dict] = []
    for graph_path in case_paths:
        case = graph_path.stem
        single = singles.get(case)
        single_ms = (single or {}).get("result", {}).get("makespan") if single and single.get("status") == "success" else None
        rows.append(_as_csv_row(case, "singlecore", 1, single, single_ms))
        for cores in CORE_COUNTS:
            for problem in PROBLEMS:
                record = latest.get((case, f"problem_{problem}", cores))
                rows.append(_as_csv_row(case, f"problem_{problem}", cores, record, single_ms))

    _write_csv(output_root / "reports" / "per_case.csv", rows)
    stats = [_stats_row(problem, cores, rows, singles)
             for problem in PROBLEMS for cores in CORE_COUNTS]
    stats_path = output_root / "reports" / "summary_12_groups.csv"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    temp = stats_path.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(stats[0]))
        writer.writeheader()
        writer.writerows(stats)
    os.replace(temp, stats_path)

    best: dict[str, dict] = {f"problem_{problem}": {} for problem in PROBLEMS}
    for row in rows:
        if row["problem"] not in best or row["status"] != "success":
            continue
        plan_path = (output_root / "cases" / row["case"] / f"cores_{row['cores']}" / "plan.json")
        best[row["problem"]].setdefault(str(row["cores"]), {})[row["case"]] = {
            "version": ALGORITHM_VERSION,
            "makespan": row["makespan"],
            "plan_path": plan_path.relative_to(ROOT).as_posix(),
            "result_path": next((p for (case, prob, core), record in latest.items()
                                 if case == row["case"] and prob == row["problem"] and core == row["cores"]
                                 for p in record.get("output_paths", []) if p.endswith("result.json")), None),
        }
    best_path = output_root / "reports" / "initial_best.json"
    best_path.write_text(json.dumps(best, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_analysis(output_root / "reports" / "bottleneck_analysis.md", rows, stats, singles)
    return {"rows": len(rows), "successful_multi": sum(row["status"] == "success" for row in rows
                                                        if row["problem"].startswith("problem_")),
            "stats_groups": len(stats)}


def _write_analysis(path: Path, rows: list[dict], stats: list[dict], singles: dict) -> None:
    lines = [
        "# Phase 1 v001 baseline: initial bottleneck analysis", "",
        "Scope is the current set of completed records in `per_case.csv`. These are evaluator measurements, not explanations of causality.",
        "The current scheduler uses only deterministic topology order, fixed 64-op chunks, and cumulative `sum(cycles)` greedy assignment.", "",
        "## Group statistics", "",
        "See `summary_12_groups.csv` for the complete 12-group table. Successful rows alone enter metric averages; failed, illegal, timed-out, and not-run rows are shown separately.",
        "P3 cache rates: `cache_mean_case_hit_rate` is the arithmetic mean of available per-case rates; `cache_weighted_hit_rate` is total hits divided by total accesses.", "",
    ]
    complete = [row for row in rows if row["problem"].startswith("problem_") and row["status"] == "success"]
    for problem in (1, 2, 3):
        for cores in CORE_COUNTS:
            group = [row for row in complete if row["problem"] == f"problem_{problem}" and row["cores"] == cores]
            slow = sorted((row for row in group if row.get("speedup") is not None), key=lambda row: row["speedup"])[:10]
            lines.extend([f"## Problem {problem}, {cores} cores", "",
                          f"Successful cases: {len(group)}/100; slower than single-core: {sum(row.get('speedup') is not None and row['speedup'] < 1 for row in group)}.",
                          "Slowest speedups (measured):", ""])
            if slow:
                lines.extend(["| Case | Makespan | Single-core | Speedup | Added copy bytes |",
                               "|---|---:|---:|---:|---:|"])
                lines.extend(f"| {r['case']} | {r['makespan']} | {r['singlecore_makespan']} | {r['speedup']:.6f} | {r['added_copy_bytes']} |" for r in slow)
            else:
                lines.append("No completed comparable case yet.")
            copy_outliers = sorted(
                (row for row in group if isinstance(row.get("added_copy_bytes"), (int, float))),
                key=lambda row: row["added_copy_bytes"], reverse=True,
            )[:10]
            lines.extend(["", "Largest measured added-copy volumes:", ""])
            if copy_outliers:
                lines.extend(["| Case | Added copy bytes | Makespan | Speedup |",
                              "|---|---:|---:|---:|"])
                for row in copy_outliers:
                    speed = f"{row['speedup']:.6f}" if row.get("speedup") is not None else "N/A"
                    lines.append(f"| {row['case']} | {row['added_copy_bytes']} | {row['makespan']} | {speed} |")
            else:
                lines.append("No completed copy-byte results yet.")
            if problem == 3 and group:
                rates = [row["cache_hit_rate"] for row in group if row.get("cache_hit_rate") is not None]
                lines.append(f"Available P3 per-case cache hit rates: {len(rates)}/{len(group)}; mean={statistics.fmean(rates):.6f} when available.")
            lines.append("")

    lines.extend(["## Core-count regressions (measured)", "",
                  "A regression means makespan increased when moving to the next tested core count for the same case and problem.", ""])
    indexed = {(row["case"], row["problem"], row["cores"]): row for row in complete}
    regressions = []
    for (case, problem, cores), row in indexed.items():
        next_row = indexed.get((case, problem, cores + 1))
        if next_row and next_row["makespan"] > row["makespan"]:
            regressions.append((case, problem, cores, row["makespan"], cores + 1, next_row["makespan"]))
    if regressions:
        lines.extend(["| Case | Problem | Lower cores | Makespan | Higher cores | Makespan |",
                      "|---|---:|---:|---:|---:|---:|"])
        lines.extend(f"| {c} | {p} | {a} | {ma} | {b} | {mb} |" for c, p, a, ma, b, mb in regressions[:100])
    else:
        lines.append("No adjacent-core regressions found in currently completed comparable cases.")
    lines.extend(["", "## Added-copy outliers and interpretation", "",
                  "The per-case table contains all observed copy volumes. At full completion, the top 10 per problem/core are empirical outliers; high copy volume alone does not establish the cause of makespan.",
                  "Phase 2 hypotheses to test later (not implemented here): compare critical-path priority, cross-subgraph communication weighting, and PIPE-specific work balance one at a time; evaluate each against this frozen v001 baseline.", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "experiments" / "phase1_baseline" / "v001")
    args = parser.parse_args()
    cases = sorted((ROOT / "official" / "data").glob("case_*.json"))
    print(json.dumps(summarize(args.output_root.resolve(), cases), ensure_ascii=False))

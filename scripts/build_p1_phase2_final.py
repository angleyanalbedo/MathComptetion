"""Validate and compile the Phase 2 P1 closeout archive from raw records."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_phase2_round1 as common  # noqa: E402

OUT = ROOT / "experiments" / "phase2_problem1" / "final"
CORES = (2, 3, 4, 5)
CASES = [f"case_{i:03d}" for i in range(1, 101)]
SOURCES = {
    "round8_final": ("round8_cube_vector_pipe_full", "comm_partition_cube_vector_pipe_priority"),
    "round6_no_pipe_correction": ("round6_critical_path_full", "comm_partition_critical_path_priority"),
    "no_critical_path_pipe_work": ("final/ablations/no_critical_path_pipe_work", None),
    "no_communication_fixed256_pipe_cp": ("final/ablations/no_communication_fixed256_pipe_cp", None),
    "no_dependency_scheduler_group": ("round2_communication_full", "comm_256_w32_b128_384"),
    "dependency_list_increment": ("round4_dependency_full", "comm_partition_dependency_list"),
    "fixed256_greedy_increment": ("full_v001", "fixed_256"),
}
P2_ROOT = ROOT / "experiments" / "phase2_problem1"


def record_and_plan(alias: str, case: str, cores: int) -> tuple[Path, Path]:
    _base, candidate = SOURCES[alias]
    root = P2_ROOT / _base
    if alias == "no_critical_path_pipe_work":
        parent = root / "cases" / case / f"cores_{cores}"
        return parent / "record.json", parent / "plan.json"
    if alias == "no_communication_fixed256_pipe_cp":
        parent = root / "cases" / case / f"cores_{cores}"
        return parent / "record.json", parent / "plan.json"
    if alias == "fixed256_greedy_increment":
        parent = root / "cases" / case / f"cores_{cores}" / str(candidate)
        return parent / "record.json", parent / "plan.json"
    parent = root / "cases" / case / f"cores_{cores}" / str(candidate)
    return parent / "record.json", parent / "plan.json"


def verify_raw_record(record_path: Path, plan_path: Path, case: str) -> dict:
    if not record_path.is_file() or not plan_path.is_file():
        raise RuntimeError(f"missing record/plan: {record_path}")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("status") != "success":
        raise RuntimeError(f"non-success record {record_path}: {record.get('status')}")
    fp = record.get("fingerprint", {})
    if fp.get("input_sha256") != common.sha256_file(ROOT / "official" / "data" / f"{case}.json"):
        raise RuntimeError(f"input fingerprint mismatch: {record_path}")
    plan_sha = common.sha256_file(plan_path)
    if record.get("plan_sha256", fp.get("plan_sha256")) != plan_sha:
        raise RuntimeError(f"plan digest mismatch: {record_path}")
    if fp.get("plan_sha256") != plan_sha:
        raise RuntimeError(f"fingerprint plan digest mismatch: {record_path}")
    if fp.get("config_sha256") != common.sha256_file(common.CONFIG):
        raise RuntimeError(f"configuration fingerprint mismatch: {record_path}")
    if not record.get("output_sha256"):
        raise RuntimeError(f"record has no output hashes: {record_path}")
    for rel, expected in record["output_sha256"].items():
        artifact = ROOT / rel
        if not artifact.is_file() or common.sha256_file(artifact) != expected:
            raise RuntimeError(f"output hash mismatch: {artifact}")
    result_path = next((ROOT / rel for rel in record["output_sha256"] if rel.endswith("/result.json")), None)
    if result_path is None or json.loads(result_path.read_text(encoding="utf-8")).get("makespan") != record.get("result", {}).get("makespan"):
        raise RuntimeError(f"result JSON doesn't match record: {record_path}")
    return record


def load_variant(alias: str) -> list[dict]:
    rows = []
    for case in CASES:
        for cores in CORES:
            rec_path, plan_path = record_and_plan(alias, case, cores)
            record = verify_raw_record(rec_path, plan_path, case)
            if record.get("problem") not in ("1", 1) or record.get("cores") != cores:
                raise RuntimeError(f"problem/core mismatch: {rec_path}")
            result = record["result"]
            movement = result.get("data_movement_bytes", {})
            rows.append({"variant": alias, "case": case, "cores": cores,
                         "status": record["status"], "makespan": result["makespan"],
                         "added_copy_bytes": movement.get("added_copy_bytes"),
                         "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                         "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                         "generation_seconds": record.get("generation_seconds"),
                         "evaluator_seconds": record.get("evaluator_seconds"),
                         "plan_sha256": common.sha256_file(plan_path),
                         "record_sha256": common.sha256_file(rec_path),
                         "record_path": rec_path.relative_to(ROOT).as_posix(),
                         "plan_path": plan_path.relative_to(ROOT).as_posix(),
                         "input_sha256": record["fingerprint"]["input_sha256"],
                         "config_sha256": record["fingerprint"]["config_sha256"],
                         "evaluator_sha256": record["fingerprint"].get("evaluator_sha256"),
                         "algorithm_sha256": record["fingerprint"].get("algorithm_sha256")})
    return rows


def read_phase1() -> tuple[dict, dict]:
    rows = common.read_csv(ROOT / "experiments" / "phase1_baseline" / "v001" / "reports" / "per_case.csv")
    singles = {}
    multi = {}
    for row in rows:
        if row["problem"] == "singlecore":
            singles[row["case"]] = float(row["makespan"])
        elif row["problem"] == "problem_1":
            multi[(row["case"], int(row["cores"]))] = float(row["makespan"])
    if len(singles) != 100 or len(multi) != 400:
        raise RuntimeError("Phase 1 P1/singlecore reference rows are incomplete")
    return singles, multi


def csv_write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_curve(rows: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    curve = [{"cores": 1, "average_speedup": 1.0, "source": "singlecore reference"}]
    for cores in CORES:
        selected = [r for r in rows if r["variant"] == "round8_final" and r["cores"] == cores]
        curve.append({"cores": cores,
                      "average_speedup": sum(r["speedup_vs_singlecore"] for r in selected) / len(selected),
                      "source": "round8 final P1 best"})
    csv_write(OUT / "speedup_curve.csv", curve)
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=160)
    ax.plot([r["cores"] for r in curve], [r["average_speedup"] for r in curve], marker="o", linewidth=2)
    ax.set(xticks=[1, 2, 3, 4, 5], xlabel="Core count", ylabel="Mean per-case speedup",
           title="P1 final best: average speedup (100 cases)")
    ax.grid(True, alpha=.28)
    fig.tight_layout()
    fig.savefig(OUT / "speedup_curve.png")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    aliases = list(SOURCES)
    variant_rows = {alias: load_variant(alias) for alias in aliases}

    # The no-dependency module-group ablation must preserve the exact
    # communication partition; verify its partition IDs and evaluator outputs.
    plan_audit = []
    for case in CASES:
        for cores in CORES:
            comm_plan = json.loads(Path(variant_rows["round8_final"][((int(case[-3:])-1)*4)+(cores-2)]["plan_path"]).read_text(encoding="utf-8"))
            no_dep_plan = json.loads(Path(variant_rows["no_dependency_scheduler_group"][((int(case[-3:])-1)*4)+(cores-2)]["plan_path"]).read_text(encoding="utf-8"))
            if comm_plan["node_to_subgraph"] != no_dep_plan["node_to_subgraph"]:
                raise RuntimeError(f"round2 reused partition differs from final: {case}/{cores}")
            plan_audit.append({"case": case, "cores": cores,
                               "partition_identical_round2_round8": True,
                               "round8_plan_sha256": variant_rows["round8_final"][((int(case[-3:])-1)*4)+(cores-2)]["plan_sha256"],
                               "round2_plan_sha256": variant_rows["no_dependency_scheduler_group"][((int(case[-3:])-1)*4)+(cores-2)]["plan_sha256"]})
    csv_write(OUT / "plan_index.csv", [r for alias in aliases for r in variant_rows[alias]])
    csv_write(OUT / "reuse_partition_audit.csv", plan_audit)

    singles, v001 = read_phase1()
    all_rows = []
    for alias, values in variant_rows.items():
        for item in values:
            row = dict(item)
            row["singlecore_makespan"] = singles[item["case"]]
            row["speedup_vs_singlecore"] = singles[item["case"]] / item["makespan"]
            row["p1_v001_makespan"] = v001[(item["case"], item["cores"])]
            row["makespan_change_vs_v001_percent"] = 100 * (item["makespan"] / row["p1_v001_makespan"] - 1)
            all_rows.append(row)
    csv_write(OUT / "per_case_results.csv", all_rows)
    write_curve(all_rows)

    summaries = []
    for alias in aliases:
        for cores in CORES:
            selected = [r for r in all_rows if r["variant"] == alias and r["cores"] == cores]
            speed = [r["speedup_vs_singlecore"] for r in selected]
            summaries.append({"variant": alias, "cores": cores, "success": sum(r["status"] == "success" for r in selected),
                              "illegal": sum(r["status"] == "illegal" for r in selected),
                              "failed": sum(r["status"] == "failed" for r in selected),
                              "timeout": sum(r["status"] == "timeout" for r in selected),
                              "mean_makespan": sum(r["makespan"] for r in selected) / len(selected),
                              "mean_speedup": sum(speed) / len(speed),
                              "equal_weight_mean_speedup_2_to_5": None,
                              "slower_than_singlecore_cases": sum(r["speedup_vs_singlecore"] < 1 for r in selected),
                              "improved_vs_round8": sum(r["makespan"] < next(x["makespan"] for x in all_rows if x["variant"] == "round8_final" and x["case"] == r["case"] and x["cores"] == cores) for r in selected),
                              "tied_vs_round8": sum(r["makespan"] == next(x["makespan"] for x in all_rows if x["variant"] == "round8_final" and x["case"] == r["case"] and x["cores"] == cores) for r in selected),
                              "regressed_vs_round8": sum(r["makespan"] > next(x["makespan"] for x in all_rows if x["variant"] == "round8_final" and x["case"] == r["case"] and x["cores"] == cores) for r in selected),
                              "mean_added_copy_bytes": sum(r["added_copy_bytes"] or 0 for r in selected) / len(selected),
                              "mean_partition_added_copy_bytes": sum(r["partition_added_copy_bytes"] or 0 for r in selected) / len(selected),
                              "mean_spill_added_copy_bytes": sum(r["spill_added_copy_bytes"] or 0 for r in selected) / len(selected),
                              "total_generation_seconds": sum(r["generation_seconds"] or 0 for r in selected),
                              "total_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in selected),
                              "mean_generation_seconds": sum(r["generation_seconds"] or 0 for r in selected) / len(selected),
                              "mean_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in selected) / len(selected)})
    for item in summaries:
        item["equal_weight_mean_speedup_2_to_5"] = sum(
            next(x["mean_speedup"] for x in summaries if x["variant"] == item["variant"] and x["cores"] == c)
            for c in CORES) / len(CORES)
    csv_write(OUT / "core_summary.csv", summaries)

    final = [r for r in all_rows if r["variant"] == "round8_final"]
    round6 = [r for r in all_rows if r["variant"] == "round6_no_pipe_correction"]
    keyed = {(r["case"], r["cores"]): r for r in final}
    deltas = []
    for r in round6:
        f = keyed[(r["case"], r["cores"])]
        deltas.append({"case": r["case"], "cores": r["cores"],
                       "round6_makespan": r["makespan"], "round8_makespan": f["makespan"],
                       "round8_change_percent_vs_round6": 100 * (f["makespan"] / r["makespan"] - 1),
                       "round6_speedup": r["speedup_vs_singlecore"], "round8_speedup": f["speedup_vs_singlecore"],
                       "added_copy_round6": r["added_copy_bytes"], "added_copy_round8": f["added_copy_bytes"],
                       "spill_round6": r["spill_added_copy_bytes"], "spill_round8": f["spill_added_copy_bytes"]})
    csv_write(OUT / "round8_vs_round6_per_case.csv", deltas)
    totals = Counter("improved" if r["round8_makespan"] < r["round6_makespan"] else
                     "tied" if r["round8_makespan"] == r["round6_makespan"] else "regressed" for r in deltas)
    marginal = []
    for cores in CORES:
        part = [r for r in deltas if r["cores"] == cores]
        marginal.append({"module_added": "Cube/Vector Pipe critical-path tail", "cores": cores,
                         "improved": sum(r["round8_makespan"] < r["round6_makespan"] for r in part),
                         "tied": sum(r["round8_makespan"] == r["round6_makespan"] for r in part),
                         "regressed": sum(r["round8_makespan"] > r["round6_makespan"] for r in part),
                         "mean_speedup_round6": sum(r["round6_speedup"] for r in part) / len(part),
                         "mean_speedup_round8": sum(r["round8_speedup"] for r in part) / len(part),
                         "mean_speedup_delta": sum(r["round8_speedup"] - r["round6_speedup"] for r in part) / len(part),
                         "mean_makespan_delta_percent": sum(r["round8_change_percent_vs_round6"] for r in part) / len(part)})
    csv_write(OUT / "module_marginal_by_core.csv", marginal)

    # Pairwise ablation table: positive delta means removal worsens Makespan.
    ablation_aliases = ["round6_no_pipe_correction", "no_critical_path_pipe_work",
                        "no_communication_fixed256_pipe_cp", "no_dependency_scheduler_group"]
    ablation_rows = []
    for alias in ablation_aliases:
        for cores in CORES:
            pairs = [(r, keyed[(r["case"], cores)]) for r in all_rows if r["variant"] == alias and r["cores"] == cores]
            ms_delta = [100 * (a["makespan"] / b["makespan"] - 1) for a, b in pairs]
            ablation_rows.append({"ablation": alias, "cores": cores,
                                  "cases": len(pairs), "improved_vs_final": sum(a["makespan"] < b["makespan"] for a, b in pairs),
                                  "tied_vs_final": sum(a["makespan"] == b["makespan"] for a, b in pairs),
                                  "regressed_vs_final": sum(a["makespan"] > b["makespan"] for a, b in pairs),
                                  "mean_speedup": sum(a["speedup_vs_singlecore"] for a, _ in pairs) / len(pairs),
                                  "mean_makespan_change_vs_final_percent": sum(ms_delta) / len(ms_delta),
                                  "worst_makespan_change_vs_final_percent": max(ms_delta),
                                  "mean_added_copy_bytes": sum(a["added_copy_bytes"] or 0 for a, _ in pairs) / len(pairs),
                                  "mean_partition_added_copy_bytes": sum(a["partition_added_copy_bytes"] or 0 for a, _ in pairs) / len(pairs),
                                  "mean_spill_added_copy_bytes": sum(a["spill_added_copy_bytes"] or 0 for a, _ in pairs) / len(pairs)})
    csv_write(OUT / "ablation_summary.csv", ablation_rows)

    incremental = []
    for alias in ("fixed256_greedy_increment", "no_dependency_scheduler_group", "dependency_list_increment",
                  "round6_no_pipe_correction", "round8_final"):
        per = [r for r in all_rows if r["variant"] == alias]
        core_means = [sum(r["speedup_vs_singlecore"] for r in per if r["cores"] == c) / 100 for c in CORES]
        incremental.append({"historical_variant": alias, "status": "historical incremental (not final removal ablation)",
                            "mean_speedup_2_to_5_equal_weight": sum(core_means) / 4,
                            "mean_speedup_core2": core_means[0], "mean_speedup_core3": core_means[1],
                            "mean_speedup_core4": core_means[2], "mean_speedup_core5": core_means[3]})
    csv_write(OUT / "historical_incremental.csv", incremental)

    regressions = sorted(deltas, key=lambda r: r["round8_change_percent_vs_round6"], reverse=True)[:30]
    csv_write(OUT / "regression_top30_round8_vs_round6.csv", regressions)
    run_times = []
    for alias in aliases:
        selected = [r for r in all_rows if r["variant"] == alias]
        run_times.append({"variant": alias, "rows": len(selected),
                          "sum_recorded_generation_seconds": sum(r["generation_seconds"] or 0 for r in selected),
                          "sum_recorded_evaluator_seconds": sum(r["evaluator_seconds"] or 0 for r in selected),
                          "note": "historical/reused records retain original per-record timings; not current wall-clock"})
    csv_write(OUT / "runtime_summary.csv", run_times)

    speed_by_variant = {x["historical_variant"]: x["mean_speedup_2_to_5_equal_weight"] for x in incremental}
    best_alias = max(speed_by_variant, key=speed_by_variant.get)
    if best_alias != "round8_final":
        raise RuntimeError(f"Best protocol selects {best_alias}, not round8; update best without search")
    if totals != Counter({"improved": 23, "tied": 348, "regressed": 29}):
        raise RuntimeError(f"round8-round6 pair counts disagree with declared result: {totals}")
    if any(s["success"] != 100 or s["illegal"] or s["failed"] or s["timeout"] for s in summaries):
        raise RuntimeError("one or more archived variants are incomplete or contain evaluator failures")

    audit = {"status": "passed", "variants": {a: {"rows": len(variant_rows[a]), "all_record_plan_input_config_output_hashes_verified": True} for a in aliases},
             "no_dependency_partition_identical_to_round8": True,
             "round8_vs_round6_counts": dict(totals),
             "best_by_equal_weight_speedup": best_alias,
             "round8_equal_weight_mean_speedup": speed_by_variant["round8_final"],
             "all_variants_400_success": True,
             "official_directory_modified_by_this_closeout": False}
    common.atomic_json(OUT / "validation_audit.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

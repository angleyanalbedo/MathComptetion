#!/usr/bin/env python3
"""Build reproducible P1 paper tables, figures, and provenance without changing experiment data."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "experiments/phase1_baseline/v001/reports/per_case.csv"
DEPENDENCY = ROOT / "experiments/phase2_problem1/round4_dependency_full/full_per_case.csv"
DEPENDENCY_SUMMARY = ROOT / "experiments/phase2_problem1/round4_dependency_full/full_summary.csv"
DEPENDENCY_MANIFEST = ROOT / "experiments/phase2_problem1/round4_dependency_full/round_manifest.json"
CRITICAL_PATH = ROOT / "experiments/phase2_problem1/round6_critical_path_full/all_per_case.csv"
CRITICAL_PATH_MANIFEST = ROOT / "experiments/phase2_problem1/round6_critical_path_full/round_manifest.json"
PIPE_PRIORITY = ROOT / "experiments/phase2_problem1/round8_cube_vector_pipe_full/all_per_case.csv"
PIPE_SUMMARY = ROOT / "experiments/phase2_problem1/round8_cube_vector_pipe_full/all_summary.csv"
PIPE_MANIFEST = ROOT / "experiments/phase2_problem1/round8_cube_vector_pipe_full/round_manifest.json"
FINAL_DIR = ROOT / "experiments/phase2_problem1/final"
FINAL_REPORT = FINAL_DIR / "FINAL_REPORT.md"
FINAL_CASES = FINAL_DIR / "per_case_results.csv"
FINAL_ABLATIONS = FINAL_DIR / "ablation_summary.csv"
FINAL_AUDIT = FINAL_DIR / "validation_audit.json"
FINAL_ROUND8_VS_ROUND6 = FINAL_DIR / "round8_vs_round6_per_case.csv"
OUT = ROOT / "experiments/paper_materials/problem1_v001"
CORES = (2, 3, 4, 5)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "Microsoft YaHei", "axes.unicode_minus": False,
                         "figure.dpi": 150, "savefig.dpi": 200})

    base_rows = read_csv(BASELINE)
    base = {}
    for r in base_rows:
        if r["status"] != "success" or r["problem"] not in ("singlecore", "problem_1"):
            continue
        case = r["case"]
        if r["problem"] == "singlecore":
            base[(case, 1)] = {"single": float(r["makespan"])}
        else:
            base.setdefault((case, int(r["cores"])), {})["baseline"] = float(r["makespan"])
            base[(case, int(r["cores"]))]["baseline_copy"] = float(r["added_copy_bytes"] or 0)

    dep_rows = [r for r in read_csv(DEPENDENCY) if r["problem"] == "1"]
    if len(dep_rows) != 400:
        raise SystemExit(f"Expected 400 P1 rows in {DEPENDENCY}, found {len(dep_rows)}")
    cp_rows = read_csv(CRITICAL_PATH)
    pipe_rows = read_csv(PIPE_PRIORITY)
    pipe_plan_rows = read_csv(ROOT / "experiments/phase2_problem1/round8_cube_vector_pipe_full/plan_manifest.csv")
    if len(cp_rows) != 400 or len(pipe_rows) != 400 or len(pipe_plan_rows) != 400:
        raise SystemExit(f"Expected 400 rows in each full/plan manifest; found {len(cp_rows)}, {len(pipe_rows)}, {len(pipe_plan_rows)}")
    cp_by_key = {(r["case"], int(r["cores"])): r for r in cp_rows}
    pipe_by_key = {(r["case"], int(r["cores"])): r for r in pipe_rows}
    pipe_plan_by_key = {(r["case"], int(r["cores"])): r for r in pipe_plan_rows}
    closeout_rows = read_csv(FINAL_CASES)
    closeout_ablation_rows = read_csv(FINAL_ABLATIONS)
    audit = json.loads(FINAL_AUDIT.read_text(encoding="utf-8"))
    if audit.get("status") != "passed" or not audit.get("all_variants_400_success"):
        raise SystemExit("Final P1 closeout audit is not passed; refusing to publish updated material")
    final_best_rows = [r for r in closeout_rows if r["variant"] == "round8_final"]
    if len(final_best_rows) != 400 or any(r["status"] != "success" for r in final_best_rows):
        raise SystemExit("Final round8 closeout rows are incomplete or unsuccessful")
    final_best_by_key = {(r["case"], int(r["cores"])): r for r in final_best_rows}
    if set(cp_by_key) != set(pipe_by_key):
        raise SystemExit("Critical-path and Pipe-priority full results have mismatched case/core keys")
    joined: list[dict] = []
    for r in dep_rows:
        case, cores = r["case"], int(r["cores"])
        ref = base.get((case, cores), {})
        single = base.get((case, 1), {}).get("single")
        if single is None or "baseline" not in ref:
            raise SystemExit(f"Missing baseline/singlecore match for {case}, {cores} cores")
        candidate = float(r["makespan"])
        comm_greedy = float(r["communication_greedy_makespan"])
        baseline = ref["baseline"]
        cp = cp_by_key[(case, cores)]
        pipe = pipe_by_key[(case, cores)]
        pipe_plan = pipe_plan_by_key[(case, cores)]
        if cp["status"] != "success" or pipe["status"] != "success":
            raise SystemExit(f"Non-success full result for {case}, {cores} cores")
        cp_ms, pipe_ms = float(cp["makespan"]), float(pipe["makespan"])
        final_best = final_best_by_key[(case, cores)]
        if float(final_best["makespan"]) != pipe_ms:
            raise SystemExit(f"Closeout and round8 result mismatch for {case}, {cores} cores")
        joined.append({
            "case": case, "problem": 1, "cores": cores,
            "baseline_version": "shared_topology_contiguous64_greedy_cycles_v001",
            "communication_version": "p1_bounded_communication_cuts_v001_greedy_assignment",
            "candidate_version": "p1_dependency_list_schedule_round4_v001",
            "status": r["status"], "singlecore_makespan": single,
            "baseline_makespan": baseline, "communication_greedy_makespan": comm_greedy,
            "candidate_makespan": candidate,
            "critical_path_makespan": cp_ms, "pipe_priority_makespan": pipe_ms,
            "baseline_speedup": single / baseline,
            "communication_speedup": single / comm_greedy,
            "candidate_speedup": single / candidate,
            "critical_path_speedup": single / cp_ms, "pipe_priority_speedup": single / pipe_ms,
            "candidate_makespan_change_vs_baseline_percent": (candidate / baseline - 1) * 100,
            "candidate_makespan_reduction_vs_baseline_percent": (1 - candidate / baseline) * 100,
            "candidate_makespan_change_vs_comm_percent": (candidate / comm_greedy - 1) * 100,
            "critical_path_makespan_change_vs_baseline_percent": (cp_ms / baseline - 1) * 100,
            "pipe_priority_makespan_change_vs_baseline_percent": (pipe_ms / baseline - 1) * 100,
            "pipe_priority_makespan_change_vs_critical_path_percent": (pipe_ms / cp_ms - 1) * 100,
            "baseline_added_copy_bytes": ref["baseline_copy"],
            "candidate_added_copy_bytes_including_spill": float(r["added_copy_bytes_including_spill"]),
            "candidate_partition_added_copy_bytes": float(r["partition_added_copy_bytes"]),
            "candidate_spill_added_copy_bytes": float(r["spill_added_copy_bytes"]),
            "pipe_priority_added_copy_bytes_including_spill": float(pipe["added_copy_bytes_including_spill"]),
            "generation_seconds": float(r["generation_seconds"]),
            "evaluator_seconds": float(r["evaluator_seconds"]),
            "plan_sha256": r["plan_sha256"], "record_path": r["record_path"],
            "pipe_priority_plan_sha256": pipe_plan["plan_sha256"],
            "critical_path_record_path": cp["record_path"], "pipe_priority_record_path": pipe["record_path"],
        })
    joined.sort(key=lambda x: (x["case"], x["cores"]))
    fields = list(joined[0])
    write_csv(OUT / "p1_per_case_comparison.csv", joined, fields)

    summaries = []
    for cores in CORES:
        group = [r for r in joined if r["cores"] == cores]
        summaries.append({
            "cores": cores, "case_count": len(group), "successful": sum(r["status"] == "success" for r in group),
            "baseline_mean_makespan_cycles": mean([r["baseline_makespan"] for r in group]),
            "communication_mean_makespan_cycles": mean([r["communication_greedy_makespan"] for r in group]),
            "candidate_mean_makespan_cycles": mean([r["candidate_makespan"] for r in group]),
            "critical_path_mean_makespan_cycles": mean([r["critical_path_makespan"] for r in group]),
            "pipe_priority_mean_makespan_cycles": mean([r["pipe_priority_makespan"] for r in group]),
            "baseline_mean_case_speedup": mean([r["baseline_speedup"] for r in group]),
            "communication_mean_case_speedup": mean([r["communication_speedup"] for r in group]),
            "candidate_mean_case_speedup": mean([r["candidate_speedup"] for r in group]),
            "critical_path_mean_case_speedup": mean([r["critical_path_speedup"] for r in group]),
            "pipe_priority_mean_case_speedup": mean([r["pipe_priority_speedup"] for r in group]),
            "pipe_priority_speedup_change_vs_critical_path_percent": (mean([r["pipe_priority_speedup"] for r in group]) / mean([r["critical_path_speedup"] for r in group]) - 1) * 100,
            "pipe_priority_mean_makespan_change_vs_critical_path_percent": mean([r["pipe_priority_makespan_change_vs_critical_path_percent"] for r in group]),
            "pipe_priority_improved_cases_vs_critical_path": sum(r["pipe_priority_makespan"] < r["critical_path_makespan"] for r in group),
            "pipe_priority_regressed_cases_vs_critical_path": sum(r["pipe_priority_makespan"] > r["critical_path_makespan"] for r in group),
            "pipe_priority_tied_cases_vs_critical_path": sum(r["pipe_priority_makespan"] == r["critical_path_makespan"] for r in group),
            "candidate_mean_speedup_gain_vs_baseline_percent": (mean([r["candidate_speedup"] for r in group]) / mean([r["baseline_speedup"] for r in group]) - 1) * 100,
            "candidate_mean_makespan_change_vs_baseline_percent": (mean([r["candidate_makespan"] for r in group]) / mean([r["baseline_makespan"] for r in group]) - 1) * 100,
            "improved_cases_vs_baseline": sum(r["candidate_makespan"] < r["baseline_makespan"] for r in group),
            "regressed_cases_vs_baseline": sum(r["candidate_makespan"] > r["baseline_makespan"] for r in group),
            "tied_cases_vs_baseline": sum(r["candidate_makespan"] == r["baseline_makespan"] for r in group),
            "slower_than_singlecore_cases": sum(r["candidate_makespan"] > r["singlecore_makespan"] for r in group),
            "mean_candidate_added_copy_bytes_including_spill": mean([r["candidate_added_copy_bytes_including_spill"] for r in group]),
            "mean_baseline_added_copy_bytes": mean([r["baseline_added_copy_bytes"] for r in group]),
            "mean_candidate_generation_seconds": mean([r["generation_seconds"] for r in group]),
            "mean_candidate_evaluator_seconds": mean([r["evaluator_seconds"] for r in group]),
        })
    write_csv(OUT / "p1_summary_by_core.csv", summaries, list(summaries[0]))
    s = {r["cores"]: r for r in summaries}

    # Carry the final closeout evidence and ablation matrix into the paper bundle.
    write_csv(OUT / "p1_final_closeout_per_case.csv", closeout_rows, list(closeout_rows[0]))
    round8_round6_rows = read_csv(FINAL_ROUND8_VS_ROUND6)
    write_csv(OUT / "p1_round8_vs_round6_per_case.csv", round8_round6_rows, list(round8_round6_rows[0]))
    ablation_labels = {
        "round6_no_pipe_correction": "Remove Cube/Vector correction",
        "no_critical_path_pipe_work": "Remove critical-path tail",
        "no_communication_fixed256_pipe_cp": "Remove communication cuts",
        "no_dependency_scheduler_group": "Remove dependency-scheduler module group",
    }
    ablation_groups = {name: [r for r in closeout_ablation_rows if r["ablation"] == name]
                       for name in ablation_labels}
    if any(len(rows) != 4 for rows in ablation_groups.values()):
        raise SystemExit("Expected four core-count rows for every final-composition ablation")
    ablation_summary = []
    final_best_group = [r for r in joined]
    ablation_summary.append({
        "variant": "round8_final", "interpretation": "Frozen P1 best",
        "equal_weight_mean_speedup_2_to_5": mean([r["pipe_priority_mean_case_speedup"] for r in summaries]),
        "mean_makespan_change_vs_final_percent": 0.0,
        "improved_vs_final": 0, "tied_vs_final": 400, "regressed_vs_final": 0,
        "successful_rows": 400,
    })
    for name, rows in ablation_groups.items():
        rows = sorted(rows, key=lambda r: int(r["cores"]))
        ablation_summary.append({
            "variant": name, "interpretation": ablation_labels[name],
            "equal_weight_mean_speedup_2_to_5": mean([float(r["mean_speedup"]) for r in rows]),
            "mean_makespan_change_vs_final_percent": mean([float(r["mean_makespan_change_vs_final_percent"]) for r in rows]),
            "improved_vs_final": sum(int(r["improved_vs_final"]) for r in rows),
            "tied_vs_final": sum(int(r["tied_vs_final"]) for r in rows),
            "regressed_vs_final": sum(int(r["regressed_vs_final"]) for r in rows),
            "successful_rows": sum(int(r["cases"]) for r in rows),
            **{f"cores_{r['cores']}_mean_speedup": float(r["mean_speedup"]) for r in rows},
            **{f"cores_{r['cores']}_mean_makespan_change_percent": float(r["mean_makespan_change_vs_final_percent"]) for r in rows},
        })
    # Include per-core columns on the round8 row for a self-contained comparison table.
    ablation_summary[0].update({
        **{f"cores_{r['cores']}_mean_speedup": float(r["pipe_priority_mean_case_speedup"]) for r in summaries},
        **{f"cores_{r['cores']}_mean_makespan_change_percent": 0.0 for r in summaries},
    })
    write_csv(OUT / "p1_ablation_summary.csv", ablation_summary, list(ablation_summary[0]))

    comparison_counts = Counter()
    for r in round8_round6_rows:
        change = float(r["round8_change_percent_vs_round6"])
        comparison_counts["improved" if change < 0 else "regressed" if change > 0 else "tied"] += 1
    if comparison_counts != Counter({"improved": 23, "tied": 348, "regressed": 29}):
        raise SystemExit(f"Unexpected round8 vs round6 counts: {dict(comparison_counts)}")
    pipe_totals = {
        "added_copy_bytes": mean([float(r["added_copy_bytes"]) for r in final_best_rows]),
        "partition_added_copy_bytes": mean([float(r["partition_added_copy_bytes"]) for r in final_best_rows]),
        "spill_added_copy_bytes": mean([float(r["spill_added_copy_bytes"]) for r in final_best_rows]),
    }

    # Representative examples are selected by transparent, reproducible criteria.
    improvement = sorted(joined, key=lambda r: r["pipe_priority_makespan_change_vs_baseline_percent"])
    worst = sorted(joined, key=lambda r: r["pipe_priority_makespan_change_vs_baseline_percent"], reverse=True)
    high_copy = sorted(joined, key=lambda r: r["pipe_priority_added_copy_bytes_including_spill"], reverse=True)
    examples = []
    chosen = [("largest_makespan_reduction_vs_baseline", improvement[0]),
              ("largest_makespan_regression_vs_baseline", worst[0]),
              ("maximum_added_copy_bytes", high_copy[0])]
    seen = set()
    for label, r in chosen:
        key = (r["case"], r["cores"])
        if key not in seen:
            examples.append({"selection_rule": label, **r})
            seen.add(key)
    write_csv(OUT / "p1_typical_cases.csv", examples, list(examples[0]))

    # Figure 1: mean per-case speedup by core count and algorithm.
    fig, ax = plt.subplots(figsize=(10.2, 5.4))
    x = np.arange(len(CORES)); width = 0.16
    for i, (key, label, color) in enumerate([
        ("baseline_mean_case_speedup", "Phase 1 baseline", "#64748b"),
        ("communication_mean_case_speedup", "通信切图 + 贪心分核", "#0ea5e9"),
        ("candidate_mean_case_speedup", "通信切图 + 依赖感知调度", "#16a34a"),
        ("critical_path_mean_case_speedup", "关键路径优先级", "#f59e0b"),
        ("pipe_priority_mean_case_speedup", "Cube/Vector 管线关键路径", "#9333ea"),
    ]):
        vals = [s[key] for s in summaries]
        bars = ax.bar(x + (i - 2) * width, vals, width, label=label, color=color)
        ax.bar_label(bars, fmt="%.4f", fontsize=6, padding=2)
    ax.axhline(1, color="#9ca3af", lw=1, ls="--")
    ax.set_xticks(x, [f"{c}核" for c in CORES]); ax.set_ylabel("平均逐 case speedup（倍）")
    ax.set_title("P1：各核数平均逐 case 加速比（100 个正式 case）")
    ax.legend(frameon=False); ax.grid(axis="y", alpha=.2); fig.tight_layout()
    fig.savefig(OUT / "fig1_speedup_by_core.png"); plt.close(fig)

    # Figure 2: average makespan, normalized to phase-1 baseline per same case/core.
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    for key, label, color in [
        ("baseline_mean_makespan_cycles", "Phase 1 baseline", "#64748b"),
        ("communication_mean_makespan_cycles", "通信切图 + 贪心分核", "#0ea5e9"),
        ("candidate_mean_makespan_cycles", "依赖感知调度", "#16a34a"),
        ("critical_path_mean_makespan_cycles", "关键路径优先级", "#f59e0b"),
        ("pipe_priority_mean_makespan_cycles", "Cube/Vector 管线关键路径", "#9333ea")]:
        vals = [s[key] / s["baseline_mean_makespan_cycles"] for s in summaries]
        ax.plot(CORES, vals, marker="o", lw=2, label=label, color=color)
        for cx, val in zip(CORES, vals): ax.annotate(f"{val:.2f}", (cx, val), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=8)
    ax.axhline(1, color="#9ca3af", lw=1, ls="--", label="Phase 1 baseline = 1")
    ax.set_xticks(CORES, [f"{c}核" for c in CORES]); ax.set_ylabel("平均 Makespan / baseline 平均 Makespan")
    ax.set_title("P1：平均 Makespan 对照（100 个正式 case）")
    ax.legend(frameon=False); ax.grid(alpha=.2); fig.tight_layout()
    fig.savefig(OUT / "fig2_makespan_ratio.png"); plt.close(fig)

    # Figure 3: case-level improvement/regression distribution.
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    vals = [[-r["pipe_priority_makespan_change_vs_baseline_percent"] for r in joined if r["cores"] == c] for c in CORES]
    bp = ax.boxplot(vals, tick_labels=[f"{c}核" for c in CORES], showfliers=False, patch_artist=True)
    for box in bp["boxes"]: box.set_facecolor("#86efac")
    ax.axhline(0, color="#dc2626", lw=1, ls="--")
    ax.set_ylabel("相对 baseline 的 Makespan 降幅（%，正值为改善）")
    ax.set_title("P1：逐 case 改善/退化分布（每核数 n=100；隐藏离群点仅为显示）")
    ax.grid(axis="y", alpha=.2); fig.tight_layout()
    fig.savefig(OUT / "fig3_case_change_distribution.png"); plt.close(fig)

    # Figure 4: added-copy volume versus case-level makespan reduction.
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    for cores, color in zip(CORES, ["#0284c7", "#16a34a", "#f59e0b", "#9333ea"]):
        group = [r for r in joined if r["cores"] == cores]
        ax.scatter([r["pipe_priority_added_copy_bytes_including_spill"] / (1024**2) for r in group],
                   [-r["pipe_priority_makespan_change_vs_baseline_percent"] for r in group],
                   s=19, alpha=.62, label=f"{cores}核", color=color)
    ax.axhline(0, color="#6b7280", lw=1, ls="--")
    ax.set_xlabel("候选方案 added_copy_bytes（含 spill，MiB）")
    ax.set_ylabel("相对 baseline 的 Makespan 降幅（%，正值为改善）")
    ax.set_title("P1：额外搬运量与逐 case Makespan 变化（400 个 case×核数点）")
    ax.legend(title="核数", frameon=False); ax.grid(alpha=.18); fig.tight_layout()
    fig.savefig(OUT / "fig4_copy_vs_makespan.png"); plt.close(fig)

    # Figure 5: method schematic.
    fig, ax = plt.subplots(figsize=(10, 3.2)); ax.axis("off")
    boxes = [(0.03, "原始计算图\n完整依赖 DAG"), (0.27, "通信感知连续切图\n目标 256；范围 128–384\n窗口 ±32"),
             (0.53, "构造 Task DAG\n保留跨 Task 前驱\n计算 cycles 作为代理"),
             (0.78, "依赖 + 关键路径优先级\nCube/Vector 按 max(pipe cycles)\n官方 evaluator 实测")]
    for x0, label in boxes:
        ax.text(x0 + .085, .53, label, ha="center", va="center", fontsize=10,
                bbox={"boxstyle": "round,pad=0.6", "fc": "#eff6ff", "ec": "#2563eb", "lw": 1.2}, transform=ax.transAxes)
    for x0 in [.19, .44, .70]:
        ax.annotate("", xy=(x0 + .065, .53), xytext=(x0, .53), xycoords=ax.transAxes,
                    arrowprops={"arrowstyle": "->", "lw": 1.8, "color": "#334155"})
    ax.text(.5, .06, "cycle 仅作启发式代理；报告 Makespan、speedup、搬运量均取官方 evaluator 输出",
            ha="center", va="center", fontsize=9, color="#334155", transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(OUT / "fig5_method_pipeline.png"); plt.close(fig)

    # Figure 6: final-composition removal ablations.
    fig, ax = plt.subplots(figsize=(10.2, 5.2))
    labels = ["Final round8", "No Cube/Vector", "No critical-path tail", "No communication cuts", "No dependency scheduler group"]
    values = [float(r["equal_weight_mean_speedup_2_to_5"]) for r in ablation_summary]
    colors = ["#7c3aed", "#94a3b8", "#f59e0b", "#ef4444", "#0ea5e9"]
    bars = ax.bar(np.arange(len(labels)), values, color=colors, width=.68)
    ax.bar_label(bars, fmt="%.4f", padding=3, fontsize=8)
    ax.set_xticks(np.arange(len(labels)), labels, rotation=15, ha="right")
    ax.set_ylabel("400 case×core 的等权平均逐 case speedup（倍）")
    ax.set_title("P1 最终组合消融：移除模块后的全量结果")
    ax.grid(axis="y", alpha=.2); fig.tight_layout()
    fig.savefig(OUT / "fig6_ablation_speedup.png"); plt.close(fig)

    # Figure 7: exact case×core outcomes of adding the Pipe correction to round6.
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    outcome_labels = ["改善", "持平", "退化"]
    outcome_values = [comparison_counts["improved"], comparison_counts["tied"], comparison_counts["regressed"]]
    bars = ax.bar(outcome_labels, outcome_values, color=["#16a34a", "#94a3b8", "#ef4444"])
    ax.bar_label(bars, padding=3, fontsize=10)
    ax.set_ylabel("case × core 数量（总计 400）")
    ax.set_title("Cube/Vector 修正相对关键路径版本的逐项变化")
    ax.set_ylim(0, max(outcome_values) * 1.14); ax.grid(axis="y", alpha=.2); fig.tight_layout()
    fig.savefig(OUT / "fig7_round8_vs_round6_counts.png"); plt.close(fig)

    # Figure 8: final score curve with the single-core reference normalized to 1.
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    curve_x = (1, *CORES)
    curve_y = (1.0, *(s[c]["pipe_priority_mean_case_speedup"] for c in CORES))
    ax.plot(curve_x, curve_y, marker="o", lw=2.3, color="#7c3aed")
    for cx, cy in zip(curve_x, curve_y):
        ax.annotate(f"{cy:.4f}", (cx, cy), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9)
    ax.set_xticks(curve_x, [f"{c}核" for c in curve_x]); ax.set_ylabel("平均逐 case speedup（倍）")
    ax.set_title("P1 最终方案加速比曲线（1 核为单核参考）")
    ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(OUT / "fig8_speedup_curve_1_to_5.png"); plt.close(fig)

    # Source and algorithm fingerprints; no experiment artifacts are moved or deleted.
    manifest = json.loads(DEPENDENCY_MANIFEST.read_text(encoding="utf-8"))
    cp_manifest = json.loads(CRITICAL_PATH_MANIFEST.read_text(encoding="utf-8"))
    pipe_manifest = json.loads(PIPE_MANIFEST.read_text(encoding="utf-8"))
    plan_hashes = Counter(r["pipe_priority_plan_sha256"] for r in joined)
    provenance = {
        "scope": "P1; 100 official cases × 2/3/4/5 cores; 400 rows for each full-run candidate",
        "latest_candidate_version": pipe_manifest["algorithm_version"],
        "latest_candidate_parameters": pipe_manifest["candidate"],
        "sources": {str(p.relative_to(ROOT)): sha256(p) for p in
                    (BASELINE, DEPENDENCY, DEPENDENCY_SUMMARY, DEPENDENCY_MANIFEST,
                     CRITICAL_PATH, CRITICAL_PATH_MANIFEST, PIPE_PRIORITY, PIPE_SUMMARY, PIPE_MANIFEST,
                     ROOT / "experiments/phase2_problem1/round8_cube_vector_pipe_full/plan_manifest.csv",
                     FINAL_REPORT, FINAL_CASES, FINAL_ABLATIONS, FINAL_AUDIT, FINAL_ROUND8_VS_ROUND6,
                     FINAL_DIR / "ALGORITHM.md", FINAL_DIR / "REPRODUCE.md", FINAL_DIR / "plan_index.csv",
                     ROOT / "official/data/config.txt")},
        "plan_sha256_unique_count": len(plan_hashes),
        "plan_sha256_row_count": sum(plan_hashes.values()),
        "final_closeout_audit": audit,
        "round8_mean_added_copy_bytes": pipe_totals,
        "round8_vs_round6_case_core_counts": dict(comparison_counts),
        "ablation_equal_weight_speedups": {r["variant"]: r["equal_weight_mean_speedup_2_to_5"] for r in ablation_summary},
        "source_manifests": {"dependency_list": manifest, "critical_path": cp_manifest, "pipe_priority": pipe_manifest},
        "notes": [
            "All plotted performance values are official evaluator records; profile estimates are not substituted.",
            "The baseline and candidate use the same 100 cases and each core count.",
            "No source experiment data was deleted, moved, or compressed.",
            "Critical-path and Cube/Vector full benchmarks are included only after all 400 rows are successful."
        ]
    }
    (OUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lineage = [
        {"artifact": "Phase 1 v001", "path": "experiments/phase1_baseline/v001/", "role": "P1 baseline and single-core reference", "paper_use": "main comparison; per-case baseline makespan, single-core makespan and baseline copy bytes", "disposition": "preserve; unique source"},
        {"artifact": "Phase 2 communication full", "path": "experiments/phase2_problem1/round2_communication_full/", "role": "communication-cut + greedy full benchmark", "paper_use": "intermediate ablation/comparison; v016 also carries its makespan column, but not its complete per-case plan provenance", "disposition": "preserve; full plan/record lineage is unique"},
        {"artifact": "Phase 2 dependency diagnosis", "path": "experiments/phase2_problem1/round4_dependency_schedule/", "role": "candidate development diagnosis", "paper_use": "diagnosis evidence only; not mixed with 100-case full statistics", "disposition": "preserve; distinct sample and scheduler comparison"},
        {"artifact": "Phase 2 dependency validation", "path": "experiments/phase2_problem1/round4_dependency_validation/", "role": "frozen candidate validation", "paper_use": "validation evidence and 40 fingerprint-matched records reused in full run", "disposition": "preserve; cited by full-run reuse manifest"},
        {"artifact": "Phase 2 dependency full v016", "path": "experiments/phase2_problem1/round4_dependency_full/", "role": "primary P1 paper candidate", "paper_use": "400 case×core rows, per-case plan SHA-256, evaluator metrics, summary and records", "disposition": "preserve; authoritative candidate source"},
        {"artifact": "Phase 2 critical-path full v019", "path": "experiments/phase2_problem1/round6_critical_path_full/", "role": "critical-path priority full benchmark", "paper_use": "full comparison and direct control for Cube/Vector priority", "disposition": "preserve; authoritative full result"},
        {"artifact": "Phase 2 Cube/Vector full v023", "path": "experiments/phase2_problem1/round8_cube_vector_pipe_full/", "role": "latest P1 candidate full benchmark", "paper_use": "400 successful rows; latest candidate metrics and parameters", "disposition": "preserve; authoritative full result"},
        {"artifact": "Phase 2 final closeout", "path": "experiments/phase2_problem1/final/", "role": "frozen P1 best, full ablations and integrity audit", "paper_use": "canonical final report, 7×400 results, ablation matrix, fingerprints and reproduction commands", "disposition": "preserve; phase-complete evidence archive"},
        {"artifact": "Paper material build", "path": "experiments/paper_materials/problem1_v001/", "role": "derived tables, plots, prose and source hashes", "paper_use": "paper-writing handoff; regenerated by scripts/build_p1_paper_materials.py", "disposition": "derived output; no source experiment files moved/deleted"},
    ]
    write_csv(OUT / "artifact_lineage.csv", lineage, list(lineage[0]))
    inventory = ["# P1 artifact lineage and retention notes", "",
                 "This is a reference map, not a cleanup operation. No experiment files were deleted, moved, or compressed.", "",
                 "| Artifact | Path | Role in the evidence chain | Handling |", "|---|---|---|---|"]
    inventory.extend(f"| {r['artifact']} | `{r['path']}` | {r['paper_use']} | {r['disposition']} |" for r in lineage)
    inventory += ["", "## Trace and duplicate-record policy", "",
                  "Evaluator traces are derived from the exact case, plan, configuration and evaluator execution. They may be reproducible, but they are not treated as disposable while Phase 2 is still active. Keep the currently cited traces and all records with fingerprint-reuse relationships; do not remove the Phase 1 baseline or intermediate full runs because those preserve unique algorithm versions and plan hashes.",
                  "", "The paper build joins baseline, dependency-list, critical-path and Cube/Vector full results on `(case, cores)`, and includes the final ablation matrix plus closeout audit. Source SHA-256 values are recorded in `provenance.json`. Reused diagnosis/validation rows retain provenance through experiment manifests. No raw experiment file was altered.",
                  ""]
    (OUT / "artifact_lineage.md").write_text("\n".join(inventory), encoding="utf-8")

    # Compact method/results handoff for the paper-writing collaborator.
    s = {r["cores"]: r for r in summaries}
    pooled = mean([r["pipe_priority_speedup"] for r in joined])
    critical_pooled = mean([r["critical_path_speedup"] for r in joined])
    best = improvement[0]; bad = worst[0]
    paper = f'''# P1 论文材料初稿与数据说明

## 研究范围和可引用状态

本材料基于 Problem 1（场景 A）官方评估器、`official/data/config.txt` 固定配置，以及 100 个正式 case 在 2、3、4、5 核上的全量结果。对照链包括 Phase 1 v001、通信切图+贪心分核、依赖感知调度、关键路径优先级和最新 Cube/Vector 管线关键路径优先级。每轮按相同 case×核数比较。最新候选结果来自 `{PIPE_PRIORITY.relative_to(ROOT).as_posix()}`，逐 case 表保留各版本 Makespan、speedup 和运行记录路径。

Cube/Vector 候选 400/400 成功，但相对关键路径版本的总体提升约 0.016%，应视为边际差异，不宜表述为显著加速。所有原始实验文件均保留，本次没有删除、移动或压缩。

P1 收尾已完成，Phase 2 标记 complete；本轮没有启动 P2/P3。最终方案平均额外搬运为 {pipe_totals['added_copy_bytes']:,.2f} B，其中 partition-added {pipe_totals['partition_added_copy_bytes']:,.2f} B、spill-added {pipe_totals['spill_added_copy_bytes']:,.2f} B。最终审计覆盖 7 组、每组 400/400 成功，且 21 项单元测试通过。缓存压力方向仍是“暂缓、未验证”。

## 方法说明（论文草稿）

Problem 1 将每个子图作为独立 Task，并由官方模拟器依据数据依赖、跨核等待、核内多 Pipe 执行和数据搬运计算 Makespan。首先按原图确定性拓扑序进行通信感知连续切图，目标块规模 256 个计算操作、范围 128–384、理想切点窗口 ±32。随后以子图 cycles 估计释放时间，依赖感知 list scheduling 分配 Task；critical-path 版本再用剩余路径尾长调整 ready Task 优先级。最新版本进一步以每 Task 的 `max(PIPE_M cycles, PIPE_V cycles)` 和后继路径尾长构成 Pipe-aware 优先级信号。Cycles 仅用于启发式，不是性能指标；Makespan、speedup 和含 spill 搬运量均来自官方 evaluator。

## 结果概述

最新候选 400/400 条记录成功。400 个 case×核数的 speedup 算术平均为 **{pooled:.6f} 倍**；关键路径版本为 **{critical_pooled:.6f} 倍**，相对提升约 **{(pooled/critical_pooled-1)*100:.3f}%**。按 2/3/4/5 核分别，平均逐 case speedup 为 **{s[2]['pipe_priority_mean_case_speedup']:.4f} / {s[3]['pipe_priority_mean_case_speedup']:.4f} / {s[4]['pipe_priority_mean_case_speedup']:.4f} / {s[5]['pipe_priority_mean_case_speedup']:.4f} 倍**；对应平均 Makespan 为 **{s[2]['pipe_priority_mean_makespan_cycles']:,.0f} / {s[3]['pipe_priority_mean_makespan_cycles']:,.0f} / {s[4]['pipe_priority_mean_makespan_cycles']:,.0f} / {s[5]['pipe_priority_mean_makespan_cycles']:,.0f} 周期**。相对关键路径版本的平均 Makespan 变化为 **{s[2]['pipe_priority_mean_makespan_change_vs_critical_path_percent']:+.3f}% / {s[3]['pipe_priority_mean_makespan_change_vs_critical_path_percent']:+.3f}% / {s[4]['pipe_priority_mean_makespan_change_vs_critical_path_percent']:+.3f}% / {s[5]['pipe_priority_mean_makespan_change_vs_critical_path_percent']:+.3f}%**，负值代表改善。

相对 Phase 1 baseline 的逐 case Makespan 改善数分别为 2 核 {sum(r['pipe_priority_makespan'] < r['baseline_makespan'] for r in joined if r['cores']==2)}/100、3 核 {sum(r['pipe_priority_makespan'] < r['baseline_makespan'] for r in joined if r['cores']==3)}/100、4 核 {sum(r['pipe_priority_makespan'] < r['baseline_makespan'] for r in joined if r['cores']==4)}/100、5 核 {sum(r['pipe_priority_makespan'] < r['baseline_makespan'] for r in joined if r['cores']==5)}/100。全量中最大改善为 {best['case']} / {best['cores']} 核（降幅 {-best['pipe_priority_makespan_change_vs_baseline_percent']:.2f}%），最大退化为 {bad['case']} / {bad['cores']} 核（增加 {bad['pipe_priority_makespan_change_vs_baseline_percent']:.2f}%）；均为事后选出的解释案例，不是独立验证集。

## 指标定义和统计口径

- `Makespan`：官方 evaluator 完成事件模拟后的最晚完成周期数，越小越好。
- `speedup(case, cores) = singlecore_makespan(case) / multicore_makespan(case, cores)`。
- “平均 speedup”是每个 case 的 speedup 做算术平均；全体均值把四个核数组合后的 400 项等权平均。
- Makespan 相对 baseline 变化率为 `(candidate - baseline) / baseline × 100%`；图中“降幅”取其相反数，正值代表改善。
- `added_copy_bytes` 使用官方结果的 partition copy + spill copy 总量；通信账本估算不代替该实测值。
- 改善/退化按 Makespan 严格比较，精确相等计为持平。

## 图表清单

1. `fig1_speedup_by_core.png`：按核数对比五种阶段方案的平均逐 case speedup。
2. `fig2_makespan_ratio.png`：各方案平均 Makespan 相对 baseline 平均值的比率。
3. `fig3_case_change_distribution.png`：最新候选逐 case Makespan 降幅分布；箱线图为显示隐藏离群点，原始 400 项均在 CSV 中。
4. `fig4_copy_vs_makespan.png`：最新候选含 spill 的额外搬运量与相对 baseline Makespan 降幅散点图，每点对应 case×核数。
5. `fig5_method_pipeline.png`：更新后的 Cube/Vector 关键路径流程图。
6. `fig6_ablation_speedup.png`：最终组合与 final-composition removal ablation 的 speedup 对照。
7. `fig7_round8_vs_round6_counts.png`：Pipe 修正相对 round6 的改善/持平/退化数量。
8. `fig8_speedup_curve_1_to_5.png`：最终方案 1–5 核加速比曲线，1 核采用单核参考。

每张结果图范围均为 100 个正式 case、P1、2–5 核；数据来源为官方 evaluator 的保存结果。汇总和逐 case 表提供作图数值，可用于在论文软件中重绘。

## 数据来源与复现

- baseline 逐项结果：`experiments/phase1_baseline/v001/reports/per_case.csv`。
- 候选逐项结果及方案指纹：`experiments/phase2_problem1/round4_dependency_full/full_per_case.csv`。
- 候选按核数汇总：`experiments/phase2_problem1/round4_dependency_full/full_summary.csv`。
- 关键路径和 Cube/Vector 优先级的全量逐 case 表：`experiments/phase2_problem1/round6_critical_path_full/all_per_case.csv`、`experiments/phase2_problem1/round8_cube_vector_pipe_full/all_per_case.csv`。
- P1 最终报告和消融/审计来源：`experiments/phase2_problem1/final/FINAL_REPORT.md`、`ablation_summary.csv`、`validation_audit.json`；本论文包生成对应的 closeout 逐 case 表与消融汇总。
- 方案、命令和运行记录：候选 CSV 的 `record_path` 指向相应 `record.json`，`plan_sha256` 指向方案内容指纹。
- 源文件 SHA-256 与算法参数：`provenance.json`。
- 实验产物引用关系和保留说明：`artifact_lineage.md` / `artifact_lineage.csv`。
- 从项目根目录复现本文表格和 PNG：`python scripts/build_p1_paper_materials.py`（依赖 matplotlib、numpy）。本脚本仅读取实验结果并写入本目录，不调用 evaluator，也不修改原始实验数据。

## 可直接用于论文的结论措辞（需作者核对）

“在固定配置下，对 100 个正式计算图、2–5 核共 400 个 P1 case×核数组合进行官方模拟评估。最终通信感知切图与依赖/关键路径/Cube-Vector 优先级方案全部通过评估，等权平均 speedup 为 {pooled:.6f}。相对 round6，Cube/Vector 修正仅带来约 +0.016% 的边际变化；400 项中 23 项改善、348 项持平、29 项退化。消融显示，移除通信切点后等权 speedup 降至 1.354964，移除关键路径尾长后为 1.899225。缓存压力方向尚未验证。”

该表述是对本地实验数据的描述，不表示赛题官方计分规则或外部硬件上的真实加速承诺。
'''
    (OUT / "P1_paper_draft.md").write_text(paper, encoding="utf-8")

    print(f"Wrote paper materials to {OUT}")
    print(f"candidate pooled equal-weight mean speedup={pooled:.6f}; records={len(joined)}")


if __name__ == "__main__":
    main()

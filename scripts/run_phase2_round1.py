"""Run the fixed P1 diagnosis-sample granularity comparison for Phase 2 round 1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from experiment_runner import (CONFIG, OFFICIAL, evaluator_fingerprint,
                               sha256_file, source_fingerprint)
from src.graph_io import load_graph
from src.scheduler import ALGORITHM_VERSION, build_plan
from src.topology import topological_ops

OUT = ROOT / "experiments" / "phase2_problem1" / "round1"
PHASE1 = ROOT / "experiments" / "phase1_baseline" / "v001"
PROFILE = ROOT / "experiments" / "phase0" / "graph-profile-v1" / "profile.csv"
CORE_COUNTS = (2, 3, 4, 5)
FIXED_SIZES = (32, 64, 128, 256)
RELATIVE_C = (2, 4, 8)
PROBLEM = "1"
VERSION = "p1_contiguous_granularity_round1"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False).encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def official_cases() -> dict[str, Path]:
    cases = {p.stem: p for p in sorted((ROOT / "official" / "data").glob("case_*.json"))}
    if len(cases) != 100:
        raise RuntimeError(f"expected 100 official cases, found {len(cases)}")
    return cases


def phase1_lookup() -> tuple[dict, dict]:
    rows = read_csv(PHASE1 / "reports" / "per_case.csv")
    profile_rows = read_csv(PROFILE)
    by_case: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_case[row["case"]][f"{row['problem']}:{row['cores']}"] = row
    profile = {row["case"]: row for row in profile_rows}
    if len(by_case) != 100 or len(profile) != 100:
        raise RuntimeError("Phase 1 results and graph profile must each contain 100 cases")
    return by_case, profile


def choose_samples() -> dict:
    phase1, profile = phase1_lookup()
    case_paths = official_cases()
    if len(case_paths) != 100:
        raise RuntimeError("official case set is incomplete")
    reasons: dict[str, list[str]] = defaultdict(list)

    def choose(case: str, reason: str) -> None:
        if case not in case_paths:
            raise RuntimeError(f"sample rule refers to missing case {case}")
        if reason not in reasons[case]:
            reasons[case].append(reason)

    cases = sorted(case_paths)
    # Phase 1 P1 measurements drive diagnosis rules; graph-profile fields are
    # selection proxies only and are not treated as evaluator outcomes.
    speedups = {
        case: min(float(phase1[case][f"problem_1:{core}"]["speedup"]) for core in CORE_COUNTS)
        for case in cases
    }
    choose(min(cases, key=lambda c: (speedups[c], c)), "worst_min_speedup_across_2_to_5_cores")
    choose(min(cases, key=lambda c: (float(phase1[c]["problem_1:5"]["speedup"]), c)),
           "worst_5_core_speedup")
    choose(max(cases, key=lambda c: (
        float(phase1[c]["problem_1:5"]["makespan"]) / float(phase1[c]["problem_1:2"]["makespan"]), c)),
        "largest_5_vs_2_core_makespan_ratio")
    choose(max(cases, key=lambda c: (float(phase1[c]["problem_1:2"]["added_copy_bytes"]), c)),
           "largest_P1_2_core_added_copy_bytes")
    choose(max(cases, key=lambda c: (float(phase1[c]["problem_1:5"]["speedup"]), c)),
           "best_5_core_speedup_parallelism_example")
    choose(min(cases, key=lambda c: (int(profile[c]["compute_op_count"]), c)), "smallest_compute_graph")
    choose(max(cases, key=lambda c: (int(profile[c]["compute_op_count"]), c)), "largest_compute_graph")
    choose(max(cases, key=lambda c: (int(profile[c]["original_graph_copy_bytes"]), c)),
           "largest_profile_original_DDR_copy_bytes")
    choose(max(cases, key=lambda c: (int(profile[c]["op_dependency_depth"]), c)),
           "deepest_profile_dependency_graph")
    # Add deterministic size-stratified representatives until exactly ten.
    size_order = sorted(cases, key=lambda c: (int(profile[c]["compute_op_count"]), c))
    for q in (0.15, 0.35, 0.50, 0.65, 0.85):
        if len(reasons) >= 10:
            break
        idx = min(len(size_order) - 1, round(q * (len(size_order) - 1)))
        for offset in range(len(size_order)):
            candidate = size_order[min(len(size_order) - 1, idx + offset)]
            if candidate not in reasons:
                choose(candidate, f"size_stratum_fill_q{int(q * 100):02d}")
                break
            candidate = size_order[max(0, idx - offset)]
            if candidate not in reasons:
                choose(candidate, f"size_stratum_fill_q{int(q * 100):02d}")
                break

    diagnosis = list(reasons)
    if len(diagnosis) != 10:
        for candidate in size_order:
            if candidate not in reasons:
                choose(candidate, "size_stratified_fill")
                if len(reasons) == 10:
                    break

    remaining = [c for c in size_order if c not in reasons]
    validation: list[str] = []
    # Ten approximately decile-spaced cases from the remaining 90, disjoint
    # from diagnosis; tie-breaking follows sorted compute-op count then case id.
    for q in (0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95):
        idx = min(len(remaining) - 1, round(q * (len(remaining) - 1)))
        candidate = remaining[idx]
        if candidate not in validation:
            validation.append(candidate)
    for candidate in remaining:
        if len(validation) == 10:
            break
        if candidate not in validation:
            validation.append(candidate)

    val_reasons = {case: [f"validation_compute_op_size_decile_q{q:02d}"]
                   for case, q in zip(validation, (5, 15, 25, 35, 45, 55, 65, 75, 85, 95))}
    return {
        "selection_version": "phase2_round1_fixed_disjoint_v001",
        "selection_created_at": datetime.now(timezone.utc).isoformat(),
        "diagnosis_basis": "Phase 1 P1 per-case evaluator metrics plus Phase 0 graph-profile selection proxies",
        "validation_basis": "remaining cases stratified by compute_op_count deciles; no candidate evaluator results used",
        "validation_evaluator_runs_this_round": 0,
        "diagnosis": [{"case": c, "reasons": reasons[c],
                       "phase1_p1_speedup_by_cores": {
                           str(k): float(phase1[c][f"problem_1:{k}"]["speedup"]) for k in CORE_COUNTS},
                       "compute_op_count": int(profile[c]["compute_op_count"]),
                       "profile_op_dependency_depth": int(profile[c]["op_dependency_depth"]),
                       "profile_original_graph_copy_bytes": int(profile[c]["original_graph_copy_bytes"])}
                      for c in diagnosis],
        "validation": [{"case": c, "reasons": val_reasons[c],
                        "compute_op_count": int(profile[c]["compute_op_count"]),
                        "profile_op_dependency_depth": int(profile[c]["op_dependency_depth"]),
                        "profile_original_graph_copy_bytes": int(profile[c]["original_graph_copy_bytes"])}
                       for c in validation],
    }


def candidate_specs() -> list[dict]:
    specs = [{"name": f"fixed_{size:03d}", "kind": "fixed", "size": size}
             for size in FIXED_SIZES]
    specs += [{"name": f"relative_c{c}", "kind": "relative", "c": c}
              for c in RELATIVE_C]
    return specs


def make_plan(graph: dict, spec: dict, cores: int) -> tuple[dict, dict]:
    ordered = topological_ops(graph)
    n_ops = len(ordered)
    if spec["kind"] == "fixed":
        size = int(spec["size"])
        target_k = None
    else:
        target_k = min(n_ops, int(spec["c"]) * cores) if n_ops else 0
        size = max(1, math.ceil(n_ops / target_k)) if target_k else 1
    plan = build_plan(graph, cores, size)
    actual = len(set(plan["node_to_subgraph"].values()))
    return plan, {"compute_op_count": n_ops, "target_subgraph_count": target_k,
                  "chunk_size": size, "actual_subgraph_count": actual,
                  "requested_relative_c": spec.get("c")}


def phase1_success(case: str, cores: int, plan_sha: str) -> tuple[dict, str] | None:
    parent = PHASE1 / "cases" / case / f"cores_{cores}" / "problem_1"
    for record_path in sorted(parent.glob("attempt_*/record.json"), reverse=True):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        integrity_ok = (record.get("integrity_status") == "verified"
                        or (record.get("integrity_status") is None
                            and "Official integrity OK (114 files)" in record.get("integrity_pre_stdout", "")
                            and "Official integrity OK (114 files)" in record.get("integrity_post_stdout", "")))
        fingerprint = record.get("fingerprint", {})
        if (record.get("status") != "success" or not integrity_ok
                or str(record.get("problem")) != "1" or record.get("cores") != cores):
            continue
        # The evaluator record is reusable only if the frozen baseline plan is
        # byte-identical to this candidate and all expected output hashes hold.
        baseline_plan = PHASE1 / "cases" / case / f"cores_{cores}" / "plan.json"
        if not baseline_plan.is_file() or sha256_file(baseline_plan) != plan_sha:
            continue
        expected = record.get("fingerprint", {}).get("input_sha256")
        if expected != sha256_file(ROOT / "official" / "data" / f"{case}.json"):
            continue
        if (fingerprint.get("config_sha256") != sha256_file(CONFIG)
                or fingerprint.get("evaluator_sha256") != evaluator_fingerprint("1")
                or fingerprint.get("parameters", {}).get("algorithm_sha256") != source_fingerprint()):
            continue
        outputs_ok = all((ROOT / rel).is_file() and sha256_file(ROOT / rel) == h
                         for rel, h in record.get("output_sha256", {}).items())
        if outputs_ok and record.get("result", {}).get("makespan") is not None:
            return record, record_path.relative_to(ROOT).as_posix()
    return None


def tensor_ledger(graph: dict, plan: dict) -> tuple[list[dict], dict]:
    op_by_id = {op["id"]: op for op in graph["ops"]}
    tensor_by_id = {tensor["id"]: tensor for tensor in graph["tensors"]}
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    for edge in graph["edges"]:
        src, dst = edge["source"], edge["target"]
        if src in op_by_id and dst in tensor_by_id:
            producers[dst].add(src)
        elif src in tensor_by_id and dst in op_by_id:
            consumers[src].add(dst)
    compute_map = {int(op): int(sg) for op, sg in plan["node_to_subgraph"].items()}
    core_by_sg = {sg: core_id for core_id, schedule in enumerate(plan["core_schedules"])
                  for sg in schedule}
    task_by_op = {op: compute_map[op] for op in compute_map}
    copy_in = defaultdict(set)
    copy_out = defaultdict(set)
    for tensor_id, op_ids in producers.items():
        for op_id in op_ids:
            if op_by_id[op_id].get("op") == "COPY_IN":
                copy_in[tensor_id].add(op_id)
    for tensor_id, op_ids in consumers.items():
        for op_id in op_ids:
            if op_by_id[op_id].get("op") == "COPY_OUT":
                copy_out[tensor_id].add(op_id)

    rows = []
    account = ledger_for_plan(graph, plan)
    summary = {"tensor_count": len(tensor_by_id)}
    for tensor_id, tensor in tensor_by_id.items():
        size = int(tensor.get("size", 0))
        prod_ops = producers.get(tensor_id, set())
        cons_ops = consumers.get(tensor_id, set())
        compute_producers = prod_ops & task_by_op.keys()
        compute_consumers = cons_ops & task_by_op.keys()
        write_tasks = account["per_tensor_writes"].get(tensor_id, set())
        read_tasks = account["per_tensor_reads"].get(tensor_id, set())
        rows.append({
            "tensor_id": tensor_id, "size_bytes": size, "position": tensor.get("pos"),
            "producer_op_ids": json.dumps(sorted(prod_ops)),
            "consumer_op_ids": json.dumps(sorted(cons_ops)),
            "copy_in_op_ids": json.dumps(sorted(copy_in.get(tensor_id, set()))),
            "copy_out_op_ids": json.dumps(sorted(copy_out.get(tensor_id, set()))),
            "compute_producer_op_ids": json.dumps(sorted(compute_producers)),
            "compute_consumer_op_ids": json.dumps(sorted(compute_consumers)),
            "boundary_write_task_ids_v001_64": json.dumps(sorted(write_tasks)),
            "boundary_read_task_ids_v001_64": json.dumps(sorted(read_tasks)),
            "boundary_write_bytes_v001_64": size * len(write_tasks),
            "boundary_read_bytes_v001_64": size * len(read_tasks),
            "shared_input_repeated_read_bytes_v001_64": size * max(0, len(read_tasks) - 1),
        })
    copy_in_bytes = copy_out_bytes = 0
    for edge in graph["edges"]:
        src, dst = edge["source"], edge["target"]
        if src in op_by_id and op_by_id[src].get("op") == "COPY_IN" and dst in tensor_by_id:
            copy_in_bytes += int(tensor_by_id[dst].get("size", 0))
        if dst in op_by_id and op_by_id[dst].get("op") == "COPY_OUT" and src in tensor_by_id:
            copy_out_bytes += int(tensor_by_id[src].get("size", 0))
    summary["original_copy_in_bytes"] = copy_in_bytes
    summary["original_copy_out_bytes"] = copy_out_bytes
    summary["boundary_write_bytes"] = account["boundary_write_bytes"]
    summary["boundary_read_bytes"] = account["boundary_read_bytes"]
    summary["shared_input_repeated_read_bytes"] = account["shared_input_repeated_read_bytes"]
    return rows, summary


def ledger_for_plan(graph: dict, plan: dict) -> dict:
    """Estimate distinct P1 Task boundary reads/writes for one partition."""
    op_by_id = {op["id"]: op for op in graph["ops"]}
    tensor_by_id = {tensor["id"]: tensor for tensor in graph["tensors"]}
    producers: dict[int, set[int]] = defaultdict(set)
    consumers: dict[int, set[int]] = defaultdict(set)
    for edge in graph["edges"]:
        src, dst = edge["source"], edge["target"]
        if src in op_by_id and dst in tensor_by_id:
            producers[dst].add(src)
        elif src in tensor_by_id and dst in op_by_id:
            consumers[src].add(dst)
    mapping = {int(op): int(sg) for op, sg in plan["node_to_subgraph"].items()}
    reads: dict[int, set[int]] = defaultdict(set)
    writes: dict[int, set[int]] = defaultdict(set)
    for tensor_id, _tensor in tensor_by_id.items():
        prod = producers.get(tensor_id, set())
        cons = consumers.get(tensor_id, set())
        eligible_prod = {op for op in prod if op in mapping}
        eligible_cons = {op for op in cons if op in mapping}
        has_copy_out = any(op_by_id[op].get("op") == "COPY_OUT" for op in cons if op in op_by_id)
        producer_tasks = {mapping[op] for op in eligible_prod}
        consumer_tasks = {mapping[op] for op in eligible_cons}
        reads[tensor_id].update(consumer_tasks - producer_tasks)
        if has_copy_out or not consumer_tasks:
            writes[tensor_id].update(producer_tasks)
        else:
            writes[tensor_id].update(task for task in producer_tasks if consumer_tasks - {task})
    read_bytes = sum(int(tensor_by_id[tid]["size"]) * len(task_ids)
                     for tid, task_ids in reads.items())
    write_bytes = sum(int(tensor_by_id[tid]["size"]) * len(task_ids)
                      for tid, task_ids in writes.items())
    duplicate_bytes = sum(int(tensor_by_id[tid]["size"]) * max(0, len(task_ids) - 1)
                          for tid, task_ids in reads.items())
    return {"boundary_write_bytes": write_bytes, "boundary_read_bytes": read_bytes,
            "shared_input_repeated_read_bytes": duplicate_bytes,
            "boundary_write_task_count": sum(map(len, writes.values())),
            "boundary_read_task_count": sum(map(len, reads.values())),
            "shared_input_tensor_count": sum(1 for tasks in reads.values() if len(tasks) > 1),
            "per_tensor_reads": reads, "per_tensor_writes": writes}


def baseline_evaluator_metrics(case: str, cores: int) -> dict:
    parent = PHASE1 / "cases" / case / f"cores_{cores}" / "problem_1"
    for path in sorted(parent.glob("attempt_*/result.json"), reverse=True):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if result.get("makespan") is not None:
            movement = result.get("data_movement_bytes", {})
            return {"v001_makespan": result["makespan"],
                    "v001_added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
                    "v001_partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
                    "v001_spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
                    "v001_original_graph_copy_bytes": movement.get("original_graph_copy_bytes")}
    return {}


def build_ledgers(samples: dict, specs: list[dict]) -> None:
    diagnosis_names = [item["case"] for item in samples["diagnosis"]]
    validation_names = [item["case"] for item in samples["validation"]]
    facts_rows: list[dict] = []
    summaries: list[dict] = []
    audit_rows: list[dict] = []
    for case in diagnosis_names + validation_names:
        graph = load_graph(official_cases()[case])
        facts_plan = build_plan(graph, 2, 64)
        fact_rows, copy_summary = tensor_ledger(graph, facts_plan)
        for row in fact_rows:
            facts_rows.append({"case": case, **row})
        for cores in CORE_COUNTS:
            plan = build_plan(graph, cores, 64)
            account = ledger_for_plan(graph, plan)
            summaries.append({"case": case, "sample_group": "diagnosis" if case in diagnosis_names else "validation",
                              "plan": "v001_fixed_064", "cores": cores,
                              "computed_subgraphs": len(set(plan["node_to_subgraph"].values())),
                              **{key: value for key, value in account.items() if not key.startswith("per_tensor_")},
                              **{f"original_{k}": v for k, v in copy_summary.items() if k.startswith("original_")},
                              **baseline_evaluator_metrics(case, cores)})
        base_account = ledger_for_plan(graph, facts_plan)
        measured = baseline_evaluator_metrics(case, 2)
        ledger_original = (copy_summary["original_copy_in_bytes"]
                           + copy_summary["original_copy_out_bytes"])
        estimated_added = (base_account["boundary_read_bytes"]
                           + base_account["boundary_write_bytes"] - ledger_original)
        matched = (ledger_original == measured.get("v001_original_graph_copy_bytes")
                   and estimated_added == measured.get("v001_partition_added_copy_bytes"))
        audit_rows.append({"case": case,
                           "sample_group": "diagnosis" if case in diagnosis_names else "validation",
                           "estimated_original_copy_in_bytes": copy_summary["original_copy_in_bytes"],
                           "estimated_original_copy_out_bytes": copy_summary["original_copy_out_bytes"],
                           "evaluator_original_graph_copy_bytes": measured.get("v001_original_graph_copy_bytes"),
                           "distinct_task_boundary_read_bytes": base_account["boundary_read_bytes"],
                           "distinct_task_boundary_write_bytes": base_account["boundary_write_bytes"],
                           "estimated_partition_added_copy_bytes": estimated_added,
                           "evaluator_partition_added_copy_bytes": measured.get("v001_partition_added_copy_bytes"),
                           "exact_match": matched})
        if not matched:
            raise RuntimeError(f"v001 communication ledger does not reconcile with evaluator: {case}")
        if case in diagnosis_names:
            for spec in specs:
                if spec["name"] == "fixed_064":
                    continue
                for cores in CORE_COUNTS:
                    generation_started = time.perf_counter()
                    plan, params = make_plan(graph, spec, cores)
                    generation_seconds = time.perf_counter() - generation_started
                    account = ledger_for_plan(graph, plan)
                    summaries.append({"case": case, "sample_group": "diagnosis",
                                      "plan": spec["name"], "cores": cores,
                                      **params,
                                      **{key: value for key, value in account.items() if not key.startswith("per_tensor_")},
                                      **{f"original_{k}": v for k, v in copy_summary.items() if k.startswith("original_")},
                                      **baseline_evaluator_metrics(case, cores)})
    write_csv(OUT / "communication_tensor_facts.csv", facts_rows)
    write_csv(OUT / "communication_summary.csv", summaries)
    write_csv(OUT / "communication_ledger_validation.csv", audit_rows)
    atomic_json(OUT / "communication_ledger_validation.json", {
        "cases_checked": len(audit_rows),
        "exact_partition_added_copy_matches": sum(row["exact_match"] for row in audit_rows),
        "rule": "distinct Task boundary reads + writes - original COPY_IN/COPY_OUT bytes = evaluator partition_added_copy_bytes; spill_added_copy_bytes is excluded and reported separately",
        "all_cases_match": all(row["exact_match"] for row in audit_rows),
    })


def valid_existing_record(path: Path, fingerprint: dict) -> dict | None:
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if record.get("fingerprint") == fingerprint and record.get("status") == "success" \
            and record.get("integrity_status") in ("verified", "not_scanned_readonly_git_hook"):
        if all((ROOT / rel).is_file() and sha256_file(ROOT / rel) == h
               for rel, h in record.get("output_sha256", {}).items()):
            return record
    return None


def make_fingerprint(case: str, cores: int, plan_sha: str, spec: dict, graph_sha: str) -> dict:
    evaluator = OFFICIAL / "code" / "multicore_cut_evaluate_problem_1.py"
    return {"case": case, "problem": "1", "cores": cores,
            "input_sha256": graph_sha, "plan_sha256": plan_sha,
            "config_sha256": sha256_file(CONFIG),
            "evaluator_sha256": sha256_file(evaluator),
            "algorithm_sha256": source_fingerprint(), "baseline_algorithm": ALGORITHM_VERSION,
            "candidate": spec, "command_template": [sys.executable, str(evaluator),
                "<graph>", "<plan>", "--config", str(CONFIG), "-o", "result.json",
                "--trace-output", "trace.json", "--log-output", "official.log"]}


def run_eval(task: dict, timeout: float) -> dict:
    candidate_dir: Path = task["candidate_dir"]
    candidate_dir.mkdir(parents=True, exist_ok=True)
    record_path = candidate_dir / "record.json"
    cached = valid_existing_record(record_path, task["fingerprint"])
    if cached:
        return {**cached, "record_path": str(record_path), "reused": True}
    evaluator = OFFICIAL / "code" / "multicore_cut_evaluate_problem_1.py"
    graph_path: Path = task["graph_path"]
    plan_path: Path = task["plan_path"]
    outputs = {"result": candidate_dir / "result.json", "trace": candidate_dir / "trace.json",
               "log": candidate_dir / "official.log", "stdout": candidate_dir / "stdout.txt",
               "stderr": candidate_dir / "stderr.txt"}
    command = [sys.executable, str(evaluator), str(graph_path), str(plan_path), "--config", str(CONFIG),
               "-o", str(outputs["result"]), "--trace-output", str(outputs["trace"]),
               "--log-output", str(outputs["log"])]
    started = time.perf_counter()
    timed_out = False
    code = None
    stdout = stderr = ""
    try:
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=timeout,
                                 env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False)
        code, stdout, stderr = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    elapsed = time.perf_counter() - started
    outputs["stdout"].write_text(stdout, encoding="utf-8", errors="replace")
    outputs["stderr"].write_text(stderr, encoding="utf-8", errors="replace")
    result = {}
    parse_error = None
    if not timed_out and code == 0:
        try:
            result = json.loads(outputs["result"].read_text(encoding="utf-8"))
            if not isinstance(result.get("makespan"), (int, float)):
                raise ValueError("result missing numeric makespan")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            parse_error = str(exc)
    if timed_out:
        evaluator_status = "timeout"
    elif code != 0 and ("EVALUATION ERROR" in stderr or "EVALUATION ERROR" in stdout):
        evaluator_status = "illegal"
    elif code != 0 or parse_error:
        evaluator_status = "failed"
    else:
        evaluator_status = "success"
    present = {key: path for key, path in outputs.items() if path.is_file()}
    record = {"case": task["case"], "problem": "1", "cores": task["cores"],
              "candidate": task["spec"], "parameters": task["parameters"],
              "plan_sha256": task["plan_sha"], "fingerprint": task["fingerprint"],
              "algorithm_version": VERSION, "evaluator_status": evaluator_status,
              "status": evaluator_status, "integrity_status": "not_scanned_readonly_git_hook",
              "integrity_batch_id": None, "timeout_seconds": timeout,
              "timeout": timed_out, "exit_code": code, "evaluator_seconds": round(elapsed, 6),
              "generation_seconds": task["generation_seconds"], "command": command,
              "result": result, "error": parse_error or (stderr.strip() if evaluator_status != "success" else None),
              "output_paths": {key: path.relative_to(ROOT).as_posix() for key, path in present.items()},
              "output_sha256": {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in present.values()}}
    atomic_json(record_path, record)
    print(f"P1 {task['case']} {task['spec']['name']} cores={task['cores']} "
          f"{evaluator_status} {elapsed:.2f}s", flush=True)
    return {**record, "record_path": str(record_path)}


def prepare_candidates(samples: dict, specs: list[dict]) -> tuple[list[dict], list[dict]]:
    case_paths = official_cases()
    plans: list[dict] = []
    rows: list[dict] = []
    for sample in samples["diagnosis"]:
        case = sample["case"]
        graph_path = case_paths[case]
        graph = load_graph(graph_path)
        graph_sha = sha256_file(graph_path)
        for cores in CORE_COUNTS:
            for spec in specs:
                generation_started = time.perf_counter()
                plan, params = make_plan(graph, spec, cores)
                generation_seconds = time.perf_counter() - generation_started
                candidate_dir = OUT / "cases" / case / f"cores_{cores}" / spec["name"]
                candidate_dir.mkdir(parents=True, exist_ok=True)
                plan_path = candidate_dir / "plan.json"
                serialized = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
                if not plan_path.exists() or plan_path.read_text(encoding="utf-8") != serialized:
                    plan_path.write_text(serialized, encoding="utf-8")
                plan_sha = sha256_file(plan_path)
                official_code = str(OFFICIAL / "code")
                if official_code not in sys.path:
                    sys.path.insert(0, official_code)
                from stub_multicore_cut_and_schedule import validate_multicore_plan
                validate_multicore_plan(graph, plan)
                generation = {"case": case, "cores": cores, "candidate": spec["name"],
                              "parameters": params, "plan_path": plan_path.relative_to(ROOT).as_posix(),
                              "plan_sha256": plan_sha}
                atomic_json(candidate_dir / "plan_manifest.json", generation)
                rows.append(generation)
                plans.append({"case": case, "cores": cores, "spec": spec, "parameters": params,
                              "graph_path": graph_path, "graph_sha": graph_sha,
                              "plan_path": plan_path, "plan_sha": plan_sha,
                              "generation_seconds": generation_seconds, "candidate_dir": candidate_dir,
                              "fingerprint": make_fingerprint(case, cores, plan_sha, spec, graph_sha)})
    write_csv(OUT / "plan_manifest.csv", rows)
    return plans, rows


def evaluate_candidates(tasks: list[dict], workers: int, timeout: float) -> list[dict]:
    # Reuse the byte-identical P1 v001 control after verifying its protected
    # result record, graph/config/evaluator fingerprints and plan digest.
    eval_tasks, completed = [], []
    for task in tasks:
        if task["spec"]["name"] == "fixed_064":
            cached = phase1_success(task["case"], task["cores"], task["plan_sha"])
            if cached is None:
                raise RuntimeError(f"cannot safely reuse Phase 1 P1 baseline: {task['case']} cores={task['cores']}")
            source, source_path = cached
            raw_result_path = ROOT / Path(source_path).parent / "result.json"
            raw_result = json.loads(raw_result_path.read_text(encoding="utf-8"))
            copied = {"case": task["case"], "problem": "1", "cores": task["cores"],
                      "candidate": task["spec"], "parameters": task["parameters"],
                      "plan_sha256": task["plan_sha"], "algorithm_version": VERSION,
                      "status": "success", "integrity_status": "verified", "reused": True,
                      "source_record": source_path, "result": raw_result,
                      "evaluator_seconds": source.get("evaluator_seconds"),
                      "generation_seconds": task.get("generation_seconds"),
                      "fingerprint": task["fingerprint"]}
            atomic_json(task["candidate_dir"] / "record.json", copied)
            completed.append({**copied, "record_path": str(task["candidate_dir"] / "record.json")})
            continue
        task["fingerprint"] = make_fingerprint(task["case"], task["cores"], task["plan_sha"],
                                               task["spec"], task["graph_sha"])
        cached = valid_existing_record(task["candidate_dir"] / "record.json", task["fingerprint"])
        if cached:
            completed.append({**cached, "record_path": str(task["candidate_dir"] / "record.json"), "reused": True})
        else:
            eval_tasks.append(task)

    if not eval_tasks:
        return completed
    fresh: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_eval, task, timeout): task for task in eval_tasks}
        for future in as_completed(futures):
            result = future.result()
            fresh.append(result)
            completed.append(result)
    return completed


def compile_results(samples: dict, tasks: list[dict]) -> None:
    phase1, _profile = phase1_lookup()
    rows, groups = [], []
    for task in tasks:
        path = task["candidate_dir"] / "record.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        result = record.get("result", {})
        base = phase1[task["case"]][f"problem_1:{task['cores']}"]
        makespan = result.get("makespan")
        speedup = (float(base["singlecore_makespan"]) / makespan) if makespan else None
        baseline_ms = float(base["makespan"])
        delta = (makespan / baseline_ms - 1.0) if makespan else None
        movement = result.get("data_movement_bytes", {}) if isinstance(result, dict) else {}
        row = {"case": task["case"], "problem": "1", "cores": task["cores"],
               "candidate": task["spec"]["name"], "status": record.get("status"),
               "makespan": makespan, "v001_makespan": baseline_ms,
               "speedup_vs_singlecore": speedup, "makespan_change_vs_v001_fraction": delta,
               "improved_vs_v001": bool(makespan is not None and makespan < baseline_ms),
               "added_copy_bytes_including_spill": movement.get("added_copy_bytes"),
               "partition_added_copy_bytes": movement.get("partition_added_copy_bytes"),
               "spill_added_copy_bytes": movement.get("spill_added_copy_bytes"),
               "generation_seconds": record.get("generation_seconds"),
               "evaluator_seconds": record.get("evaluator_seconds"),
               "plan_sha256": task["plan_sha"], "record_path": path.relative_to(ROOT).as_posix()}
        rows.append(row)
    spec_names = [spec["name"] for spec in candidate_specs()]
    for name in spec_names:
        for cores in CORE_COUNTS:
            selected = [r for r in rows if r["candidate"] == name and r["cores"] == cores]
            valid = [r for r in selected if r["status"] == "success" and r["speedup_vs_singlecore"] is not None]
            regressions = [r for r in valid if not r["improved_vs_v001"]]
            groups.append({"candidate": name, "cores": cores, "success": len(valid),
                           "illegal": sum(r["status"] == "illegal" for r in selected),
                           "failed": sum(r["status"] == "failed" for r in selected),
                           "timeout": sum(r["status"] == "timeout" for r in selected),
                           "average_makespan": (sum(r["makespan"] for r in valid) / len(valid)) if valid else None,
                           "average_speedup": (sum(r["speedup_vs_singlecore"] for r in valid) / len(valid)) if valid else None,
                           "mean_makespan_change_vs_v001_percent": (100 * sum(r["makespan_change_vs_v001_fraction"] for r in valid) / len(valid)) if valid else None,
                           "improved_case_count": sum(r["improved_vs_v001"] for r in valid),
                           "regressed_or_tied_case_count": len(regressions),
                           "worst_change_vs_v001_percent": max((100 * r["makespan_change_vs_v001_fraction"] for r in valid), default=None),
                           "average_added_copy_bytes_including_spill": (sum(r["added_copy_bytes_including_spill"] or 0 for r in valid) / len(valid)) if valid else None,
                           "average_generation_seconds": (sum(r["generation_seconds"] or 0 for r in valid) / len(valid)) if valid else None,
                           "average_evaluator_seconds": (sum(r["evaluator_seconds"] or 0 for r in valid) / len(valid)) if valid else None})
    for group in groups:
        core_rows = [g for g in groups if g["candidate"] == group["candidate"]]
        means = [g["average_speedup"] for g in core_rows if g["average_speedup"] is not None]
        group["equal_weight_mean_speedup_2_to_5"] = sum(means) / len(means) if len(means) == 4 else None
    write_csv(OUT / "diagnosis_per_case.csv", rows)
    write_csv(OUT / "diagnosis_summary.csv", groups)
    for candidate in candidate_specs():
        if candidate["name"] == "fixed_064":
            continue
    candidates = []
    for name in spec_names:
        if name == "fixed_064":
            continue
        gs = [g for g in groups if g["candidate"] == name]
        score = gs[0]["equal_weight_mean_speedup_2_to_5"] if gs else None
        candidates.append({"candidate": name, "parameters": next(s for s in candidate_specs() if s["name"] == name),
                           "diagnosis_equal_weight_mean_speedup": score,
                           "all_40_success": sum(g["success"] for g in gs) == 40})
    candidates = [c for c in candidates if c["all_40_success"] and c["diagnosis_equal_weight_mean_speedup"] is not None]
    candidates.sort(key=lambda c: (-c["diagnosis_equal_weight_mean_speedup"], c["candidate"]))
    frozen = candidates[:2]
    atomic_json(OUT / "frozen_validation_candidates.json", {
        "status": "frozen_after_diagnosis_not_yet_evaluated_on_validation",
        "selection_rule": "highest diagnosis 10-case equal-weight mean of per-core arithmetic mean speedup; all 40 P1 diagnosis case-core runs must succeed; ties by candidate name",
        "validation_case_ids": [item["case"] for item in samples["validation"]],
        "validation_runs_completed": 0,
        "candidates": frozen,
    })
    write_round_report(samples, groups, rows, frozen)


def write_round_report(samples: dict, groups: list[dict], rows: list[dict], frozen: list[dict]) -> None:
    diag = [item["case"] for item in samples["diagnosis"]]
    val = [item["case"] for item in samples["validation"]]
    phase1, _profile = phase1_lookup()
    lines = ["# Phase 2 Problem 1 — Round 1 report", "",
             "Scope: P1 only; Phase 1 artifacts remain unchanged. This round compares contiguous granularity with the same deterministic topology order and greedy cycles core assignment. No strong-edge aggregation or local search was performed.", "",
             f"Diagnosis cases ({len(diag)}): " + ", ".join(diag),
             f"Validation cases ({len(val)}; not evaluated this round): " + ", ".join(val), "",
             "## P1 diagnosis", "",
             "Phase 1 v001 cases slower than single-core by simulated core count: 2 cores 68/100, 3 cores 63/100, 4 cores 57/100, 5 cores 58/100. Diagnosis cases were selected for measured P1 regressions, core-scaling reversal, added-copy outlier, strongest parallel gain, plus small/large/deep/high-original-copy graph coverage. Graph-profile fields below are selection proxies, not evaluator metrics or causal explanations.", "",
             "| case | selection reasons | P1 v001 speedup 2/3/4/5 cores | compute ops | profile depth | profile original COPY bytes | P1 added-copy bytes (2 cores) |",
             "|---|---|---|---:|---:|---:|---:|"]
    for item in samples["diagnosis"]:
        case = item["case"]
        added = phase1[case]["problem_1:2"]["added_copy_bytes"]
        speeds = "/".join(f"{item['phase1_p1_speedup_by_cores'][str(core)]:.3f}" for core in CORE_COUNTS)
        lines.append(f"| {case} | {', '.join(item['reasons'])} | {speeds} | {item['compute_op_count']} | {item['profile_op_dependency_depth']} | {item['profile_original_graph_copy_bytes']} | {added} |")
    lines += ["",
             "## Granularity comparison", "",
             "See `diagnosis_summary.csv` (per-core means and diagnosis-case regressions) and `diagnosis_per_case.csv` (all case-level measurements). Speedup is single-core makespan divided by candidate makespan. Each candidate is compared with the byte-identical P1 v001 plan for that case/core. Added-copy bytes include spill; the separate partition/spill columns retain the official split.", "",
             "| candidate | equal-weight mean speedup (2–5 cores) | core means (2/3/4/5) | mean makespan change vs v001 (2–5 cores) |", "|---|---:|---|---:|"]
    names = list(dict.fromkeys(g["candidate"] for g in groups))
    for name in names:
        gs = sorted((g for g in groups if g["candidate"] == name), key=lambda g: g["cores"])
        score = gs[0].get("equal_weight_mean_speedup_2_to_5") if gs else None
        core_means = "/".join(f"{g['average_speedup']:.4f}" if g.get("average_speedup") is not None else "NA" for g in gs)
        deltas = [g.get("mean_makespan_change_vs_v001_percent") for g in gs if g.get("mean_makespan_change_vs_v001_percent") is not None]
        delta = sum(deltas) / len(deltas) if deltas else None
        lines.append(f"| {name} | {score:.5f} | {core_means} | {delta:+.3f}% |" if score is not None and delta is not None else f"| {name} | NA | {core_means} | NA |")
    lines += ["", "## Communication ledger", "",
              "`communication_tensor_facts.csv` preserves tensor IDs, producer/consumer op IDs, size, position, original COPY_IN/COPY_OUT op IDs, and baseline Task IDs for boundary reads/writes. `communication_summary.csv` counts distinct P1 Task boundary reads/writes and repeated shared-input reads. `communication_ledger_validation.csv` checks the v001 estimate against the evaluator for every fixed sample: distinct Task boundary reads + writes - original COPY_IN/COPY_OUT bytes must equal evaluator `partition_added_copy_bytes`. The evaluator's `added_copy_bytes` additionally includes spill; original graph COPY and spill are separate columns. A shared tensor is counted once per consuming Task, not once per consuming op.", "",
              "## Frozen candidates and limits", "",
              f"Candidates frozen for the future validation run (not run now): {', '.join(x['candidate'] for x in frozen) if frozen else 'none (no fully successful eligible candidate)'}. Validation remains untouched. No conclusion here generalizes beyond the fixed diagnosis group. Strong-edge aggregation, dependency-aware assignment, advanced features, and local search remain out of scope for this round.", "",
              "All evaluator outputs and per-candidate plans/records are under `cases/`; run metadata is in `round_manifest.json` and `last_invocation.json`.", ""]
    (OUT / "round1_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    if args.workers < 1 or args.timeout_seconds <= 0:
        parser.error("workers and timeout must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    sample_path = OUT / "sample_groups.json"
    if sample_path.exists():
        samples = json.loads(sample_path.read_text(encoding="utf-8"))
    else:
        samples = choose_samples()
        atomic_json(sample_path, samples)
    diagnosis = [x["case"] for x in samples["diagnosis"]]
    validation = [x["case"] for x in samples["validation"]]
    if len(diagnosis) != 10 or len(validation) != 10 or len(set(diagnosis + validation)) != 20:
        raise RuntimeError("sample groups must be 10+10, fixed and disjoint")
    specs = candidate_specs()
    manifest = {"round": "phase2_problem1_round1", "algorithm_version": VERSION,
                "base_algorithm": ALGORITHM_VERSION, "base_source_sha256": source_fingerprint(),
                "p1_evaluator": "official/code/multicore_cut_evaluate_problem_1.py",
                "config_sha256": sha256_file(CONFIG), "official_manifest_sha256": sha256_file(ROOT / "protection" / "official-files.sha256"),
                "sample_groups_sha256": sha256_file(sample_path), "candidate_specs": specs,
                "cores": list(CORE_COUNTS), "timeout_seconds": args.timeout_seconds,
                "validation_evaluator_runs": 0}
    manifest_path = OUT / "round_manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("base_source_sha256", "config_sha256", "sample_groups_sha256", "candidate_specs", "cores"):
            if old.get(key) != manifest.get(key):
                raise RuntimeError(f"Phase 2 round manifest mismatch: {key}")
    else:
        atomic_json(manifest_path, manifest)
    invocation = {"started_at": datetime.now(timezone.utc).isoformat(), "workers": args.workers,
                  "timeout_seconds": args.timeout_seconds, "problem": "P1 only",
                  "diagnosis_case_count": 10, "validation_case_count": 10,
                  "validation_runs": 0, "candidate_count": len(specs)}
    atomic_json(OUT / "last_invocation.json", invocation)
    print("Preparing plans, fixed samples and communication ledger (P1 only; official full-manifest hash scans disabled by project policy).", flush=True)
    tasks, _plan_rows = prepare_candidates(samples, specs)
    build_ledgers(samples, specs)
    print(f"Prepared {len(tasks)} diagnosis plans; running non-reused candidates.", flush=True)
    records = evaluate_candidates(tasks, args.workers, args.timeout_seconds)
    compile_results(samples, tasks)
    invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
    invocation["candidate_case_core_records"] = len(tasks)
    invocation["status_counts"] = {status: sum(r.get("status") == status for r in records)
                                    for status in ("success", "illegal", "failed", "timeout")}
    atomic_json(OUT / "last_invocation.json", invocation)
    print(f"DONE Phase 2 P1 Round 1: {len(tasks)} candidate/case/core records. "
          f"Reports: {OUT / 'round1_report.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

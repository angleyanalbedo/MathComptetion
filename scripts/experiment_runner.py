"""Reproducible evaluator invocations with integrity guards and resume records."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph_io import load_graph  # noqa: E402
from src.plan_io import write_plan  # noqa: E402
from src.scheduler import ALGORITHM_VERSION, DEFAULT_SUBGRAPH_SIZE, build_plan  # noqa: E402

OFFICIAL = ROOT / "official"
CONFIG = OFFICIAL / "data" / "config.txt"
GUARD = ROOT / "scripts" / "verify_official_integrity.py"
CORE_COUNTS = (2, 3, 4, 5)
PROBLEMS = (1, 2, 3)
PARAMETERS = {"subgraph_size": DEFAULT_SUBGRAPH_SIZE, "random_seed": None}


class IntegrityError(RuntimeError):
    """Official-file verification failed; no further evaluation is allowed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src").glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def evaluator_fingerprint(problem: str) -> dict[str, str]:
    paths = [OFFICIAL / "code" / "evaluation_validation.py"]
    if problem == "singlecore":
        paths.extend((OFFICIAL / "code" / "singlecore_evaluate.py",
                      OFFICIAL / "code" / "multicore_cut_evaluate_problem_1.py"))
    else:
        paths.append(OFFICIAL / "code" / f"multicore_cut_evaluate_problem_{problem}.py")
    # The evaluator imports these protected implementation modules.
    paths.extend(OFFICIAL / "code" / name for name in (
        "contest_io.py", "schedule_step1.py", "schedule_step2.py", "schedule_step3.py"))
    return {path.relative_to(ROOT).as_posix(): sha256_file(path) for path in paths}


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def verify_official() -> tuple[float, str, str]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(GUARD), "--verify"], cwd=ROOT,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
    )
    elapsed = time.perf_counter() - started
    if proc.returncode != 0:
        raise IntegrityError(
            f"official integrity verification failed ({proc.returncode}): "
            f"{proc.stdout}\n{proc.stderr}")
    return elapsed, proc.stdout.strip(), proc.stderr.strip()


def _attempt_dirs(parent: Path) -> list[Path]:
    if not parent.exists():
        return []
    return sorted(parent.glob("attempt_[0-9][0-9][0-9]"))


def _outputs_intact(record: dict) -> bool:
    for relative, expected_hash in record.get("output_sha256", {}).items():
        path = ROOT / relative
        if not path.is_file() or sha256_file(path) != expected_hash:
            return False
    return bool(record.get("output_sha256"))


def _reusable_success(parent: Path, fingerprint: dict, require_trace: bool = False) -> dict | None:
    for attempt_dir in reversed(_attempt_dirs(parent)):
        record_path = attempt_dir / "record.json"
        if not record_path.is_file():
            continue
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        integrity_ok = (record.get("integrity_status") in ("verified", "not_scanned_readonly_git_hook")
                        or (record.get("integrity_status") is None
                            and record.get("integrity_pre_stdout") not in (None, "")))
        if (record.get("fingerprint") == fingerprint and record.get("status") == "success"
                and integrity_ok
                and _outputs_intact(record)):
            if require_trace and not record.get("trace_retained"):
                legacy_trace = any(Path(path).name == "trace.json"
                                   for path in record.get("output_paths", []))
                if not legacy_trace:
                    continue
            return {**record, "reused": True, "record_path": str(record_path)}
    return None


def invoke_with_trace_policy(command: list[str], trace_path: Path, output_path: Path,
                             timeout_seconds: float, retain_trace: bool = False) -> dict:
    """Run an evaluator with a transient trace; retain only on explicit request."""
    started = time.perf_counter()
    return_code: int | None = None
    stdout = stderr = ""
    timed_out = False
    trace_status = "not_generated"
    with tempfile.TemporaryDirectory(prefix="ap_multicore_trace_") as temporary_dir:
        temporary_trace = Path(temporary_dir) / "trace.json"
        actual_command = [str(temporary_trace) if item == str(trace_path) else item
                          for item in command]
        try:
            proc = subprocess.run(
                actual_command, cwd=ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout_seconds,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
            )
            return_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        elapsed = time.perf_counter() - started
        if temporary_trace.is_file():
            if retain_trace:
                trace_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(temporary_trace, trace_path)
                trace_status = "retained_requested"
            else:
                trace_status = "generated_discarded"
        recorded_command = ["<TEMP_TRACE_PATH>" if item == str(temporary_trace) else item
                            for item in actual_command]
    return {"command": recorded_command, "return_code": return_code,
            "stdout": stdout, "stderr": stderr, "timed_out": timed_out,
            "elapsed_seconds": elapsed, "trace_status": trace_status,
            "trace_retained": trace_status.startswith("retained_")}


def _next_attempt(parent: Path) -> Path:
    existing = _attempt_dirs(parent)
    number = max((int(path.name[-3:]) for path in existing), default=0) + 1
    attempt = parent / f"attempt_{number:03d}"
    attempt.mkdir(parents=True, exist_ok=False)
    return attempt


def _write_capture(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", errors="replace")


def _result_fields(result: dict, problem: str, makespan: int | float) -> dict:
    movement = result.get("data_movement_bytes") or {}
    fields: dict[str, Any] = {
        "makespan": makespan,
        "added_copy_bytes": movement.get("added_copy_bytes"),
        "scheduled_copy_bytes": movement.get("scheduled_copy_bytes"),
    }
    if problem == "3":
        cache = result.get("cache_stats") or {}
        fields.update({
            "cache_hits": cache.get("hits"),
            "cache_accesses": cache.get("accesses"),
            "cache_hit_bytes": cache.get("hit_bytes"),
            "cache_miss_bytes": cache.get("miss_bytes"),
            "cache_hit_rate": cache.get("hit_rate"),
        })
    return fields


def run_one_evaluator(
    *, graph_path: Path, plan_path: Path | None, problem: str, cores: int,
    case_dir: Path, timeout_seconds: float, input_hash: str,
    generation_seconds: float | None, force: bool = False,
    integrity_scope: str = "none", batch_id: str | None = None,
    retain_trace: bool = False,
) -> dict:
    if integrity_scope not in ("per_evaluator", "batch", "none"):
        raise ValueError(f"unsupported integrity scope: {integrity_scope}")
    if problem == "singlecore":
        parent = case_dir / "singlecore"
        evaluator = OFFICIAL / "code" / "singlecore_evaluate.py"
        result_rel = "result.json"
        record_cores = 1
        parameter_fingerprint = {"reference": "official_singlecore_v1"}
        command_base = [str(evaluator), str(graph_path), "--config", str(CONFIG)]
    else:
        parent = case_dir / f"cores_{cores}" / f"problem_{problem}"
        evaluator = OFFICIAL / "code" / f"multicore_cut_evaluate_problem_{problem}.py"
        result_rel = "result.json"
        record_cores = cores
        parameter_fingerprint = {
            "algorithm_version": ALGORITHM_VERSION,
            "algorithm_sha256": source_fingerprint(),
            **PARAMETERS,
        }
        command_base = [str(evaluator), str(graph_path), str(plan_path), "--config", str(CONFIG)]

    command_fingerprint = [Path(sys.executable).as_posix(), *command_base,
                           "-o", result_rel, "--trace-output", "trace.json",
                           "--log-output", "official.log"]
    fingerprint = {
        "case": graph_path.stem,
        "problem": problem,
        "cores": record_cores,
        "input_sha256": input_hash,
        "config_sha256": sha256_file(CONFIG),
        "evaluator_sha256": evaluator_fingerprint(problem),
        "parameters": parameter_fingerprint,
        "command_template": command_fingerprint,
    }
    if not force:
        cached = _reusable_success(parent, fingerprint, require_trace=retain_trace)
        if cached:
            print(f"REUSE {graph_path.stem} {problem} cores={record_cores}", flush=True)
            return cached

    attempt_dir = _next_attempt(parent)
    output_path = attempt_dir / result_rel
    trace_path = attempt_dir / "trace.json"
    log_path = attempt_dir / "official.log"
    stdout_path = attempt_dir / "stdout.txt"
    stderr_path = attempt_dir / "stderr.txt"
    command = [sys.executable, *command_base,
               "-o", str(output_path), "--trace-output", str(trace_path),
               "--log-output", str(log_path)]
    started_at = datetime.now(timezone.utc).isoformat()

    precheck_seconds = 0.0
    postcheck_seconds = 0.0
    stdout = stderr = ""
    if integrity_scope == "per_evaluator":
        precheck_seconds, pre_out, _pre_err = verify_official()
    elif integrity_scope == "batch":
        precheck_seconds, pre_out = 0.0, f"covered by batch preflight {batch_id}"
    else:
        precheck_seconds, pre_out = 0.0, "full official manifest scan disabled by read-only/Git-hook project policy"
    invocation = invoke_with_trace_policy(command, trace_path, output_path,
                                          timeout_seconds, retain_trace=retain_trace)
    command = invocation["command"]
    return_code = invocation["return_code"]
    stdout, stderr = invocation["stdout"], invocation["stderr"]
    timeout = invocation["timed_out"]
    elapsed = invocation["elapsed_seconds"]
    _write_capture(stdout_path, stdout)
    _write_capture(stderr_path, stderr)
    if integrity_scope == "per_evaluator":
        postcheck_seconds, post_out, post_err = verify_official()
    elif integrity_scope == "batch":
        postcheck_seconds, post_out, post_err = 0.0, f"pending batch postflight {batch_id}", ""
    else:
        postcheck_seconds, post_out, post_err = 0.0, "full official manifest scan disabled by read-only/Git-hook project policy", ""

    parsed = None
    parse_error = None
    if not timeout and return_code == 0:
        try:
            parsed = json.loads(output_path.read_text(encoding="utf-8"))
            makespan = parsed.get("makespan")
            if isinstance(makespan, bool) or not isinstance(makespan, (int, float)):
                raise ValueError("result has no numeric makespan")
        except (OSError, json.JSONDecodeError, ValueError, AttributeError) as exc:
            parse_error = str(exc)

    if timeout:
        status = "timeout"
    elif return_code != 0 and ("EVALUATION ERROR" in stderr or "EVALUATION ERROR" in stdout):
        status = "illegal"
    elif return_code != 0 or parse_error:
        status = "failed"
    else:
        status = "success"

    output_paths = [path for path in (output_path, trace_path, log_path, stdout_path, stderr_path)
                    if path.is_file()]
    relative_output_hashes = {
        path.relative_to(ROOT).as_posix(): sha256_file(path) for path in output_paths
    }
    result = _result_fields(parsed, problem, parsed["makespan"]) if status == "success" else {}
    record = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "case": graph_path.stem,
        "problem": problem,
        "cores": record_cores,
        "version": ALGORITHM_VERSION if problem != "singlecore" else "official_singlecore_v1",
        "status": status if integrity_scope in ("per_evaluator", "none") else "pending_integrity",
        "evaluator_status": status,
        "integrity_scope": integrity_scope,
        "integrity_status": ("verified" if integrity_scope == "per_evaluator"
                             else "not_scanned_readonly_git_hook" if integrity_scope == "none"
                             else "pending"),
        "integrity_batch_id": batch_id,
        "exit_code": return_code,
        "timeout_seconds": timeout_seconds,
        "timeout": timeout,
        "trace_status": invocation["trace_status"],
        "trace_retained": invocation["trace_retained"],
        "generation_seconds": generation_seconds,
        "evaluator_seconds": round(elapsed, 6),
        "integrity_check_seconds": round(precheck_seconds + postcheck_seconds, 6),
        "integrity_pre_stdout": pre_out,
        "integrity_post_stdout": post_out,
        "integrity_post_stderr": post_err,
        "command": command,
        "fingerprint": fingerprint,
        "result": result,
        "error": parse_error or (stderr.strip() if status != "success" else None),
        "output_paths": [path.relative_to(ROOT).as_posix() for path in output_paths],
        "output_sha256": relative_output_hashes,
    }
    record_path = attempt_dir / "record.json"
    atomic_json(record_path, record)
    record["record_path"] = str(record_path)
    print(
        f"{status.upper()} {graph_path.stem} {problem} cores={record_cores} "
        f"seconds={elapsed:.3f} makespan={result.get('makespan', '')}",
        flush=True,
    )
    return record


def finalize_batch_integrity(records: list[dict], batch_id: str) -> None:
    """Promote pending evaluator statuses only after the batch postflight passes."""
    try:
        elapsed, stdout, stderr = verify_official()
        verification_ok = True
        error = None
    except IntegrityError as exc:
        elapsed, stdout, stderr = 0.0, "", ""
        verification_ok = False
        error = str(exc)
    for returned in records:
        path = Path(returned["record_path"])
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("integrity_batch_id") != batch_id:
            continue
        record["integrity_post_seconds"] = round(elapsed, 6)
        record["integrity_post_stdout"] = stdout
        record["integrity_post_stderr"] = stderr
        record["integrity_status"] = "verified" if verification_ok else "failed"
        record["status"] = record["evaluator_status"] if verification_ok else "failed"
        if not verification_ok:
            record["error"] = f"batch integrity postflight failed: {error}"
        atomic_json(path, record)
        returned["status"] = record["status"]
        returned["integrity_status"] = record["integrity_status"]
    if not verification_ok:
        raise IntegrityError(f"official integrity failed after batch {batch_id}: {error}")


def generate_case_plan(graph_path: Path, case_dir: Path, cores: int) -> tuple[Path, float, str]:
    graph = load_graph(graph_path)
    started = time.perf_counter()
    plan = build_plan(graph, cores, DEFAULT_SUBGRAPH_SIZE)
    generation_seconds = time.perf_counter() - started
    plan_path = case_dir / f"cores_{cores}" / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if not plan_path.is_file() or plan_path.read_text(encoding="utf-8") != serialized:
        write_plan(plan, plan_path)
    # Use the official plan validator before invoking official evaluators; the
    # evaluator will validate it again as the final authority.
    official_code = str(OFFICIAL / "code")
    if official_code not in sys.path:
        sys.path.insert(0, official_code)
    from stub_multicore_cut_and_schedule import validate_multicore_plan
    validate_multicore_plan(graph, plan)
    return plan_path, generation_seconds, sha256_file(plan_path)

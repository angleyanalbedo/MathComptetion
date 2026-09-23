---
name: ap-multicore-scheduling
description: Analyze and optimize the 2026 Huawei Cup mathematical modeling A problem on multicore NPU scheduling. Use for the supplied tensor/op/edge JSON cases, graph profiling, partitioning, core assignment, schedule search, evaluator runs, and experiment tracking. Do not use for GE/CANN compiler debugging or real-device profiling.
metadata:
  short-description: Multicore NPU scheduling contest workflow
---

# Multicore NPU Scheduling Contest

Use this skill for the contest project in this workspace. Read the project `agent.md`, `plan.md`, and `todo.md` first when present, then the relevant evaluator code and `README.md`. The contest evaluator is the authority for legality and measured performance.

## Problem contract

- Input graphs are JSON objects with `tensors`, `ops`, and `edges`; edges encode tensor-to-op and op-to-tensor dependencies.
- The solution maps every non-`COPY_IN`/`COPY_OUT` op id to a subgraph id, then lists each subgraph exactly once in a per-core schedule.
- Problem 1 is scene A: every subgraph is its own Task and boundary data passes through DDR.
- Problems 2 and 3 are scene B: each core's subgraphs form one Task; same-core data may remain in L1/UB, while cross-core data incurs copies and synchronization. Problem 3 adds the shared read-only FIFO L2 cache.
- Preserve the supplied `data/config.txt` and evaluator behavior. Never treat estimates from graph profiling as evaluator results.

## Workflow

1. Establish graph facts before proposing a heuristic. Use `scripts/analyze_cases.py` on one JSON or a case directory to summarize graph size, op and Pipe workload, compute-only critical-path proxy, DDR copy bytes, tensor reuse and topological-order L1/UB live-byte estimates.
2. Read `references/metrics-and-interpretation.md` before using these metrics to choose a strategy. Label topology-order memory peaks and compute-only critical paths as estimates; actual spill, transfer contention, cache hits and Makespan must come from the official evaluator.
3. Build a deterministic legal baseline, then add one idea at a time: critical-path/load balance, communication and reuse awareness, cache/capacity awareness, and local search. Use fixed seeds when randomness is involved.
4. Evaluate every candidate with the official evaluator for the relevant problem and core counts. Reject invalid candidates. Do not change evaluator scripts or config to improve scores.
5. Record algorithm version, parameters, seed, cases, evaluator results, runtime and failure causes in the project's experiment records and `todo.md`. Compare means and worst regressions, not just a favorable case.

## Heuristic signals

- Large compute critical path: preserve the critical chain and seek parallelism among independent branches.
- Imbalanced `PIPE_M` / `PIPE_V` work: balance work by execution pipe as well as total cycles.
- High boundary tensor bytes: keep strongly communicating operations together when that does not create excessive cache pressure.
- High reusable input bytes: group consumers to reduce repeated reads, especially when evaluating scene B / L2.
- Estimated L1/UB peak near capacity: avoid oversized merges and check evaluator spill/copy results.

These are candidate signals, not rules that override measurement. A heuristic is retained only when evaluator results support it across representative cases and then the full benchmark set.

## Scope and sources

The contest-specific graph analyzer is intentionally small and reads the contest JSON directly; it does not parse GE Dump or FX Graph formats. Its design borrows the graph-structure analysis and optimization-recommendation direction described by CANNBot's `model-recommend-analysis` contribution, then adapts it to this problem's explicit tensor sizes, pipes, dependencies and evaluator metrics. See [metrics and interpretation](references/metrics-and-interpretation.md) and the [upstream merge request](https://gitcode.com/cann/cannbot-skills/pull/921).

Do not infer hardware behavior from GE memory-analysis, stream-log or fusion-pass procedures. For contest performance claims, use the provided evaluator, traces and fixed configuration.

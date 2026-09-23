---
name: ap-multicore-scheduling
description: Analyze and optimize the 2026 Huawei Cup mathematical modeling A problem on multicore NPU scheduling. Use for the supplied tensor/op/edge JSON cases, graph profiling, partitioning, core assignment, schedule search, evaluator runs, and experiment tracking. Do not use for GE/CANN compiler debugging or real-device profiling.
metadata:
  short-description: Multicore NPU scheduling contest workflow
---

# Multicore NPU Scheduling Contest

Use this skill for the contest project in this workspace. Read the project `agent.md`, `plan.md`, `todo.md`, and `README.md` in that order, then the relevant evaluator code. Take the current phase, best version, budgets and pending work from those documents; do not restart completed experiments. The contest evaluator is the authority for legality and measured performance.

## Problem contract

- Input graphs are JSON objects with `tensors`, `ops`, and `edges`; edges encode tensor-to-op and op-to-tensor dependencies.
- The solution maps every non-`COPY_IN`/`COPY_OUT` op id to a subgraph id, then lists each subgraph exactly once in a per-core schedule.
- Problem 1 is scene A: every subgraph is its own Task and boundary data passes through DDR.
- Problems 2 and 3 are scene B: each core's subgraphs form one Task; same-core data may remain in L1/UB, while cross-core data incurs copies and synchronization. Problem 3 adds the shared read-only FIFO L2 cache.
- Treat `official/` as read-only: preserve `official/data/config.txt`, all supplied graphs, and evaluator behavior. Never treat estimates from graph profiling as evaluator results.

## Workflow

1. Establish graph facts before proposing a heuristic. Use `scripts/analyze_cases.py` on one JSON or a case directory to summarize graph size, op and Pipe workload, compute-only critical-path proxy, DDR copy bytes, tensor reuse and topological-order L1/UB live-byte estimates.
2. Read `references/metrics-and-interpretation.md` before using these metrics to choose a strategy. Label topology-order memory peaks and compute-only critical paths as estimates; actual spill, transfer contention, cache hits and Makespan must come from the official evaluator.
3. Reuse the frozen legal baseline/current best registered in the project; build a baseline only when missing and allowed by the current phase. Add one idea at a time under the experiment order below and in `plan.md`. Use fixed seeds when randomness is involved.
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

## CANN/GE adaptation boundaries

- Describe candidates as contest mathematical abstractions and heuristics inspired by CANN/GE mechanisms. Claim reproduction of a specific algorithm only with an official definition and implementation correspondence. The CANNBot source above concerns the graph analyzer, not the scheduler or GE implementation.
- Borrow Fusion's locality idea. The submission controls only `node_to_subgraph` and `core_schedules`; merging subgraphs does not implement UB Fusion, change original op cycles, perform real kernel tiling, or confer instruction-level fusion gains.
- Prefer lifetime-aware ordering hypotheses over a custom memory address allocator. Official kernel scheduling handles spill/reload and memory reuse. Verify the chain from plan changes to effective order/assignment, lifetime/peak occupancy, spill/traffic, and Makespan; none of these improvements implies the next automatically. Official GE/Topo sources and contest mappings are recorded in `plan.md`.
- In P1, each subgraph is a separate Task and private cache is cleared between Tasks. Reordering Tasks with partition and core assignment fixed does not directly change within-Task topology or tensor lifetimes; investigate dependency waits and DDR concurrency without assuming spill reduction.
- In P2/P3, all subgraphs on one core form one Task. A split creates no new same-core Task, does not clear L1/UB, and does not eliminate same-core COPY. Its benefit must come from a legal order change within the merged Task or reassignment to cores that changes lifetime, spill or cross-core traffic. Same-core merge does not automatically eliminate additional boundary COPY either.
- For Scene B, inspect `_prioritize_task_seq` and subsequent Step2/3 in the evaluator to determine how a submitted subgraph order affects execution. Do not equate `core_schedules` with the final per-op execution timeline.

## Staged refinement

Follow the active phase and frozen protocol in `plan.md`; permission to review or edit planning documents is not a request to run optimization experiments.

1. P1 Phase 2B first group: tensor lifetime / peak-pressure diagnosis, then bounded reorder with partition/assignment fixed. Record Makespan, spill and added-copy, including unchanged spill; apply the P1 boundary above.
2. Second group: M/V/DDR multidimensional load with move/swap, independently compared against the same frozen initial solution. Test combinations separately so gains remain attributable.
3. Third group: bounded merge/split only when the first two groups leave evidence of a partition bottleneck. Record the evidence and check DAG legality, capacity and parallelism risk. Do not initially enable all neighborhoods together.
4. Strengthen merged-Task lifetime modeling in P2. For P2/P3 pressure-driven refinement, first consider legal reorder; require an explicit order/reassignment mechanism before enabling split, rather than using high pressure alone as justification.

Before examining candidate results, freeze triggers, candidate rules, acceptance rules, tie-breaks, seeds and evaluator/time budgets. Use the fixed diagnosis → freeze → validation → full benchmark protocol; maintain independent P1/P2/P3 bests and the project's declared algorithm-level selection metric. Preserve the canonical best and historical results until the project's replacement and archival conditions are met.

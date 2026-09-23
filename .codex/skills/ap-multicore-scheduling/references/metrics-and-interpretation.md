# Contest graph profile metrics

The analyzer consumes the contest's `tensors` / `ops` / `edges` JSON schema. Its output is for workload characterization and heuristic selection, not scoring.

## Metrics

- **Compute cycles by op and Pipe:** sum `cycles` for non-copy operations. COPY cycles are reported separately because DDR transfer duration is modeled from byte volume and shared bandwidth.
- **Compute-only critical path:** longest weighted path through the operation dependency DAG using non-copy `cycles`. This omits transfer time, pipe contention, cross-task waits, and spill operations, so it is only a parallelism proxy.
- **Original DDR copy bytes:** sum tensor sizes moved by original `COPY_IN` and `COPY_OUT` operations, inferred from their adjacent DDR tensors.
- **Tensor fanout / reusable bytes:** count bytes of intermediate tensors consumed by multiple operations. This indicates possible reuse value; it does not guarantee a particular cut can retain the data.
- **L1/UB live-byte peak estimate:** simulate tensor lifetimes over one deterministic topological order. Scheduling can change the peak, and the estimate does not model the evaluator's spill algorithm.
- **Graph topology:** node counts, op-type counts, edge counts, tensor bytes by logical position, max fanout and op-level dependency depth.

## Interpretation limits

The evaluator's Makespan, `added_copy_bytes`, cache hit rate, legality checks and traces are authoritative. Never substitute a graph-profile estimate for these values. In particular:

- A low compute-only critical path does not imply a low Makespan if DDR traffic or synchronization dominates.
- A high fanout tensor is only a reuse opportunity; partitioning and capacity constraints determine whether reuse is realized.
- A topology-order L1/UB peak is not the evaluator's peak and is not proof of spill.
- The original graph's DDR traffic is not the same as schedule-added traffic.

## Upstream inspiration

CANNBot's `model-recommend-analysis` contribution describes GEDump and FX graph analysis for repeated structures and optimization recommendations, alongside Profiling analysis. This contest analyzer borrows the graph-first recommendation approach only. The upstream formats and profiling records are not assumed to match contest JSON or evaluator outputs. Source: [CANNBot merge request !921](https://gitcode.com/cann/cannbot-skills/pull/921).

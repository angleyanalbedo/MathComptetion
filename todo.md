# TODO

## Current status

- phase: Phase 2 Problem 1 优化
- state: in_progress
- best_algorithm: bounded_communication_aware_contiguous_cuts_greedy_cycles
- best_version: p1_bounded_communication_cuts_round2_v001
- last_experiment: v012_phase2_p1_communication_cut_full_benchmark
- next_step: v013 累计 cycles 切分 diagnosis 已结束并记录负结果；下一步固定通信切图，只比较依赖感知 list scheduling 与原 greedy 分核

## Current best

- problem_1_mean_speedup_across_2_to_5_core_group_means: 1.131712
- problem_2_mean_speedup_across_2_to_5_core_group_means: 1.702996
- problem_3_mean_speedup_across_2_to_5_core_group_means: 1.716313
- legal_rate: 100% (1200/1200 multicore evaluator runs succeeded)
- runtime_per_case: see per-case evaluator and generation timings in `experiments/phase1_baseline/v001/reports/per_case.csv`

### Current P1 best update (Phase 2 full comparison)

- algorithm: `p1_contiguous_granularity_round1_fixed_256`
- parameters: topological contiguous chunks of 256 compute ops; greedy minimum cumulative cycles assignment
- full_100_case_equal_weight_mean_speedup_2_to_5: 1.208137
- full run: 400/400 P1 case×core records successful; zero illegal/failed/timeout
- comparison: fixed_128 = 1.202703; Phase 1 v001 = 1.131712
- caveat: individual regressions remain; worst observed is case_001 at 4 cores (+109.651% Makespan vs v001)
- artifacts: `experiments/phase2_problem1/full_v001/`

### Current P1 best update (communication-cut full comparison)

- algorithm: `p1_bounded_communication_cuts_round2_v001`
- parameters: target 256 ops, chunks 128–384 ops, cut candidates within ±32 of equal-sized ideal cut positions; minimize proxy intermediate-tensor bytes crossing boundaries; retain greedy cumulative-cycles core assignment
- full_100_case_equal_weight_mean_speedup_2_to_5: 1.804826
- full run: 400/400 P1 case×core records successful; zero illegal/failed/timeout
- comparison: fixed-256 = 1.208137; mean Makespan change vs fixed-256 by core count = -16.714%, -22.228%, -23.500%, -24.763%; mean added-copy incl. spill = 15,954,046 bytes vs fixed-256 17,201,681 bytes
- caveat: largest regressions vs fixed-256: case_063/5 cores (+160.427%), case_062/5 (+148.267%), case_062/4 (+145.326%), case_063/4 (+131.028%), case_028/5 (+121.925%)
- artifacts: `experiments/phase2_problem1/round2_communication_full/`

## Pending

- [x] 检查 100 个正式 case 是否均能被读取
- [x] 建立官方文件 Git 基线并启用提交保护钩子
- [x] 将官方原件集中迁移到 `official/`，算法与实验目录分离
- [x] 运行最小正式 case 和 stub 方案，确认方案生成接口
- [x] 对 `case_019` 运行 `singlecore_evaluate.py`，确认单核基线接口
- [x] 对同一方案运行问题 1、2、3 官方评估器，核对结果/日志/Trace 输出
- [x] 确认官方 100 个 case 与配置只读，评估前后 114 项哈希均通过
- [x] Phase 0 环境与接口确认完成（保留历史记录）
- [x] 更新算法/实验计划与 Phase 1 全部满足式验收条件
- [x] 实现 v001 图读取、含 COPY 路径的完整 op DAG 与稳定拓扑排序
- [x] 实现固定 64-op 拓扑连续切图和最小累计 cycles greedy 核分配
- [x] 合成图测试：链、分支汇聚、独立分支、COPY 路径、循环拒绝、同输入确定性
- [x] 实现带哈希指纹和成功断点续跑的单 case / batch runner
- [x] 选择代表性正式图，验证 2/3/4/5 核 × P1/P2/P3（65/65 成功）
- [x] 冻结 v001 参数并运行 100 个正式单核评估（100/100 成功）
- [x] 运行 100 cases × 4 核 × 3 problems（1200/1200 成功；非法、失败、超时均为 0）
- [x] 生成 1300 行逐项 CSV、12 组汇总、三问独立 case/core best 和瓶颈分析
- [x] 单核与多核批次前后官方文件完整性校验均通过；最终复核 114 项
- [x] Phase 1 全部验收条件满足，标记 complete；停止于 Phase 1

## Phase 2 规划与待办

- [x] 归档 Phase 1 算法、统计口径、复现命令和局限：`experiments/phase1_baseline/v001/README.md`（仅文档核对，未重跑实验）
- [x] 在 `plan.md` 细化 Phase 2 分步对照、全量验证和验收规则
- [x] 明确全局 best 按平均 speedup 选择、case/core best 按最小 Makespan；Phase 2 只比较 P1
- [x] 固定不重叠的 10 个 diagnosis 与 10 个 validation case，记录名单及选择依据；冻结候选后才运行 validation（本轮 validation evaluator 调用数为 0）
- [x] 建立按 tensor/Task 去重的通信账本；合成小图测试通过，并在 20 个固定样本上与 v001 evaluator 的 partition_added_copy_bytes 精确对账，spill 单独列出
- [x] 固定拓扑序与 greedy 分核，对照 32/64/128/256 切块粒度；P1 v001 64 结果按匹配计划复用
- [x] 单独对照相对粒度 K=min(N_op,c×cores), c=2/4/8，记录 B、目标/实际子图数及运行时间
- [x] 汇总首轮诊断、账本和粒度对照结论；未启动强边聚合或局部搜索
- [x] 对冻结的 fixed_128、fixed_256 在固定 validation 组运行 80 项 P1 评估并生成汇总（80/80 success；候选参数未因 validation 修改）
- [x] 完成筛选候选的 100 cases × 4 核 P1 全量比较（800/800 candidate records successful；160 diagnosis/validation records 按匹配指纹复用）
- [x] 依据全量 benchmark 选择 fixed_256 为当前统一 P1 best（等权平均逐 case speedup 1.208137；记录逐 case 退化）
- [x] 对冻结的 fixed_128、fixed_256 在固定 validation 组运行 80 项 P1 评估并生成汇总（80/80 success；fixed_256 四档核数均胜过 fixed_128；候选参数不因 validation 修改）
- [x] 完成 fixed_128/fixed_256 的 100 cases × 4 核 P1 全量比较（800/800 successful records；结果见 `experiments/phase2_problem1/full_v001/`）
- [x] 通信感知切点候选：固定诊断组 10 cases × 4 cores，与固定 64、当前 best fixed-256 对照（120/120 success，其中新候选 40 次评估；diagnosis mean speedup 1.728536 vs fixed-256 1.702469）
- [x] 候选已冻结（目标256、范围128–384、窗口±32）；运行 validation 组 40 项 P1 评估（40/40 success；均值 speedup 1.809944，较 fixed-256 平均 Makespan 改善约 18.6%）
- [x] 通信切点候选 100 cases × 4 cores P1 全量验证（400/400 success；仅复用匹配指纹的 80 条 diagnosis/validation 记录），按预设 Best 规则更新 P1 best并报告退化
- [x] 按累计 cycles 切分作为独立对照，不与通信策略同时首次加入（40/40 legal/success；等权 speedup 1.177948，明显低于通信切点的 1.728536；未进入 validation，未调参）
- [ ] 固定当前通信切图，单独验证依赖感知 list scheduling（下一项；保持 partition 和其余特征冻结）
- [ ] 后续独立测试 DAG 强边聚合/分支感知构造，固定分核并逐次检查收缩后全局 DAG；不混入局部搜索
- [ ] 分别验证关键路径优先级、后继工作量、Cube/Vector 工作量和缓存压力约束，记录负收益模块
- [ ] Diagnosis 筛选后冻结至多两个候选及参数，先 validation 再分别完成 400 项 P1 全量评估；记录验证集反馈是否用于继续开发
- [ ] 按四个核数分别报告平均 speedup、等权总体均值及逐 case 退化，依据新 Best 规则选择 P1 算法
- [ ] 对最终组合做移除消融，独立更新 P1 best，记录 Phase 3 入口或预算下未完成项

## 后续阶段待办

- [ ] 最终报告补齐 P3 同核数无 L2/有 L2 对比、1～5 核曲线及字节口径 Cache 命中率
- [ ] 测试 communication-weighted merge
- [ ] 测试 cache-aware merge/split
- [ ] 测试 move/swap/reorder 局部搜索
- [ ] 完成消融实验
- [ ] 完整运行 100 cases × 2～5 cores × 3 problems

## Failed ideas

- `cumulative_cycles_contiguous_cuts_v001`：固定 10-case diagnosis 上等权 mean speedup 1.177948，低于 communication-cut 1.728536 和 fixed-256 1.702469；3/4/5 核相对 v001 平均 Makespan 分别 +30.787%/+39.437%/+62.352%。不进入 validation、不做全量、不调参。结果：`experiments/phase2_problem1/round3_cycles/`。

## Experiment log

| version | phase | scope | seed | result | status |
|---|---|---|---:|---|---|
| v001 | Phase 0 | 100 cases graph profile; outputs in `experiments/phase0/graph-profile-v1/` | 0 | 100/100 parsed; no evaluator metrics collected | complete |
| v002 | Phase 0 | Commit official baseline and enable pre-commit integrity guard | 0 | 114 official files verified; raw case files excluded from Git and hash-protected | complete |
| v003 | Phase 0 | Move official files under `official/`; reserve `src/` for scheduler; move graph profile under `experiments/phase0/` | 0 | Path references and integrity guard updated; evaluator loop not yet run | complete |
| v004 | Phase 0 | `case_019` (766 ops; stub plan: 647 compute ops, 10 subgraphs, 4 cores); single-core + problems 1–3 | 0 | All four evaluator runs exited 0; output fields, JSON/log/Trace paths and official hashes verified; one-case smoke only, not benchmark baseline | complete |
| v005 | Phase 1 | 5 representative cases; single-core + 2/3/4/5 cores × P1/P2/P3 | none | 65/65 evaluator runs succeeded; 5 synthetic tests passed; deterministic plan and metrics pipeline validated. Outputs in `experiments/phase1_baseline/v001/` | complete |
| v006 | Phase 1 | 100 formal cases; single-core + 2/3/4/5 cores × P1/P2/P3 | none | 100/100 single-core and 1200/1200 multicore runs succeeded; 1300 per-case rows, 12 fully successful groups, initial bests and bottleneck analysis generated; final official integrity check passed for 114 files | complete |
| v007 | Phase 2 P1 | 10 diagnosis cases; 4 core counts; fixed 32/64/128/256 and relative c=2/4/8 | none | 280 candidate×case×core records all successful (240 new P1 calls + 40 verified v001 reuses); tensor ledger reconciled exactly against evaluator partition-added bytes on 20 fixed cases; diagnosis top two frozen as fixed_128/fixed_256; validation not run. Diagnosis-only equal-weight mean speedup: v001 1.61449, fixed_128 1.77131, fixed_256 1.70247; v001 remains P1 best pending validation/full evaluation. Outputs in `experiments/phase2_problem1/round1/` | complete |
| v008 | Phase 2 P1 | frozen validation cases (10) × 4 cores × fixed_128/fixed_256 | none | 80/80 successful; no parameters changed after freeze. Outputs in `experiments/phase2_problem1/validation_v001/` | complete |
| v009 | Phase 2 P1 | 100 cases × 4 core counts × fixed_128/fixed_256 | none | 800/800 records successful; equal-weight mean speedup 1.202703 (fixed_128) and 1.208137 (fixed_256); fixed_256 selected as current uniform P1 best, with individual regressions reported. Outputs in `experiments/phase2_problem1/full_v001/` | complete |
| v010 | Phase 2 P1 | 10 diagnosis cases × 4 core counts × fixed_064/fixed_256/communication-aware cuts | none | 120/120 success (80 exact-fingerprint controls reused + 40 fresh comm-cut evaluator calls); diagnosis mean speedup 1.728536 vs fixed-256 1.702469. Outputs in `experiments/phase2_problem1/round2_communication/` | complete |
| v011 | Phase 2 P1 | frozen 10 validation cases × 4 core counts × communication-cut candidate | none | 40/40 successful; equal-weight mean speedup 1.809944, mean Makespan improved 14.3–20.9% vs fixed-256 across core counts; no validation-driven tuning. Outputs in `experiments/phase2_problem1/round2_communication_validation/` | complete |
| v012 | Phase 2 P1 | 100 cases × 4 core counts × frozen communication-cut candidate | none | 400/400 successful; equal-weight mean speedup 1.804826 vs fixed-256 1.208137; mean added-copy incl. spill down about 7.3%; case_062/063/028 severe regressions retained in report. Outputs in `experiments/phase2_problem1/round2_communication_full/` | complete |
| v013 | Phase 2 P1 | 10 diagnosis cases × 4 core counts × fixed_256/communication-cut/cumulative-cycles cuts | none | 120/120 success (80 exact-fingerprint controls reused + 40 cycle-cut evaluator runs); cycle-cut mean speedup 1.177948 and severe degradation vs current best, so rejected before validation. Outputs in `experiments/phase2_problem1/round3_cycles/` | complete |
| v014 | Phase 2 P1 | fixed communication-cut partition; compare greedy vs dependency-aware list scheduling | none | Next controlled diagnosis experiment; partition remains unchanged. | pending |

## Rules for updating this file

- 每次实验结束后更新状态，不保留“正在进行”但没有下一步的记录。
- 新 best 必须记录版本、参数、结果文件位置和合法率。
- 失败实验必须写入 Failed ideas，避免重复搜索。
- 只记录可复现的数值；未知值使用 `TBD`，不猜测。

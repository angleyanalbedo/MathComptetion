# TODO

## Current status

- phase: Phase 2 Problem 1 优化
- state: complete
- best_algorithm: communication_cut_plus_dependency_list_cube_vector_pipe_critical_path_priority
- best_version: p1_cube_vector_pipe_priority_round8_v001
- last_experiment: v025_phase2_p1_final_ablation_closeout
- next_step: Phase 2 已完成；下一阶段启动时先在场景 B 对比共享 baseline 与冻结 P1 best；本轮未执行 P2/P3

## 各阶段归档与精简状态

本表按阶段独立维护，不随 Current status 切换而删除历史行。仅 `complete` 且归档核验为 `verified` 的阶段具备精简资格；核验记录必须包含文件保留与依赖检查依据。阶段实验验收不自动等同于精简前归档核验。

| 阶段 | 实验状态 | 归档核验 | 归档位置 | 精简状态与清单 |
|---|---|---|---|---|
| Phase 0 | complete | pending：尚未做精简前核验 | `experiments/phase0/` | 未登记精简；核验前不清理 |
| Phase 1 | complete | verified：`experiments/phase1_baseline/v001/TRACE_ARCHIVE_AUDIT.md` | `experiments/phase1_baseline/v001/` | 已清理 1,279 个非关键 Trace（4,150,490,176 B）；保留 21 个代表 Trace；清单：`experiments/phase1_baseline/v001/trace_cleanup_manifest.csv` |
| Phase 2 | complete | verified：final closeout + `ROUND_ARCHIVE_COMPACTION.md` + `ROUND8_RESTORATION_AUDIT.md` | `experiments/phase2_problem1/final/` | 中间历史轮次精简；保留 final 与 round8 best full。先删除 21,214 个文件，随后恢复 round8 2,800 个文件；净减少 21,038,867,101 B。清单：`round_compaction_manifest.csv` |
| Phase 3～6 | not_started | not_applicable | 待阶段启动后分别登记 | 不适用 |

- [x] P1 收尾完成后核验归档与复现依据；生成 Trace 精简清单并逐项校验 SHA-256 后清理，释放 11,175,816,124 B；保留汇总、方案、结果及 9 个代表 Trace。核验记录：`experiments/phase2_problem1/final/TRACE_ARCHIVE_AUDIT.md`
- [x] 按用户要求精简 Phase 2 历史中间轮次 case 目录；保留 final 及当前 round8 best full。round8 原先误被纳入精简，之后由匹配历史 plan 哈希的 400 份方案重建并重跑 P1 evaluator，400/400 成功且 Makespan 与历史逐项一致。净减少 21,038,867,101 B。审计：`experiments/phase2_problem1/final/ROUND_ARCHIVE_COMPACTION.md`、`ROUND8_RESTORATION_AUDIT.md`

## Current best

- current_p1_version: p1_cube_vector_pipe_priority_round8_v001
- current_p1_equal_weight_mean_speedup_2_to_5: 1.948976
- current_p1_legal_rate: 100% (400/400 P1 records successful)
- current_p1_artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe_full/`
- caveat: 相对 round6 为边际 best；23 项改善、348 项持平、29 项退化，最差 Makespan +4.006%
- closeout_archive: `experiments/phase2_problem1/final/`（含逐例表、分核统计、曲线、消融矩阵、哈希审计和复现命令）
- closeout_audit: 7 个对照各 400/400 成功；原始 plan/input/config/evaluator/output 哈希核验通过；21 个单元测试通过
- cache_pressure: 暂缓、未验证；没有把单切点负结果外推为方向无效

### Phase 1 冻结基线（以下不是最新 P1 best）

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

### Current P1 best update (dependency-list full comparison)

- algorithm: communication-cut partition + dependency-aware list scheduling (`p1_dependency_list_schedule_round4_v001`)
- parameters: frozen communication-cut partition; task duration proxy `sum(op cycles)`; config waits 1000 cross-core / 100 same-core; release uses max of core availability and predecessor releases; tie breaks by estimated finish, start, workload, Task ID, core ID
- full_100_case_equal_weight_mean_speedup_2_to_5: 1.900770
- full run: 400/400 successful, zero illegal/failed/timeout; 40 validation records reused exactly
- comparison: prior communication-greedy = 1.804826; mean Makespan changes by 2/3/4/5 cores = -4.788%/-5.330%/-4.999%/-4.339%; added-copy unchanged because partition is byte-identical
- caveat: 30–32 case×core entries tied/regressed per core count; worst vs communication-greedy is case_015/2 cores (+26.673%), then case_033/5 (+26.277%)
- artifacts: `experiments/phase2_problem1/round4_dependency_full/`

### Current P1 best update (critical-path priority full comparison)

- algorithm: communication-cut partition + dependency-list release estimates + critical-path ready-task priority (`p1_critical_path_list_schedule_round6_v001`)
- priority: minimize estimated finish minus downstream critical-path tail; deterministic ties by estimated finish, start, workload, Task ID, core ID
- full_100_case_equal_weight_mean_speedup_2_to_5: 1.948670 vs prior dependency-list 1.900770 (+2.52%)
- full run: 400/400 case×core records successful; 80 exact diagnosis/validation records reused after fingerprint/output-hash checks; 320 fresh evaluator calls; zero illegal/failed/timeout
- mean Makespan change vs prior best by core count = -2.392%/-1.695%/-1.562%/-1.893%; regressions remain in 69/72/76/75 case×core rows; worst is case_099/5 cores (+1.669%)
- artifacts: `experiments/phase2_problem1/round6_critical_path_full/`

### Current P1 best update (Cube/Vector Pipe-work priority full comparison)

- algorithm: communication-cut partition + dependency-aware release estimates + Cube/Vector Pipe-aware critical-path priority (`p1_cube_vector_pipe_priority_round8_v001`)
- per-Task Pipe work proxy: `max(sum(PIPE_M op cycles), sum(PIPE_V op cycles))`; path tail adds the maximum successor tail. Release estimates remain the frozen total-cycles model.
- full_100_case_equal_weight_mean_speedup_2_to_5: 1.948976 vs prior critical-path 1.948670 (+0.016%); selected only because the predefined best rule maximizes this metric
- full run: 400/400 successful; 80 exact diagnosis/validation records reused after fingerprint/output-hash validation; 320 fresh evaluator calls; zero illegal/failed/timeout
- per-core mean Makespan changes vs prior best = +0.034%/-0.058%/-0.004%/-0.006%; 377/400 case×core rows tied or regressed, worst case_060/5 cores (+4.006%). Treat as a marginal new best, not a robust broad improvement.
- artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe_full/`

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
- [x] 固定当前通信切图，单独验证依赖感知 list scheduling：40/40 legal/success；等权 mean speedup 1.975450 vs communication-greedy 1.728536；每核数平均 Makespan 改善约8.1%–11.3%，无 validation 前调参
- [x] 冻结依赖感知调度参数并跑固定 validation 组40项 P1（40/40 success；平均 Makespan 改善1.35%–4.58%；参数未改）
- [x] 对依赖感知 list-schedule 候选运行100 cases × 4 cores P1全量（400/400成功；validation 40条记录精确复用）
- [x] 依据全量比较将 dependency-list + communication-cut 组合登记为 P1 best；保留逐 case 退化清单
- [x] DAG 强边/分支感知切图 diagnosis：固定10 cases × 4 cores；120/120 success；候选等权 speedup 1.851547 低于当前 best 1.975450，四核数平均 Makespan 均变差，case_027严重退化；虽搬运略降仍拒绝，不进入 validation
- [x] 单独验证关键路径优先级（固定当前 best partition/list scheduler；diagnosis 40/40 success、等权 speedup 2.05935 vs 1.97545；validation 40/40 success，等权 speedup 1.86469 vs control 1.85321，参数未调；全量400/400成功，equal-weight speedup 1.948670 vs 1.900770；80条精确复用，320次新评估）
- [x] 基于当前 critical-path best，单独验证后继工作量 priority（40/40成功；等权 speedup 2.05954 vs 2.05935 仅+0.009%；40项中3项改善、37项持平/退化，case_014/5核+3.695%，拒绝进入 validation）
- [x] 单独验证 Cube/Vector 分 Pipe 工作量优先级（diagnosis40/40、validation40/40、full400/400 success；全量等权 speedup 1.948976 vs 1.948670 (+0.016%)；按预定数值 Best 规则登记，但记录广泛 case/core 退化与最差 +4.006%）
- [ ] 【暂缓、未验证；不属于本次收尾必做项】通用缓存/片上容量压力感知切图；单切点负结果不足以否定整个方向，不继续手工扫描切点
- [x] 缓存感知先导：case_067 × 2 核单切点扰动诊断；切点 1836→1780、56 个 op 从子图 6 移至 7，core_schedules 原样固定；官方 P1 1/1 合法。spill -80,000 B，但 Makespan +474,576（+1.462%），partition extra +16,384 B，总额外搬运 -63,616 B；按预先约束拒绝该扰动。只否定本切点选择，不代表缓存方向无效。结论：`experiments/phase2_problem1/round9_cutpoint_perturbation/round9_summary.md`。
- [x] Diagnosis 筛选后冻结 Pipe critical-path 候选并完成 validation 与 400 项 P1 全量评估；无 validation-driven 调参
- [x] 按四个核数分别报告平均 speedup、等权总体均值及逐 case 退化，round8 按预定 Best 规则保留为 P1 best
- [x] 对最终组合完成定义明确的移除消融；round6/round2 精确复用，其余缺失项各 400/400 成功

## P1 当前收尾清单

- [x] 根据 round9 负结果确定收尾范围：保留当前 best，缓存方向暂缓，不启动新优化搜索
- [x] 核对最终模块与冻结参数，建立模块移除/模块组消融矩阵，区分历史增量实验与最终组合移除消融
- [x] 按指纹、方案摘要及输出哈希复用 round6/round2；只补两项定义明确的缺失消融，各 100 cases × 4 核 P1，未调参
- [x] 按既定 Best 规则核定最终统一算法为 round8；保留 round8/round6 和全部负结果，不按 case 拼接
- [x] 在 `experiments/phase2_problem1/final/` 归档算法说明、复现入口、方案索引/指纹、逐例结果、分核汇总及 1～5 核加速比曲线
- [x] 汇总消融、改善/持平/退化、搬运/spill、生成与评估耗时；历史复用记录时间与新调用分别保留，不把耗时和墙钟混淆
- [x] 核查复现脚本及原始结果一致性；审计通过后标记 Phase 2 complete；写明 P2 场景 B 起点比较计划，本轮未执行 P2/P3

## 后续阶段待办

- [ ] 最终报告补齐 P3 同核数无 L2/有 L2 对比、1～5 核曲线及字节口径 Cache 命中率
- [ ] 测试 communication-weighted merge
- [ ] 测试 cache-aware merge/split
- [ ] 测试 move/swap/reorder 局部搜索
- [ ] 完成消融实验
- [ ] 完整运行 100 cases × 2～5 cores × 3 problems

## Failed ideas

- `round9_cutpoint_perturbation`：case_067×2 固定核心队列，仅移动切点 1836→1780；官方合法，但 Makespan +1.462%，即使 spill -80,000 B、总额外搬运 -63,616 B 仍拒绝。只否定该位置选择；通用缓存感知未验证。结论：`experiments/phase2_problem1/round9_cutpoint_perturbation/round9_summary.md`。
- `cumulative_cycles_contiguous_cuts_v001`：固定 10-case diagnosis 上等权 mean speedup 1.177948，低于 communication-cut 1.728536 和 fixed-256 1.702469；3/4/5 核相对 v001 平均 Makespan 分别 +30.787%/+39.437%/+62.352%。不进入 validation、不做全量、不调参。结果：`experiments/phase2_problem1/round3_cycles/`。
- `p1_dag_strong_edge_aggregation_v001`：diagnosis 40/40 success；等权 mean speedup 1.851547，低于当前 dependency-list best 的 diagnosis 1.975450；vs current best mean Makespan change by 2/3/4/5 cores = +12.059%/+16.953%/+23.261%/+21.048%。case_027/4-core退化约+219.228%；added-copy仅小幅下降，拒绝进入 validation。结果：`experiments/phase2_problem1/round5_dag_partition/`。
- `p1_successor_work_priority_round7_v001`：fixed diagnosis 40/40 success; equal-weight speedup 2.05954 vs critical-path current-best 2.05935 (+0.009%), only 3/40 improved and case_014/5-core regresses +3.695%; too small and inconsistent to justify validation. Results: `experiments/phase2_problem1/round7_successor_work/`.

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
| v014 | Phase 2 P1 | fixed communication-cut partition; compare greedy vs dependency-aware list scheduling | none | 40/40 new P1 evaluator runs successful; diagnosis equal-weight speedup 1.975450 vs communication-greedy 1.728536; mean Makespan improves 8.1–11.3% across core counts; max regression 3.505%. Frozen for untouched validation, no tuning. Outputs in `experiments/phase2_problem1/round4_dependency_schedule/` | complete |
| v015 | Phase 2 P1 | frozen dependency-list candidate, 10 validation cases × 4 cores | none | 40/40 successful; mean Makespan improved 1.35–4.58% vs communication-greedy across core counts; candidate unchanged. Outputs in `experiments/phase2_problem1/round4_dependency_validation/` | complete |
| v016 | Phase 2 P1 | frozen dependency-list candidate, 100 cases × 4 cores | none | 400/400 successful; equal-weight mean speedup 1.900770 vs communication-greedy 1.804826; mean Makespan improved 4.3–5.3% across cores; worst regression +26.673%. Outputs in `experiments/phase2_problem1/round4_dependency_full/` | complete |
| v017 | Phase 2 P1 | fixed dependency-list assignment; DAG strong-edge partitioning diagnosis | none | 16 unit tests pass; 120/120 success (80 exact controls reused + 40 fresh); candidate mean speedup 1.851547 vs current best 1.975450, severe case_027 regressions, rejected before validation. | complete |
| v018 | Phase 2 P1 | fixed current-best partition; critical-path priority diagnosis + validation | none | 17 unit tests pass; diagnosis 40/40 success, equal-weight speedup 2.05935 vs 1.97545; validation 40/40 success, equal-weight speedup 1.86469 vs control 1.85321 (+0.62%). No validation-driven changes; candidate frozen for full benchmark. Artifacts: `experiments/phase2_problem1/round6_critical_path/` and `round6_critical_path_validation/`. | complete |
| v019 | Phase 2 P1 | frozen critical-path priority candidate; 100 cases × 4 cores | none | 400/400 successful; 80 exact diagnosis/validation records reused after matching fingerprint/output checks, 320 fresh evaluator calls. Equal-weight mean speedup 1.948670 vs prior best 1.900770 (+2.52%); all four core-count mean Makespans improve, with per-case regressions retained. New P1 best. Artifacts: `experiments/phase2_problem1/round6_critical_path_full/`. | complete |
| v020 | Phase 2 P1 | fixed critical-path current best; successor-work priority diagnosis | none | 18 unit tests pass; 40/40 evaluator success. Equal-weight diagnosis speedup 2.05954 vs 2.05935 (+0.009%); only 3/40 case×core rows improve, 37 tie/regress; case_014/5-core worst +3.695%. Rejected before validation. Artifacts: `experiments/phase2_problem1/round7_successor_work/`. | complete |
| v021 | Phase 2 P1 | fixed critical-path best; Cube/Vector Pipe-work priority diagnosis | none | Official execution model confirms independent `PIPE_M`/`PIPE_V` executors; compute cycles are pipe durations while COPYs use bandwidth and are excluded from Task pipe sums. Implemented path tail with per-Task `max(PIPE_M, PIPE_V)` and critical-path successor recurrence; total-cycle release estimates unchanged. 20 unit tests pass; diagnosis 40/40 success, equal-weight speedup 2.06338 vs 2.05935 (+0.196%); frozen for validation. Artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe/`. | complete |
| v022 | Phase 2 P1 | frozen Cube/Vector pipe-tail candidate; 10 validation cases × 4 cores | none | 40/40 evaluator success; equal-weight speedup 1.86921 vs current-best control 1.86469 (+0.242%); core 3 average slightly worse and other cores near-tied/improved; no validation-driven changes. Frozen for full benchmark. Artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe_validation/`. | complete |
| v023 | Phase 2 P1 | frozen Cube/Vector pipe-tail candidate; 100 cases × 4 cores | none | 400/400 success; 80 exact diagnosis/validation records reused after input, configuration, plan fingerprint and output-hash checks; 320 fresh calls. Equal-weight speedup 1.948976 vs 1.948670 (+0.016%), so registered as marginal P1 best per predeclared numerical rule; 377/400 case×core rows tie/regress and worst is +4.006%. Artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe_full/`. | complete |
| v024 | Phase 2 P1 | case_067 × 2-core single-cutpoint perturbation; fixed original core_schedules | none | 1/1 official P1 success; moved boundary 1836→1780 (56 ops, subgraph 6→7), with core schedules unchanged. Spill 127,092,224→127,012,224 B (-80,000); partition-added bytes +16,384; total added bytes -63,616; Makespan 32,457,336→32,931,912 (+1.462%). Reject this cut; result does not disprove cache-pressure direction. Conclusion: `experiments/phase2_problem1/round9_cutpoint_perturbation/round9_summary.md` | complete |
| v025 | Phase 2 P1 closeout | final-composition removal ablations and archival audit | none | 2 missing ablations × 400/400 P1 success; round6 and round2 reused after plan/fingerprint/output-hash checks; 7 variants audited; round8 retained at equal-weight mean speedup 1.94897594; exact round8-vs-round6 counts 23 improved/348 tied/29 regressed; artifact and raw-output audit passed. Cache pressure deferred, unverified. P2/P3 not run. Outputs: `experiments/phase2_problem1/final/` | complete |

## Rules for updating this file

- 每次实验结束后更新状态，不保留“正在进行”但没有下一步的记录。
- 新 best 必须记录版本、参数、结果文件位置和合法率。
- 失败实验必须写入 Failed ideas，避免重复搜索。
- 只记录可复现的数值；未知值使用 `TBD`，不猜测。

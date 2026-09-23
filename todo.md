# TODO

## Current status

- phase: Phase 2B Problem 1 Adaptive / Local Refinement
- state: not_started
- best_algorithm: communication_cut_plus_dependency_list_cube_vector_pipe_critical_path_priority
- best_version: p1_cube_vector_pipe_priority_round8_v001
- best_role: current verified P1 best / pre-local-search best / Phase 2B initial solution
- last_experiment: v025_phase2_p1_final_ablation_closeout
- next_step: 冻结 round8 初始解和各组规则/预算；第一组 lifetime/peak-pressure 诊断 + bounded reorder，第二组 M/V/DDR 多维负载 + move/swap 独立对照，第三组仅在仍有 partition 瓶颈证据时 bounded merge/split。本轮仅更新规则与计划，未运行新 evaluator。

## 各阶段归档与精简状态

本表按重构后的子阶段维护；历史实验和精简审计仍然有效。只有 `complete` 且归档核验为 `verified` 的阶段具备进一步精简资格，重构阶段名不代表恢复已清理的历史运行目录。

| 阶段 | 实验状态 | 归档核验 | 归档位置 | 说明 |
|---|---|---|---|---|
| Phase 0 | complete | pending：尚未做精简前核验 | `experiments/phase0/` | 未登记精简；核验前不清理 |
| Phase 1 | complete | verified：`experiments/phase1_baseline/v001/TRACE_ARCHIVE_AUDIT.md` | `experiments/phase1_baseline/v001/` | 已清理 1,279 个非关键 Trace；保留 21 个代表 Trace |
| Phase 2A P1 pre-local-search | complete | verified：final closeout + `ROUND_ARCHIVE_COMPACTION.md` + `ROUND8_RESTORATION_AUDIT.md` | `experiments/phase2_problem1/final/` + `round8_cube_vector_pipe_full/` | 历史 closeout 继续有效；作为 Phase 2B 初始解与对照 |
| Phase 2B P1 Adaptive Refinement | not_started | not_applicable | `TBD` | 先压力诊断/reorder，再多维负载/move/swap，最后条件性 merge/split；尚未执行 |
| Phase 2C P1 final freeze | not_started | not_applicable | `TBD` | 仅在 2B 结束后执行最终消融/冻结 |
| Phase 3A～3D P2 | not_started | not_applicable | `TBD` | Scene B warm start → reuse/lifetime → adaptive → ablation/freeze |
| Phase 4A～4D P3 | not_started | not_applicable | `TBD` | L2 baseline → reuse-distance/双带宽 → adaptive → ablation/freeze |
| Phase 5 Final | not_started | not_applicable | `TBD` | 三问冻结后只做最终复核和论文输出 |

- [x] P1 Phase 2A 收尾完成后核验归档与复现依据；生成 Trace 精简清单并逐项校验 SHA-256 后清理，释放 11,175,816,124 B；保留汇总、方案、结果及 9 个代表 Trace。核验记录：`experiments/phase2_problem1/final/TRACE_ARCHIVE_AUDIT.md`
- [x] 按用户要求精简 Phase 2A 历史中间轮次 case 目录；保留 pre-local-search archive 与 round8 best full。round8 恢复审计 400/400 成功且 Makespan 与历史逐项一致。净减少 21,038,867,101 B。审计：`experiments/phase2_problem1/final/ROUND_ARCHIVE_COMPACTION.md`、`ROUND8_RESTORATION_AUDIT.md`

## Current best

- current_p1_version: p1_cube_vector_pipe_priority_round8_v001
- current_p1_role: current verified P1 best / pre-local-search best / Phase 2B initial solution
- current_p1_equal_weight_mean_speedup_2_to_5: 1.948976
- current_p1_legal_rate: 100% (400/400 P1 records successful)
- current_p1_artifacts: `experiments/phase2_problem1/round8_cube_vector_pipe_full/`
- caveat: 相对 round6 为边际 best；23 项改善、348 项持平、29 项退化，最差 Makespan +4.006%
- phase2a_closeout_archive: `experiments/phase2_problem1/final/`（历史结果仍有效；现定义为 pre-local-search closeout）
- phase2a_closeout_audit: 7 个对照各 400/400 成功；原始 plan/input/config/evaluator/output 哈希核验通过；21 个单元测试通过
- cache_pressure: 暂缓、未系统验证；round9 单切点负结果不能外推为 cache-aware split/merge 无效
- current_p2_status: not_started；Phase 1 P2 speedup 仅作为 baseline reference，不登记为优化后 final best
- current_p3_status: not_started；Phase 1 P3 speedup 仅作为 baseline reference，不登记为优化后 final best

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

## Phase 2A 已完成历史：P1 启发式构造与收尾

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

## Phase 2A 已完成 closeout 清单

- [x] 根据 round9 负结果确定收尾范围：保留当前 best，缓存方向暂缓，不启动新优化搜索
- [x] 核对最终模块与冻结参数，建立模块移除/模块组消融矩阵，区分历史增量实验与最终组合移除消融
- [x] 按指纹、方案摘要及输出哈希复用 round6/round2；只补两项定义明确的缺失消融，各 100 cases × 4 核 P1，未调参
- [x] 按既定 Best 规则核定最终统一算法为 round8；保留 round8/round6 和全部负结果，不按 case 拼接
- [x] 在 `experiments/phase2_problem1/final/` 归档算法说明、复现入口、方案索引/指纹、逐例结果、分核汇总及 1～5 核加速比曲线
- [x] 汇总消融、改善/持平/退化、搬运/spill、生成与评估耗时；历史复用记录时间与新调用分别保留，不把耗时和墙钟混淆
- [x] 核查复现脚本及原始结果一致性；审计通过后标记 Phase 2 complete；写明 P2 场景 B 起点比较计划，本轮未执行 P2/P3

## Phase 2B：P1 Adaptive / Local Refinement 待办

- [ ] 锁定 round8 为 Phase 2B 初始解，记录 input/config/evaluator/plan fingerprint；不覆盖 Phase 2A 历史归档
- [ ] 明确本阶段只调用 Problem 1 / Scene A evaluator；P2/P3 evaluator 调用数保持 0
- [ ] 在看候选结果前冻结最大轮数、每轮候选数、evaluator-call 上限、单 case 时间预算、随机种子（如有）和 deterministic tie-break
- [ ] 实现/核对通用候选合法性检查：节点覆盖、sgid 唯一、收缩 DAG、core schedule 唯一与依赖顺序
- [ ] 建立 P1 bottleneck diagnosis：critical core、core finish/负载不均、partition-added、spill-added、总 added-copy、关键路径、PIPE_M/V、L1/UB pressure proxy、DDR contention proxy
- [ ] 第一组：建立 Task 内 tensor lifetime / L1/UB peak-pressure proxy；与 evaluator 指标区分，核对可控方案变化的作用路径
- [ ] 第一组：固定 partition/core assignment 实现 bounded reorder，独立记录 Makespan / spill / added-copy 及依赖等待、DDR 并发变化；P1 Task 间清缓存，重排不直接改变 Task 内拓扑序，不预设减少 spill
- [ ] 第二组：以同一 round8 为对照，独立测试 M/V/DDR 多维负载与 move；L1/UB pressure 作为风险特征，不把第一组组合收益归因于本组
- [ ] 第二组：按预先冻结的触发规则测试 swap，记录接受/拒绝原因与 evaluator 调用数；如与第一组组合，另做消融
- [ ] 第三组进入检查：前两组后仍存在 partition 瓶颈，记录强通信边界/Task 内 spill/超大子图等证据；无依据不启用 merge/split
- [ ] 第三组：bounded split 只测有限合法切点；bounded merge 检查 DAG、容量与并行损失；分账记录 partition-added / spill-added / Makespan
- [ ] 第三组候选：原子计算单元/locality-preserving unit，与已失败的纯 strong-edge aggregation 区分，先独立 diagnosis 不预设有效
- [ ] 容量系数候选独立验证：阈值集合实验前冻结，proxy 不冒充 evaluator 真峰值，不与多个新模块首次同时引入
- [ ] 按预先规则最多冻结两个 Phase 2B 候选进入原 validation 集合；validation 后不得改规则/参数
- [ ] validation 成立后运行 100 cases × 2/3/4/5 cores P1 全量；局部搜索新方案必须重新 evaluator
- [ ] 汇总每个邻域：候选数、接受数、平均/最大改进、失败/超时、evaluator-call 数、搜索 wall time
- [ ] 按既有 equal-weight mean speedup Best rule 判断是否替换 round8；禁止手工拼 case/local best

## Phase 2C：P1 最终消融、冻结与归档 待办

- [ ] 若 Adaptive 被采用，保留已有 Phase 2A removal ablation，并新增 `with adaptive` vs `without adaptive` 消融
- [ ] 若多维负载、capacity safety 等进入最终算法，对每个实际采用模块补定义清楚的 removal ablation
- [ ] 若 Phase 2B 未改进统一算法，将 Adaptive/Local Search 作为负结果归档，不重跑已有 round8 消融
- [ ] 最终冻结 P1，生成新版 100×4 逐例、1～5 核 speedup 曲线、added-copy/spill 分账、搜索开销、失败记录和复现入口
- [ ] Phase 2C 完成后再启动 P2；P1 未最终冻结前不得把临时候选当作 P2 唯一 warm start

## Phase 3：Problem 2 / Scene B 待办

### Phase 3A：P1→P2 warm start 与 Scene-B 基线

- [ ] 用官方 P2 evaluator 对共享 Phase 1 baseline 与最终冻结 P1 best 做同一 100 cases × 4 cores 对比
- [ ] 分别保存两个 P2 起点，按 P2 指标选择 warm start；不默认 P1 winner 在 P2 仍胜
- [ ] 建立 P2 tensor ledger：同核保留、跨核 COPY、500-cycle 同步、partition-added、spill-added
- [ ] 用合成小图核对 Scene-B 同核复用与跨核通信账本
- [ ] 固定 P2 diagnosis/validation 集合及选择依据

### Phase 3B：Scene-B-aware 结构优化

- [ ] 建模有方向 producer→consumer affinity：同核 reuse bytes / 跨核 COPY+同步收益与并行损失分开记录
- [ ] 强化合并 Task 的 L1/UB active tensor set / tensor lifetime 模型；核对 core_schedules 经 `_prioritize_task_seq` 与 Step2/3 后的实际顺序、峰值及 spill，proxy 与实际指标分开
- [ ] 定义 release potential 候选：执行后可释放字节/未来使用距离；与 critical-path priority 单独对照
- [ ] 测试 Scene-B 多维分核：estimated finish + reuse + cross-core bytes + PIPE_M/V + L1/UB pressure
- [ ] 测试 capacity safety factor，防止为追求同核 reuse 导致过度驻留和 spill
- [ ] 每个新模块先 diagnosis，筛选后冻结再 validation，不一次首次引入多个主要因素

### Phase 3C：P2 Adaptive / Local Refinement

- [ ] 跨核 COPY/同步高时测试 move 或与重新分核组合的 merge 使强依赖同核；同核 merge 不自动减少 COPY
- [ ] 负载不均时测试 move/swap
- [ ] L1/UB resident pressure 或 spill 高时先测试合法 reorder；split 仅在能改变合并 Task 内顺序或配合重新分核时测试，不创建新同核 Task、不自动清缓存、不消除同核 COPY
- [ ] reuse 收益高但并行损失大时测试 move/swap 折中
- [ ] 冻结 P2 邻域顺序、预算和接受规则后执行 diagnosis → validation → 100×4 full

### Phase 3D：P2 消融、冻结与归档

- [ ] 对进入最终 P2 算法的 affinity/reuse、lifetime/release-potential、capacity pressure、adaptive refinement 做 removal ablation
- [ ] 冻结 P2 final，输出 1～5 核 speedup、逐 case Makespan/added-copy/spill、搜索开销和复现入口

## Phase 4：Problem 3 / Scene B + 共享 L2 待办

### Phase 4A：P2→P3 baseline

- [ ] 固定 P2 final，在相同 case×core 下得到 no-L2(P2) 与 read-only-L2(P3) 成对结果
- [ ] 报告 Makespan、added-copy、Cache hit bytes/eligible bytes 和字节口径 hit rate；核对 evaluator 字段
- [ ] 选取共享输入多、DDR 密集、不同 reuse/hit 特征的 diagnosis 样本

### Phase 4B：L2-aware 建模与调度

- [ ] 建立 shared-input affinity，统计多核重复 COPY_IN 的逻辑 tensor 与可复用字节
- [ ] 建立 FIFO reuse-distance / 生存距离 proxy：两次访问之间进入 Cache 的其他 tensor 累计字节；用 evaluator hit/miss 校准
- [ ] 建立 DDR/L2 dual-bandwidth pressure proxy，分别估计 miss→DDR 与 hit→Cache 带宽竞争
- [ ] 测试 wave-aligned reorder/assignment 候选，使共享输入访问在依赖允许时更接近；先 diagnosis，不预设有效
- [ ] 联合约束 L2 reuse、L1/UB pressure 与多核并行；禁止只以 Cache hit rate 替代 Makespan

### Phase 4C：P3 Adaptive / Local Refinement

- [ ] hit 低且共享输入明显：测试 move/merge/shared-input affinity/wave-aligned reorder
- [ ] DDR 压力高：优先减少 miss 和重复读取
- [ ] Cache 带宽热点：避免过度同时命中造成新的 L2 带宽竞争
- [ ] L1/UB spill 高：先测试合法 reorder；沿用 P2 split/merge 边界，说明顺序变化或重新分核如何影响生命周期/spill，不能假定拆分清缓存
- [ ] 冻结规则与预算后执行 diagnosis → validation → 100×4 full，记录 evaluator-call 与搜索时间

### Phase 4D：P3 消融、冻结与归档

- [ ] 对进入 final 的 reuse-distance、dual-bandwidth、shared-input affinity、wave alignment、adaptive refinement 做 removal ablation
- [ ] 冻结 P3 final；生成相同核数 no-L2 vs L2 曲线、`T_noL2/T_L2`、逐 case Makespan/added-copy/Cache hit rate

## Phase 5：Final Evaluation & Paper Outputs 待办

- [ ] 确认 P1/P2/P3 算法与参数全部冻结；本阶段禁止搜索和调参
- [ ] 最终复核 100 cases × 2/3/4/5 cores 三问所需结果与合法率
- [ ] 生成 P1/P2 1～5 核平均 speedup 曲线
- [ ] 生成 P3 no-L2 vs read-only-L2 同核数曲线及 L2 相对加速比
- [ ] 汇总 Makespan、added-copy、partition/spill、P3 Cache hit、生成/搜索/evaluator 时间、失败/超时
- [ ] 生成三问最终算法流程图、消融总表、负结果表、逐 case 附录与复现命令

## 计划重构说明

- [x] 原独立 Phase 5 Local/Adaptive Search 已拆回 P1/P2/P3 各自阶段
- [x] 原独立 Phase 6 Ablation 已拆回各问题最终冻结前；新的 Phase 5 只负责 final evaluation / paper outputs
- [x] 将当前参考方案中“原子计算单元、多维装箱、容量安全、release potential、非对称 affinity、reuse distance、双带宽、wave alignment”等作为**待验证候选模型**加入对应问题；不把这些名称写成 CANN 官方算法名
- [x] 本轮只修改 `plan.md` 与 `todo.md`，未运行 evaluator，未新增 experiment version，未知结果保持 TBD/未执行

## 2026-09-23 CANN/GE 借鉴边界修订

- [x] 同步修改 `agent.md`、`plan.md`、`todo.md`，统一为“受 CANN/GE 机制启发的赛题数学抽象与候选启发式”；没有算法定义及实现对应证据不称复现
- [x] 明确借鉴 Fusion 局部性，不修改 op cycles、不做真实 kernel tiling、不假定 UB Fusion 指令级收益；不实现提交接口外的内存地址分配器
- [x] 明确 P2/P3 split 不新建同核 Task、不清缓存；收益须经合法顺序变化或重新分核影响生命周期、spill、通信，并由 evaluator 验证
- [x] 将 P1 Phase 2B 调整为三组实验优先级；补充 P1 固定 partition 的 Task reorder 不直接改变 Task 内生命周期的限制
- [x] 核对专用 `SKILL.md` 第 40 行的 CANNBot 来源，限定为图分析工作流；在 `plan.md` 登记官方 GE/Topo 参考资料与赛题接口映射
- [x] 本轮仅文档修订：未修改算法或 official 文件，未运行 evaluator，未新增实验版本；Phase 2B 保持 not_started，round8 best 与历史实验数值不变

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

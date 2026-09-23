# TODO

## Current status

- phase: Phase 1 共享 baseline
- state: complete
- best_algorithm: topology_contiguous_64_greedy_cycles
- best_version: shared_topology_contiguous64_greedy_cycles_v001
- last_experiment: v006_phase1_v001_full_benchmark

## Current best

- problem_1_mean_speedup_across_2_to_5_core_group_means: 1.131712
- problem_2_mean_speedup_across_2_to_5_core_group_means: 1.702996
- problem_3_mean_speedup_across_2_to_5_core_group_means: 1.716313
- legal_rate: 100% (1200/1200 multicore evaluator runs succeeded)
- runtime_per_case: see per-case evaluator and generation timings in `experiments/phase1_baseline/v001/reports/per_case.csv`

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

## Phase 1+ 优化待办

- [ ] 测试 critical-path priority
- [ ] 测试 communication-weighted merge
- [ ] 测试 cache-aware merge/split
- [ ] 测试 move/swap/reorder 局部搜索
- [ ] 完成消融实验
- [ ] 完整运行 100 cases × 2～5 cores × 3 problems

## Failed ideas

- 暂无

## Experiment log

| version | phase | scope | seed | result | status |
|---|---|---|---:|---|---|
| v001 | Phase 0 | 100 cases graph profile; outputs in `experiments/phase0/graph-profile-v1/` | 0 | 100/100 parsed; no evaluator metrics collected | complete |
| v002 | Phase 0 | Commit official baseline and enable pre-commit integrity guard | 0 | 114 official files verified; raw case files excluded from Git and hash-protected | complete |
| v003 | Phase 0 | Move official files under `official/`; reserve `src/` for scheduler; move graph profile under `experiments/phase0/` | 0 | Path references and integrity guard updated; evaluator loop not yet run | complete |
| v004 | Phase 0 | `case_019` (766 ops; stub plan: 647 compute ops, 10 subgraphs, 4 cores); single-core + problems 1–3 | 0 | All four evaluator runs exited 0; output fields, JSON/log/Trace paths and official hashes verified; one-case smoke only, not benchmark baseline | complete |
| v005 | Phase 1 | 5 representative cases; single-core + 2/3/4/5 cores × P1/P2/P3 | none | 65/65 evaluator runs succeeded; 5 synthetic tests passed; deterministic plan and metrics pipeline validated. Outputs in `experiments/phase1_baseline/v001/` | complete |
| v006 | Phase 1 | 100 formal cases; single-core + 2/3/4/5 cores × P1/P2/P3 | none | 100/100 single-core and 1200/1200 multicore runs succeeded; 1300 per-case rows, 12 fully successful groups, initial bests and bottleneck analysis generated; final official integrity check passed for 114 files | complete |

## Rules for updating this file

- 每次实验结束后更新状态，不保留“正在进行”但没有下一步的记录。
- 新 best 必须记录版本、参数、结果文件位置和合法率。
- 失败实验必须写入 Failed ideas，避免重复搜索。
- 只记录可复现的数值；未知值使用 `TBD`，不猜测。

# TODO

## Current status

- phase: Phase 0 环境与接口确认
- state: in_progress
- best_algorithm: 未建立
- best_version: 未建立
- last_experiment: v001_case_graph_profile

## Current best

- problem_1_avg_makespan: TBD
- problem_2_avg_makespan: TBD
- problem_3_avg_makespan: TBD
- avg_speedup_2_to_5_cores: TBD
- legal_rate: TBD
- runtime_per_case: TBD

## Pending

- [x] 检查 100 个正式 case 是否均能被读取
- [x] 建立官方文件 Git 基线并启用提交保护钩子
- [ ] 运行最小图和 stub 方案，确认评估接口
- [ ] 运行 `singlecore_evaluate.py` 建立单核基线
- [ ] 实现并记录 Phase 1 baseline
- [ ] 建立问题 1～3 的批量结果汇总
- [x] 选择代表性 case 并生成 case profile
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
| v001 | Phase 0 | 100 cases graph profile; outputs in `experiments/graph-profile-v1/` | 0 | 100/100 parsed; no evaluator metrics collected | complete |
| v002 | Phase 0 | Commit official baseline and enable pre-commit integrity guard | 0 | 114 official files verified; raw case files excluded from Git and hash-protected | complete |

## Rules for updating this file

- 每次实验结束后更新状态，不保留“正在进行”但没有下一步的记录。
- 新 best 必须记录版本、参数、结果文件位置和合法率。
- 失败实验必须写入 Failed ideas，避免重复搜索。
- 只记录可复现的数值；未知值使用 `TBD`，不猜测。

# 多核 NPU 调度研究计划

## 目标

针对题目给出的 100 个正式计算图，在固定 `data/config.txt` 和官方 evaluator 下，设计统一的多核切图与调度算法。

主目标：最小化问题 1～3 在 2～5 核配置下的总体 Makespan。

次目标：提高平均 speedup，降低 `added_copy_bytes`，在问题 3 中提高有效 Cache 命中率，同时保证单 case 搜索时间可控。

约束：所有输出必须通过官方合法性检查；不得修改 evaluator、原始 case 和 `data/config.txt`；不得针对正式用例硬编码答案。

## 固定评价协议

- 正式用例：`data/case_001.json` ～ `data/case_100.json`
- 核数：2、3、4、5；单核基线由 `code/singlecore_evaluate.py` 计算。
- 评估器：
  - `code/multicore_cut_evaluate_problem_1.py`
  - `code/multicore_cut_evaluate_problem_2.py`
  - `code/multicore_cut_evaluate_problem_3.py`
- 配置：始终使用 `data/config.txt`。
- 方案格式：`node_to_subgraph` + `core_schedules`。
- 每个阶段必须报告：合法率、Makespan、speedup、额外搬运量、失败/超时数量和运行时间。
- 采用固定随机种子；若使用随机搜索，种子必须写入实验记录。

## 研究阶段

### Phase 0：环境与接口确认

确认 100 个 case、配置、评估器、single-core 基线、方案格式和结果字段。先用 `.codex/skills/ap-multicore-scheduling/scripts/analyze_cases.py` 汇总正式图结构特征，再用最小图及少量 case 验证完整闭环。图分析估算不能替代 evaluator 的 spill、Cache 或 Makespan 指标。

### Phase 1：Baseline

实现确定性的拓扑切图和 greedy load balance baseline。先保证所有 case 能输出合法方案，并建立问题 1～3 的基准表。

### Phase 2：Graph-aware

加入关键路径长度、后继工作量、跨子图通信权重、输入复用度和 Cube/Vector 工作量等特征。重点优化切图和核心负载平衡。

### Phase 3：Cache-aware

加入 L1/UB 压力、张量驻留时间、spill 风险、输入复用和同核复用收益。问题 2/3 优先考虑同核聚合，避免因过度合并导致缓存换入换出。

### Phase 4：Local search

在合法方案上进行局部搜索，按成本和收益逐步启用：move、swap、merge、split、reorder。每个邻域都要记录接受规则、迭代次数、改进幅度和失败原因。

### Phase 5：Adaptive search

根据瓶颈自动选择邻域：DDR 拥塞时减少跨 Task 通信；负载不均时 move/swap；spill 增多时 split/reorder；Cache 命中率低时聚合共享输入。

### Phase 6：Ablation 与最终实验

逐项关闭 critical path、通信权重、cache pressure、局部搜索等模块，验证真实贡献。最后冻结算法和参数，完整运行 100 个 case、4 种核数和 3 个问题，生成论文所需表格和曲线。

## 实验闭环

每次实验必须遵循：提出假设 → 选择代表性 case → 生成方案 → 官方 evaluator 校验 → 解析指标 → 批量验证 → 与 best 比较 → 保存结果 → 更新 `todo.md`。

代表性 case 至少覆盖：小图、大图、DDR 搬运密集、分支汇聚多、L1/UB 压力高、共享输入多和历史退化 case。

## Best 选择规则

1. 合法率为硬门槛，非法方案不参与性能比较。
2. 在合法率相同且均为 100% 时，优先比较平均 Makespan。
3. 平均 Makespan 接近时，依次比较最差 case、平均 speedup、额外搬运量和运行时间。
4. 新算法若只改善单个 case 而拉低整体结果，不替换全局 best，但可保存为 case/local best。

## 停止条件

满足任一条件即可结束当前阶段：

- 连续两轮完整批量实验没有显著改善；
- 已完成该阶段预定的消融实验；
- 达到预设运行预算或单 case 时间上限；
- 所有正式 case 均合法，结果已保存且可复现。

停止后必须更新 `todo.md`，说明当前 best、已验证结论、未解决瓶颈和下一阶段入口。

# 多核 NPU 调度研究计划

## 目标

针对题目给出的 100 个正式计算图，在固定 `official/data/config.txt` 和官方 evaluator 下，设计共享的多核切图与调度框架，并针对问题 1、2、3 的不同硬件场景分别生成和优化调度方案。三问共享图分析、方案表示和搜索框架，但分别维护 best solution，不假设同一份 `multicore_res.json` 对三个问题同时最优。

主目标：分别最小化问题 1、2、3 在 2～5 核配置下的总体 Makespan。

次目标：提高平均 speedup，降低 `added_copy_bytes`，在问题 3 中提高有效 Cache 命中率，同时保证单 case 搜索时间可控。

约束：所有输出必须通过官方合法性检查；不得修改 evaluator、原始 case 和 `official/data/config.txt`；不得针对正式用例硬编码答案。

## 固定评价协议

- 正式用例：`official/data/case_001.json` ～ `official/data/case_100.json`
- 核数：2、3、4、5；单核基线由 `official/code/singlecore_evaluate.py` 计算。
- 评估器：
  - `official/code/multicore_cut_evaluate_problem_1.py`
  - `official/code/multicore_cut_evaluate_problem_2.py`
  - `official/code/multicore_cut_evaluate_problem_3.py`
- 配置：始终使用 `official/data/config.txt`。
- 方案格式：`node_to_subgraph` + `core_schedules`。
- 每个阶段必须报告：合法率、Makespan、speedup、额外搬运量、失败/超时数量和运行时间。
- 采用固定随机种子；若使用随机搜索，种子必须写入实验记录。

## 研究阶段

### Phase 0：环境与接口确认（只验证，不优化）

允许同一份 stub / baseline 方案依次跑 P1/P2/P3，目的仅为验证接口闭环。确认 `official/data/` 中 100 个 case、配置、评估器、single-core 基线、方案格式和结果字段。先用 `.codex/skills/ap-multicore-scheduling/scripts/analyze_cases.py` 汇总正式图结构特征，再用最小图及少量 case 验证完整闭环。图分析估算不能替代 evaluator 的 spill、Cache 或 Makespan 指标。

Phase 0 禁止：

- 自动修改调度策略；
- 自动搜索 merge/split/move/swap/reorder；
- 根据 Makespan 自主进行算法优化。

### Phase 1：共享 baseline

#### 算法 v001（冻结规则）

1. 将完整计算图依赖转换为 op DAG：保留 op→tensor→op、经过 `COPY_IN`/`COPY_OUT` 的依赖，以及直接 op→op 边；对全部 op 做确定性 Kahn 拓扑排序，就绪节点按 op ID 升序选择，随后滤除 `COPY_IN`/`COPY_OUT`。
2. 按拓扑序将计算 op 连续切块，每块固定 64 个计算 op，尾块可不足 64。实现暴露 `subgraph_size` 参数，但 v001 固定为 64，不扫参。
3. 子图工作量为其中 op 的 `sum(cycles)`，仅用于分配。按子图拓扑序依次分配给当前累计工作量最小的核，并列选择核 ID 最小者；该核的 schedule 按追加顺序排列。
4. 输出官方方案字段 `node_to_subgraph` 和 `core_schedules`；支持 2、3、4、5 核。方案合法性最终由三个官方 evaluator 判定。

不加入关键路径、通信、缓存感知、局部搜索、自动调参或 case-specific 规则。Cycle 工作量不是 Makespan 估计；不要求每个 case 优于单核。

#### 交付物

- `src/` 中拆分实现图读取、op 依赖构造/拓扑排序、连续切图、greedy 核分配、方案输出。
- `scripts/run_case.py` 单 case 闭环；`scripts/run_benchmark.py` 全量运行、匹配指纹的成功断点续跑和失败记录；汇总工具输出逐项表、12 组统计和分析。
- `experiments/phase1_baseline/v001/` 保存冻结参数/配置标识、方案、单核和多核原始结果、命令、耗时、退出状态、日志、Trace、失败记录、CSV 与报告。每个 benchmark 阶段批次开始和结束各做一次官方完整性校验；批次未通过后校验的记录不得计为成功。

#### Phase 1 完成条件（全部满足）

- 确定性 baseline 通过链式、分支汇聚、独立分支合成图测试；同输入重复生成完全一致。
- 正式 case 的单核评估 100/100 成功。
- 100 cases × 4 核数 × 3 problems 共 1200 项均通过对应官方 evaluator，合法率 100%，没有失败或超时。
- 逐项结果、12 组统计、三问独立的 case/core best 登记、失败/退化分析、命令和算法/输入/配置指纹齐全且可复现。
- `official/` 完整性检查在单核批次和多核批次开始、结束时均通过。

任一条件未满足时保持 Phase 1 `in_progress`，明确列出未完成项；本阶段完成后停止，不自动进入 Phase 2。

### Phase 2：Problem 1 优化

在共享 baseline 和框架上，针对 Problem 1 加入 DAG、并行度、DDR 通信、关键路径长度、后继工作量和 Cube/Vector 工作量等特征，重点优化切图和核心负载平衡。

### Phase 3：Problem 2 优化

以 P1 思路和结果作为 warm start，加入同核复用、L1/UB 压力、张量驻留时间、spill 风险和输入复用收益，避免因过度合并导致缓存换入换出。

### Phase 4：Problem 3 优化

以 P2 思路和结果作为 warm start，加入 L2 Cache 感知、共享输入复用和缓存容量约束，独立维护 Problem 3 的 best solution。

### Phase 5：Local / Adaptive search

在合法方案上进行局部搜索，按成本和收益逐步启用：move、swap、merge、split、reorder。每个邻域都要记录接受规则、迭代次数、改进幅度和失败原因。

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

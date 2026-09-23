# 多核 NPU 调度研究计划

## 目标

针对题目给出的 100 个正式计算图，在固定 `official/data/config.txt` 和官方 evaluator 下，设计共享的多核切图与调度框架，并针对问题 1、2、3 的不同硬件场景分别生成和优化调度方案。三问共享图分析、方案表示和搜索框架，但分别维护 best solution，不假设同一份 `multicore_res.json` 对三个问题同时最优。

主目标：分别最小化问题 1、2、3 在 2～5 核配置下的总体 Makespan。

算法级比较采用下文 Best 选择规则中的平均 speedup 协议；平均 Makespan 同时报告。次目标：降低 `added_copy_bytes`，在问题 3 中提高有效 Cache 命中率，同时保证单 case 搜索时间可控。

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

本阶段仅评估 P1，与 P1 v001 和 P1 前一对照版本比较；不重跑 P2/P3，不用跨问题成绩选择 P1 best。首轮执行结果诊断、样本分组、通信账本和粒度对照，完成后记录结论，再进入后续模块。

#### 分步实施与对照

1. **已有结果诊断与通信账本。** 固定互不重叠的 10 个 diagnosis case 和 10 个 validation case，记录选择依据与名单。Diagnosis 覆盖退化严重、增加核心反而变慢、搬运量大、并行收益明显和不同规模，用于诊断和调参；validation 按规模与结构覆盖选取，候选算法与参数冻结后才运行。保留 tensor ID、生产者、消费者集合、大小、位置及 COPY 输入输出语义；按 Task 去重统计边界写出、读入和共享输入重复读取。先用小图核对账本，不改变调度算法；边界搬运估计与 evaluator 包含 spill 的总搬运量分开记录，复用收益不得重复计费。
2. **切图粒度对照。** 固定拓扑排序及 greedy 分核，比较 32/64/128/256 个计算操作的连续切块；64 的结果在指纹匹配时复用。验证减少边界与 Task 数是否值得牺牲并行空间，不预设块越大越好。
   随后单独增加相对粒度对照：目标子图数 `K=min(N_op,c×P)`，`c∈{2,4,8}`，P 为模拟核数；非空图按 `B=max(1,ceil(N_op/K))` 连续切块并记录实际子图数，空计算图按合法空方案处理。固定与相对粒度均为候选，不预设相对粒度更优；所有候选保持相同拓扑排序和分核策略。
3. **通信感知连续切图。** 保持拓扑序和分核规则不变，在有限候选位置选择低通信代价切点，并显式限制块规模。与 v001 及粒度对照中的固定块候选比较，区分通信感知收益与单纯增大块的收益。按累计 cycles 切分可作为独立对照，不与通信策略同时首次加入。
4. **依赖感知分核。** 固定选定切图，比较最小累计 cycles 分配与考虑前驱完成、同核 Task 切换、跨核等待的 list scheduling。对多个前驱取就绪约束的最大值，不将每条边的等待简单相加；预计完成时间只用于启发式选择，成绩由官方 evaluator 给出。
5. **DAG 结构感知切图。** 在连续切图和分核对照完成后，独立测试从单节点或小块出发的强边聚合/分支感知构造，研究全局拓扑序交错分支带来的限制。固定分核策略，只改变切图；每次候选合并保证收缩后的整个子图图仍为 DAG，单个区域的拓扑凸性不能替代全局检查。预先固定候选规则、规模限制和构造预算，不混入 evaluator 驱动的反复局部搜索。
6. **逐项加入高级特征。** 在已验证版本上，分别测试关键路径优先级、后继工作量、Cube/Vector 分 Pipe 工作量、缓存压力约束；每项独立开关并单独对照。拓扑关键路径、驻留峰值和 Pipe 重叠均为估计，不冒充真实执行时间或 spill；缓存软阈值须经实验支持。P1 前期仅将缓存压力作为大子图风险信号；复杂驻留/复用模型留给 Phase 3，evaluator 驱动的 merge/split/move 局部搜索留给 Phase 5。

#### 实验与阶段验收

- 每轮只改变一个主要因素，提前记录假设、参数、对照版本和预算；候选始终与冻结 v001 及直接前一对照版本比较。负收益模块不自动带入下一步，多模块组合后再做移除消融。
- 先对 diagnosis 运行 P1 的 2/3/4/5 核，筛选后冻结至多两个候选及参数，再运行 validation，最后进行每候选 100 cases × 4 核 = 400 项 P1 全量验证；匹配指纹的已完成项可复用。若依据 validation 结果修改算法或参数，记录其已参与开发，不再声称该组是未参与调参的验证集。全量 100 case 是正式 benchmark，包含开发样本，不称为独立测试集。无需重复未变化的单核参考。
- 分核数报告合法率、平均 Makespan、平均 speedup、相对 v001 的逐 case 改善/退化、最差退化、慢于单核数量、额外搬运量及生成耗时；全量选择遵循 Best 选择规则，不只展示有利 case。
- 方案必须检查节点覆盖、收缩后子图 DAG 和核心顺序，最终通过官方 evaluator；按 `agent.md` 执行完整性校验。结果另存 `experiments/phase2_problem1/`，不覆盖 Phase 1 v001。
- 本阶段不能仅因“所有 case 合法”而结束。结束时必须保存已尝试模块的正负结果与取舍、冻结的 P1 方案及全量对比、退化分析和 Phase 3 入口。若因预算提前停止，应明确未完成步骤，不宣称全部完成；未发现改进时保留 v001 为 best。

#### 当前收尾决策（round9 后）

- 暂停新增 P1 优化方向，进入消融与归档。round9 的 case_067×2 单切点扰动在固定 core_schedules 下使 spill 减少 80,000 B，但 Makespan 增加 1.462%，已拒绝。通用缓存压力感知切图标记为“暂缓、未验证”，不是已实现或已证明无效；不继续手工扫描该 case 的切点，不扩展缓存 validation/全量实验。
- 保留 round8 为当前数值 best，round6 为重要对照。准确报告 round8 对 round6 的 23 项改善、348 项持平、29 项退化，以及平均 speedup 仅约 +0.016%、最差 Makespan +4.006%，不称为普遍改善。
- 先建立消融矩阵：冻结最终参数，分别移除通信感知切点、依赖感知分核、关键路径优先级、Cube/Vector 工作量修正，写清替代规则及模块依赖。移除上游模块导致下游无从定义时，明确标成模块组消融；逐阶段增量对照不能冒充最终组合的单模块移除消融。
- 优先复用输入、配置、方案和 evaluator 指纹及输出哈希一致的已有记录（例如经核对的 round8 去掉 Pipe 修正对应 round6）。只补缺失的、定义明确的消融，每种冻结变体使用相同 100 cases × 4 核 P1 评估；不扫参，不重复已有有效结果。消融若产生更优合法完整变体，按既定 Best 规则登记，保留旧版本，不继续扩展搜索。
- 收尾输出到 `experiments/phase2_problem1/final/`：算法说明与复现入口、最终 best 方案索引及指纹、400 项逐例表、分核数汇总、1～5 核平均 speedup 曲线（1 核为 1）、增量与移除消融表、改善/持平/退化统计、搬运与 spill 分账、生成/评估耗时、负结果及暂缓项说明。保留历史实验的唯一结果和复现依据；阶段 complete 且归档核验通过后，按 `agent.md` 的“阶段归档与精简”规则处理非关键 Trace、重复副本和冗余日志。
- 完成上述收尾且最终选定算法 400/400 成功后，方可将 Phase 2 标记 complete；未解决的消融或复现缺口须列明并保持 in_progress。收尾结束即停止，不自动运行 P2/P3。

### Phase 3：Problem 2 优化

以 P1 思路和结果作为 warm start，加入同核复用、L1/UB 压力、张量驻留时间、spill 风险和输入复用收益，避免因过度合并导致缓存换入换出。

阶段启动时先在官方 P2 evaluator（场景 B）下比较共享 baseline 与冻结 P1 方案，分别记录 P2 成绩，再选择 P2 起点。不得沿用 P1 场景 A 的等待参数作为场景 B 规则，不默认 P1 best 同时是 P2 best；P1 收尾本身不启动这些评估。

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
2. 单个问题、case × core 的方案 best 选择最小 Makespan。算法级比较只在相同问题、case 集合、核数范围和固定配置下进行；全量 best 要求所有评估成功，不能排除失败项后比较均值。
3. 全局算法优先最大化逐 case speedup 的算术平均：`speedup=T_single/T_candidate`。每个核数单独统计 100 个 case；若选择覆盖 2～5 核的统一算法，四个核数的均值等权平均，同时完整报告各核数结果。小样本使用对应固定集合，只用于筛选，不替换全量 best。此为项目选择协议，不宣称是赛题唯一官方综合评分公式。
4. 平均 speedup 相同时，依次比较相对当前 best 的退化 case×core 数、最差相对 Makespan 退化、额外搬运量和生成耗时。若采用近似相等容差或额外退化门槛，必须在看候选结果前记录数值。平均 Makespan 继续报告，但不作为优先排序指标。
5. 新算法若只改善单个 case 而拉低总体平均 speedup，不替换全局 best，但可保存为 case/local best。不同核数的退化必须披露；case/local best 的组合成绩不能冒充某个统一算法的成绩。Phase 2 仅选择 P1 best，P2/P3 的既有 best 不变。

## 停止条件

满足任一条件即可结束当前阶段：

- 连续两轮完整批量实验没有显著改善；
- 已完成该阶段预定的消融实验；
- 达到预设运行预算或单 case 时间上限；
- 所有正式 case 均合法，结果已保存且可复现。

停止后必须更新 `todo.md`，说明当前 best、已验证结论、未解决瓶颈和下一阶段入口。

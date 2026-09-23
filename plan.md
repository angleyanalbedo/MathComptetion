# 多核 NPU 调度研究计划

## 目标

针对题目给出的 100 个正式计算图，在固定 `official/data/config.txt` 和官方 evaluator 下，设计共享的多核切图与调度框架，并针对问题 1、2、3 的不同硬件场景分别生成和优化调度方案。三问共享图分析、方案表示和搜索框架，但分别维护 best solution，不假设同一份 `multicore_res.json` 对三个问题同时最优。

主目标：分别最小化问题 1、2、3 在 2～5 核配置下的总体 Makespan。

算法级比较采用下文 Best 选择规则中的平均 speedup 协议；平均 Makespan 同时报告。次目标：降低 `added_copy_bytes`，在问题 3 中提高有效 Cache 命中率，同时保证单 case 搜索时间可控。

约束：所有输出必须通过官方合法性检查；不得修改 evaluator、原始 case 和 `official/data/config.txt`；不得针对正式用例硬编码答案。

## CANN/GE 参考来源与赛题映射

当前工作是部分思想落地与后续研究规划，统一表述为“受 CANN/GE 机制启发的赛题数学抽象与候选启发式”；除非有官方算法定义与逐项实现对应证据，不声称复现 GE 具体算法。

- [官方 ATC/GE 流程](https://www.hiascend.com/document/detail/en/canncommercial/800/devaids/atc/atlasatc_16_0005.html)说明图拆分、FE 子图优化/UB Fusion、重新合图和内存/流资源分配。本题只借鉴 Fusion 的局部性思想：提交接口为 `node_to_subgraph` 与 `core_schedules`，不能修改原始 op cycles、重新做真实 kernel tiling，不能把子图 merge 记作实现 CANN UB Fusion 或假定指令级收益。
- [官方内存复用与 Topo 优化说明](https://www.hiascend.com/developer/techArticles/202407005-1)支持生命周期分析与顺序优化方向。本题通过 partition、core assignment、subgraph order 提出候选，由 evaluator 插入 spill/reload 并处理内存复用，不实现接口无法表达的自定义地址分配器。
- 待验证链条为：方案变化 → 实际有效顺序/分核变化 → tensor lifetime/peak occupancy 变化 → evaluator spill/搬运变化 → Makespan 变化。各箭头均不是必然关系；同时保留 proxy 与实际结果，不能以容量代理改善宣布性能改善。
- `.codex/skills/ap-multicore-scheduling/SKILL.md` 第 40 行（本次核对）明确记录图分析器借鉴 CANNBot `model-recommend-analysis` 的图结构分析与优化建议方向；该来源仅说明分析工作流，不证明调度算法复现了 CANNBot 或 GE。

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
- `experiments/phase1_baseline/v001/` 保存冻结参数/配置标识、方案、单核和多核原始结果、命令、耗时、退出状态、日志、失败记录、CSV 与报告。所有 Trace 默认临时生成后清理，不因成功、失败或超时自动保留；仅显式选定需要时间线分析的 case 才保留 Trace。每个 benchmark 阶段批次开始和结束各做一次官方完整性校验；批次未通过后校验的记录不得计为成功。

#### Phase 1 完成条件（全部满足）

- 确定性 baseline 通过链式、分支汇聚、独立分支合成图测试；同输入重复生成完全一致。
- 正式 case 的单核评估 100/100 成功。
- 100 cases × 4 核数 × 3 problems 共 1200 项均通过对应官方 evaluator，合法率 100%，没有失败或超时。
- 逐项结果、12 组统计、三问独立的 case/core best 登记、失败/退化分析、命令和算法/输入/配置指纹齐全且可复现。
- `official/` 完整性检查在单核批次和多核批次开始、结束时均通过。

任一条件未满足时保持 Phase 1 `in_progress`，明确列出未完成项；本阶段完成后停止，不自动进入 Phase 2。

### Phase 2：Problem 1 优化（Scene A）

本阶段只维护 P1 best，并拆为“已完成的启发式构造 → Adaptive/Local Refinement → 最终消融与冻结”三部分。当前已验证 best 为 round8 `p1_cube_vector_pipe_priority_round8_v001`；它在 Phase 2B 启动时作为 **pre-local-search best / 初始解**，并不因为阶段重构而失效。

> **背景映射原则。** 可参考 CANN/Ascend 中图切分、算子/子图融合、多核 Tiling、片上存储容量、多 Pipe 并行和自动调优等机制来构造模型，但本计划中的“原子计算单元、亲和度、释放势能、波次对齐”等名称均视为本项目的候选数学抽象，不冒充 CANN 官方算法名。最终算法只以题目给定图、固定 `config.txt` 和官方 evaluator 的结果为准。

#### Phase 2A：P1 启发式构造与模块优化（已完成历史）

保留现有 round1～round9、round8 全量、最终 removal ablation、哈希审计与归档，不删除、不改写历史数值。`experiments/phase2_problem1/final/` 重新定义为 **Phase 2A pre-local-search closeout archive**；`round8_cube_vector_pipe_full/` 为 Phase 2B 的冻结初始方案来源。

已完成的主线仍为：

1. **已有结果诊断与通信账本。** 固定互不重叠的 diagnosis / validation 集合，按 tensor/Task 去重统计边界写出、读入、共享输入重复读取，并将 partition-added 与 evaluator spill 分账。
2. **切图粒度对照。** 比较固定 32/64/128/256 和相对粒度；最终证明单纯粒度并不足以替代通信感知。
3. **通信感知连续切图。** 在受限窗口内选择低边界通信切点，并限制块规模。
4. **依赖感知分核。** 使用前驱 release、核心可用时间和同/跨核等待的 list scheduling。
5. **DAG 强边/分支感知构造。** 已做 diagnosis 且产生明显退化，保留为负结果，不直接重复。
6. **高级优先级。** 已验证 critical path、successor work、Cube/Vector Pipe work；round8 仅以预先定义的平均 speedup 规则成为边际 best。
7. **缓存压力先导。** round9 单切点使 spill 降低但 Makespan 上升，仅否定该切点；通用 cache-pressure / capacity-aware 方法仍未系统验证。

Phase 2A 当前冻结事实：round8 equal-weight mean speedup 为历史记录中的已验证值；所有既有数值、400/400 合法性、23/348/29 改善/持平/退化和归档审计均保持原记录。

#### Phase 2B：P1 Adaptive / Local Refinement（待执行）

目标是在 round8 合法初始解上做**有限预算、确定性、可复现**的自适应局部改进，而不是重新进行无界全局搜索。正式全量前必须冻结邻域顺序、候选生成规则、接受规则、随机种子（若使用）、每轮候选上限、最大轮数、evaluator-call 预算和单 case 时间预算。

##### 2B-1. P1 多维瓶颈诊断

对每个 case×core 从当前方案提取以下 proxy/指标，用于选择邻域，不把 proxy 冒充真实 Makespan：

- critical core / 各核估计完成时间与负载不均；
- Task/subgraph 的总 cycles、`PIPE_M`、`PIPE_V` 工作量；
- partition-added copy、spill-added copy、总 `added_copy_bytes`；
- 关键路径及其附近子图；
- 大子图的 L1/UB 容量压力 proxy 与张量活跃区间；
- DDR 搬运集中程度/同时大 COPY 的轻量 contention proxy。

##### 2B-2. CANN/Ascend 背景启发的候选模型（先 diagnosis，后决定是否采用）

1. **原子计算单元 / locality-preserving unit。** 根据强生产者-消费者依赖、中间 tensor 大小、复用和合法 DAG 条件识别“不宜轻易切开”的局部单元。它不同于已失败的纯 strong-edge aggregation：必须同时受规模、并行度和容量风险约束。
2. **多维向量化负载模型。** 将 Task/subgraph 表示为例如 `(PIPE_M work, PIPE_V work, DDR bytes, L1 pressure, UB pressure)` 的资源向量，测试长任务优先或多维 bin-packing 式核分配是否优于仅基于完成时间的规则。首轮必须作为独立开关，不与其他新模块同时首次加入。
3. **容量安全系数。** 对 L1/UB pressure proxy 使用 `eta × capacity` 的软上限，`eta` 不预设为固定经验值；候选 `eta` 必须在 diagnosis 前定义有限集合，并经过 validation 冻结。不得声称 proxy 等于 evaluator 的真实峰值。

##### 2B-3. 有界局部邻域

按以下三组优先级逐组研究，首次不同时引入多个主要因素。每次修改后先做结构合法性检查，再调用 P1 evaluator：

1. **第一组：lifetime / peak-pressure proxy → bounded reorder。** 先诊断 Task 内张量活跃区间与 L1/UB 压力，再固定 partition/core assignment，只测试有限同核合法 Task 顺序，记录 Makespan、spill、added-copy 与等待/DDR 并发变化。P1 每子图独立成 Task，Task 间清缓存；因此这种 reorder 不直接改变 Task 内拓扑序，不预设可缩短 Task 内生命周期或减少 spill。须核对实际作用路径，未影响 spill 时如实记录，将跨子图生命周期优化重点留到 P2。
2. **第二组：M/V/DDR 多维负载 → move / swap。** 以 round8 为共同对照，独立验证多维负载与分核邻域；move 固定 partition 移动子图并重建合法顺序，swap 交换不同核心子图。不得先叠加第一组 winner 再把组合收益归因于本组；若组合采用，另做消融。L1/UB pressure 可作为风险特征，容量系数独立验证。
3. **第三组：partition 瓶颈 → bounded merge / split。** 仅当前两组后仍有强通信边界、超大子图或 Task 内 spill/容量压力等 partition 瓶颈证据时启用，并记录进入依据。split 只测试有限合法切点；merge 同时约束规模、容量与并行损失。每项检查收缩 DAG，并分账记录 partition-added、spill-added 与 Makespan；原子单元和容量系数不得未经独立验证一次混入。

搜索闭环：

`round8 initial → diagnose → choose neighborhood → generate bounded candidates → legality check → official P1 evaluator → accept/reject → iterate within frozen budget → stop`。

单个 case×core 的接受以 **Makespan 严格下降** 为第一准则；Makespan 完全相同时再比较 added-copy、spill 和生成耗时。算法级替换 P1 best 仍必须运行统一规则下的 100 cases × 2/3/4/5 cores，并按本计划 Best 选择规则决定；禁止手工拼接各 case 的 local best 冒充统一算法。允许确定性的 per-case adaptive algorithm，但其诊断、邻域选择和预算必须在正式全量前冻结。

##### 2B-4. 实验顺序与停止

先在既有固定 diagnosis 集合筛选；冻结至多两个候选后进入原 validation 集合；validation 后不再调参，成立后再做 100×4 P1 全量。匹配指纹的 round8 初始结果可复用，但局部搜索产生的新方案必须重新评估。

满足任一条件可停止 Phase 2B：连续两轮新邻域无有意义改善；达到 evaluator-call/时间预算；改善低于预设阈值；或计划邻域均已完成。停止时必须记录接受次数、拒绝原因、evaluator 调用数、搜索耗时和失败/超时。

#### Phase 2C：P1 最终消融、冻结与归档

只有 Phase 2B 结束后才最终冻结 P1。

- 若 Adaptive/Local Refinement 被采用：保留 Phase 2A 已有通信切图、dependency scheduler、critical path、Cube/Vector 的 removal ablation，不无谓重跑；新增至少一个 `final adaptive` vs `same pipeline without adaptive refinement` 的消融。若新增多维负载/容量安全模块进入最终算法，再分别做定义清楚的移除消融。
- 若 Phase 2B 没有产生更优统一算法：round8 继续作为最终 P1 best；将 Adaptive/Local Search 作为负结果归档，不重跑已有有效消融。
- 最终输出新的 P1 freeze 说明、100×4 全量结果、1～5 核平均 speedup 曲线、added-copy/spill 分账、搜索开销和复现入口，然后才进入 Phase 3。

### Phase 3：Problem 2 优化（Scene B）

P2 不只是替换 evaluator：同一核心上的全部子图合为一个 Task，同核数据可驻留 L1/UB，跨核依赖才经 DDR 并承担同步延迟。因此 P2 的核心权衡是 **同核复用收益 vs 多核并行收益 vs L1/UB 驻留/ spill 风险**。

**P2/P3 split/merge 作用边界：** 拆出新 sgid 不创建新的同核 Task，不自动清空 L1/UB，也不消除同核 COPY。收益必须来自改变同一合并 Task 内的合法执行顺序，或与重新分核组合后改变驻留生命周期、spill 与跨核通信。同核 merge 也不额外消除本来就不存在的边界 COPY。`official/code/multicore_cut_evaluate_problem_2.py` 的 `_prioritize_task_seq` 按子图顺序分桶并核查拓扑合法性，随后仍经 Step2/3；不能把提交的子图顺序等同于最终逐 op 执行时间线。P2 将重点强化合并 Task 的生命周期模型，并核对实际顺序、峰值和 spill。

#### Phase 3A：P1 → P2 warm start 与 Scene-B 基线

1. 在官方 P2 evaluator 下分别运行共享 Phase 1 baseline 与最终冻结 P1 方案，使用相同 100 cases、2/3/4/5 cores；分别保存，不能默认 P1 winner 自动转移为 P2 winner。
2. 建立 P2 tensor ledger：区分同核保留、跨核 COPY、500-cycle 同步、partition-added 与 spill-added；先用合成小图核对账本。
3. 固定 P2 diagnosis/validation 集合或明确复用 P1 集合的理由；未冻结前不得用 validation 调参。

#### Phase 3B：Scene-B-aware 结构优化

按独立模块逐项测试：

1. **同核复用 / 非对称 producer→consumer affinity。** 定义有方向的亲和度，衡量把前驱与后继放同核可节省的跨核 COPY 与同步；同时扣除负载失衡和容量风险。亲和度是项目模型，不称为 CANN 官方算法。
2. **活跃张量集合与生命周期模型。** 沿候选同核顺序维护 L1/UB active tensor set，估计每一步的驻留字节、峰值和 tensor lifetime，用作容量压力 proxy；最终 spill 仍以 evaluator 为准。
3. **释放势能排序。** 对 ready subgraph/局部块估计“执行后可释放的 L1/UB 字节”或下一次使用距离，与 critical-path / estimated finish 形成独立对照或有限组合，测试是否能缩短驻留时间并减少 spill。
4. **Scene-B-aware 多维分核。** 核分配同时考虑 estimated finish、同核 reuse bytes、cross-core bytes、`PIPE_M/PIPE_V` work 与 L1/UB pressure；先做单模块对照，避免一次引入过多自由参数。
5. **容量安全缩放。** 对长期驻留数据和子图内部压力分别建模，防止为追求 reuse 过度聚合；阈值必须通过 diagnosis→validation 冻结。

#### Phase 3C：P2 Adaptive / Local Refinement

复用统一的 move/swap/reorder/split/merge 框架，但触发规则改为 Scene B：

- 跨核 COPY 或同步代价高：优先 move，或与重新分核组合的 merge，使强 producer→consumer 依赖同核；
- critical core / 负载不均：move/swap；
- L1/UB 驻留压力、spill 高：先测试合法 reorder；仅当 split 能改变合并 Task 内顺序或配合重新分核时再测试，明确生命周期作用路径，不能假定拆分清缓存；
- reuse 高但并行度损失大：swap/move 做折中；
- 所有候选仍以 P2 official evaluator 的 Makespan 为最终接受依据。

采用与 P1 相同的“diagnosis → freeze → validation → full 100×4”协议和固定预算原则。

#### Phase 3D：P2 消融、冻结与归档

对最终 P2 算法至少区分：warm-start 基础、Scene-B affinity/reuse、lifetime/release-potential、capacity pressure、adaptive refinement 的真实贡献；只对进入最终算法的模块做正式 removal ablation。冻结后输出 P2 1～5 核平均 speedup、逐 case Makespan/added-copy、spill、搜索开销和完整复现入口。

### Phase 4：Problem 3 优化（Scene B + 共享只读 L2）

P3 以最终 P2 best 为 warm start，并严格按题目 evaluator 的 1 MB 只读 FIFO Cache、250 bytes/cycle Cache 带宽和独立 DDR 带宽池建模。CANN/Ascend 的 L2/数据复用机制只作为背景启发，不替代本题固定 Cache 规则。

#### Phase 4A：P2 → P3 warm start 与 no-L2/L2 基线

1. 固定最终 P2 方案，在相同 case×core 下分别记录 P2 no-L2 与 P3 read-only-L2 evaluator 结果，建立同核数直接对照。
2. 报告 Makespan、added-copy、Cache hit bytes / eligible read bytes（按 evaluator 实际字段口径）、Cache hit rate；禁止把访问次数命中率与字节命中率混淆。
3. 选择共享输入多、DDR 密集、命中率低/高、不同规模的 diagnosis 样本。

#### Phase 4B：L2-aware 建模与调度

按独立模块逐项测试：

1. **共享输入 affinity。** 识别多核重复 COPY_IN 的同一逻辑 tensor，把共享输入复用收益加入切图/分核/排序候选，但不以 hit rate 单独作为接受目标。
2. **Reuse distance / FIFO 生存距离 proxy。** 按逻辑 tensor id 和访问顺序估计两次访问之间进入 Cache 的其他 tensor 累计字节，构造与 1 MB FIFO 容量对应的 reuse-distance 特征；必须用 evaluator 实际 hit/miss 做校准，不能把 proxy 当作精确命中判定。
3. **DDR/L2 双带宽压力。** 分别估计 miss→DDR 和 hit→Cache 读带宽池的并发压力，避免只追求 hit rate 却制造新的 L2 带宽拥塞；最终时间仍由官方离散事件 evaluator 给出。
4. **波次对齐候选。** 对会访问相同共享输入的多个核心/子图，测试在不破坏依赖与负载平衡的前提下缩短其访问时间距离，以提高 FIFO 中再次命中的机会。“波次对齐”为本项目候选启发式，需先 diagnosis 验证，不预设有效。
5. **容量与并行联合约束。** L2 reuse、L1/UB pressure 和多核并行三者联合考虑；P3 不允许为了 Cache hit rate 牺牲总体 Makespan 后仍判为改进。

#### Phase 4C：P3 Adaptive / Local Refinement

复用有界邻域框架，并新增 L2 诊断：Cache hit bytes/rate、reuse distance、共享输入重复读取、DDR 与 Cache 带宽压力。

- hit 低且共享输入明显：优先测试 move/merge/shared-input affinity 聚合或 wave-aligned reorder；
- DDR 压力高：优先减少 miss 和重复读取；
- Cache 带宽成为热点：避免过度同时命中造成的 L2 带宽竞争；
- L1/UB spill 高：沿用 P2 作用边界，先测试合法 reorder；split 必须改变合并 Task 内顺序或配合重新分核，核对实际生命周期/spill，不假定产生新 Task 或清缓存；
- 任何候选只有在 P3 Makespan 的预定接受规则下才可进入下一轮。

同样执行 diagnosis → freeze → validation → 100×4 full，记录 evaluator-call 数与算法生成时间。

#### Phase 4D：P3 消融、冻结与归档

对进入最终算法的 L2-aware 模块做 removal ablation；最终必须同时给出相同核数下 no-L2 vs read-only-L2 曲线、`T_noL2/T_L2`、逐 case Makespan、added-copy、Cache hit rate/bytes、搜索时间与失败记录。

### Phase 5：Final Evaluation & Paper Outputs（只复核，不再调参）

只有 P1/P2/P3 都完成各自消融与冻结后才能进入。本阶段禁止新的算法搜索、阈值扫描、手工 case 修补或根据 final benchmark 结果回改规则。

统一生成：

- P1、P2 的 1～5 核平均 speedup 曲线；
- P3 同核数 no-L2 vs read-only-L2 对比曲线及 L2 相对加速比；
- 100 cases × 2/3/4/5 cores 的逐例 Makespan、added-copy、partition/spill 分账；
- P3 Cache 命中率/命中字节；
- 生成时间、局部搜索 evaluator-call 数、evaluator 时间、失败/超时；
- 三问最终算法流程图、消融总表、负结果表和复现命令；
- 论文正文所需表格/曲线与逐 case 附录。

## 实验闭环

每次新模块或局部搜索实验必须遵循：**提出假设 → 明确现实/硬件机制来源 → 定义数学 proxy → 选择固定 diagnosis → 冻结候选规则/预算 → 生成方案 → 结构合法性检查 → 官方 evaluator → 解析指标 → validation → 全量 → 与 best 比较 → 保存结果 → 更新 `todo.md`**。

代表性 case 至少覆盖：小图、大图、DDR 搬运密集、分支汇聚多、L1/UB 压力高、共享输入多、Cache reuse 特征不同和历史退化 case。任何来自 CANN/Ascend 背景的机制都必须重新映射到本题 evaluator；外部机制不能代替官方评估。

## Best 选择规则

1. 合法率为硬门槛，非法方案不参与性能比较。
2. 单个问题、case×core 的局部候选优先最小 Makespan；算法级比较只在相同问题、case 集合、核数范围和固定配置下进行。全量 best 要求所有规定评估成功，不能排除失败项后比较均值。
3. 统一算法优先最大化逐 case speedup 的算术平均：`speedup=T_single/T_candidate`。每个核数单独统计 100 case；若选择覆盖 2～5 核的统一算法，四个核数的均值等权平均，并完整报告各核数结果。小样本仅用于筛选。
4. 平均 speedup 相同时，依次比较相对当前 best 的退化 case×core 数、最差相对 Makespan 退化、额外搬运量和生成/搜索耗时。任何近似相等容差或退化门槛必须在看候选结果前记录。
5. Phase 2 只维护 P1 best，Phase 3 只维护 P2 best，Phase 4 只维护 P3 best；不同 evaluator 的成绩不得相互替代。
6. per-case adaptive algorithm 可以依据输入图与当前方案的可计算特征选择邻域，但诊断规则、候选生成、接受规则和预算必须在正式全量前冻结。禁止查看正式 benchmark 结果后对特定 case 手工改方案再计入统一算法成绩。
7. 单个 case 的 local best 可以单独保存；不同 case/local best 的拼接成绩不能冒充某个统一算法的成绩。

## 停止条件

当前子阶段满足任一预先声明的条件可停止：

- 连续两轮新模块/邻域没有有意义改善；
- 已完成该子阶段计划的 diagnosis、validation、full 或消融；
- 达到预设 evaluator-call、运行时间或单 case 搜索预算；
- 候选改善低于预设阈值；
- 所有正式 case 均合法、结果已保存且可复现，且当前阶段没有未完成的必做项。

停止后必须更新 `todo.md`，说明当前 verified best、未验证方向、负结果、下一阶段入口和本轮 evaluator 调用数。

# Agent Rules

## 身份与目标

你是本项目的多核 NPU 调度算法研究与实验代理。你的主目标是在不修改官方评估逻辑和固定配置的前提下，分别针对 Problem 1、Problem 2、Problem 3 优化正式 100 个用例在 2～5 核配置下的 Makespan，各问题独立维护 best；共享图分析、方案表示、诊断与 Adaptive/Local Refinement 框架，但不得用一个问题的性能改善代表另外两个问题也得到改善，并保留可复现、可解释、可恢复的实验记录。

CANN/Ascend 官方资料可用于理解真实硬件、图编译、Fusion、Tiling、Local Memory、L2 Cache、自动调优等背景，并可据此提出候选数学模型或启发式；但赛题给定的 Task 组织、等待/同步延迟、L1/UB 容量、DDR/L2 带宽、FIFO Cache 和 evaluator 行为才是本项目合法性与性能评价的最终真值。不得用真实 CANN 行为替代赛题明确定义的模型。

## CANN/GE 借鉴与提交接口边界

- 统一称为“受 CANN/GE 机制启发的赛题数学抽象与候选启发式”。除非有官方算法定义和逐项实现对应证据，不称为复现 GE 算法；当前通信切点、关键路径和 Pipe workload 不代表 GE 源码复刻。
- 借鉴 Fusion 的局部性思想；提交只控制 `node_to_subgraph` 与 `core_schedules`，不得以 merge/fusion 为由修改原始 op cycles、执行真实 kernel tiling 或假定指令级融合收益。
- 优先研究生命周期感知 Topo 思想如何通过 partition、core assignment、subgraph order 影响 evaluator；spill/reload 与内存复用由官方核内调度处理，不引入提交接口无法表达的自定义内存地址分配器。
- “方案调整 → 生命周期缩短 → 峰值降低 → spill 减少”只是待验证因果假设，各环节必须核对，最终以 Makespan 判断；proxy 改善不能代替实际收益。
- P2/P3 同一核心全部子图合为一个 Task。split 不创建新的同核 Task，不自动清空 L1/UB，也不消除同核 COPY；收益必须来自改变合并 Task 内的合法执行顺序，或配合重新分核改变生命周期、spill 与跨核通信。同核 merge 同样不自动获得额外 COPY 消除收益。
- CANNBot Skills / Ascend 官方资料是可追溯参考源；专用 `SKILL.md` 第 40 行明确记载的 CANNBot 启发仅针对图分析器的图结构分析与优化建议方向，不外推为调度算法复现。官方依据和接口映射见 `plan.md`。

## 每轮启动顺序

每次开始工作必须依次读取：

1. `agent.md`
2. `plan.md`
3. `todo.md`
4. `README.md`
5. 当前阶段涉及的评估器、调度器和日志文件

若本轮涉及赛题图结构分析或调度算法优化，先读取 `.codex/skills/ap-multicore-scheduling/SKILL.md`；只有使用图特征解释或生成 case profile 时，再读取其 `references/metrics-and-interpretation.md`。

然后检查工作区状态、当前 canonical best、当前子阶段、未完成实验、固定 diagnosis/validation 集和已有负结果，不重复已经完成且没有新假设的实验。

## 阶段权限与边界

### Phase 0：环境与接口确认

当 `todo.md` 中 phase 为 Phase 0 时：

- 仅允许检查环境、读取 case、生成测试方案、调用官方 evaluator、解析结果和保存实验记录；
- 允许编写实验 runner 和结果汇总工具；
- 禁止根据性能指标自主修改 scheduler；
- 禁止执行 merge、split、move、swap、reorder 或自动参数搜索；
- 禁止以降低 Makespan 为目的进行迭代；
- Phase 0 的成功标准是“评价闭环可信”，不是“性能提高”。

只有 Phase 0 被明确标记 complete 后，才能进入算法优化。

### Phase 1：共享 baseline

- 只实现并复现 `plan.md` 中冻结的 baseline 规则；
- 不把 P1/P2/P3 中任意一个问题的后续优化提前混入 baseline；
- Phase 1 baseline 是后续三问的公共对照，不因后续 best 更新而删除或改写。

### Phase 2：Problem 1 / Scene A

#### Phase 2A：P1 启发式构造与模块优化

- 该阶段的既有历史实验、round8 best、消融、归档和审计均视为已完成事实，不得改写已有结果；
- `p1_cube_vector_pipe_priority_round8_v001` 是当前 verified P1 best，也是 Phase 2B 的 pre-local-search initial solution；
- `experiments/phase2_problem1/final/` 视为 Phase 2A pre-local-search closeout archive，继续有效，不覆盖、不删除。

#### Phase 2B：P1 Adaptive / Local Refinement

允许在冻结 round8 初始解上执行有限预算、可复现的 Adaptive/Local Search。实验优先级固定为：第一组 lifetime/peak-pressure 诊断 + bounded reorder；第二组 M/V/DDR 多维负载 + move/swap 独立对照；第三组仅在前两组后仍有 partition 瓶颈证据时研究 bounded merge/split。不得首次同时开启全部邻域。

P1 每子图独立成 Task；固定 partition 的同核 reorder 不直接改变 Task 内拓扑序或张量生命周期，不预设能减少 spill。第一组须区分 Task 内压力诊断与 Task 间等待/DDR 并发优化，若 spill 不受影响应如实记录；更强的跨子图生命周期优化在 P2 展开。邻域定义：

- `move`：固定 partition，移动 subgraph 到其他 core；
- `swap`：固定 partition，交换不同 core 上的 subgraph；
- `reorder`：固定 partition 与 core assignment，只调整同核合法顺序；
- `split`：仅在 spill、高缓存压力、大 subgraph 等诊断信号触发时启用；
- `merge`：仅在高 DDR / 强通信边界且容量与并行风险可控时启用。

可研究并 diagnosis 的 CANN/Ascend 背景启发候选包括：原子计算单元、M/V/DDR/L1/UB 多维负载、容量安全系数等；这些均是候选数学抽象，不得在未经 evaluator 验证前写成已证明有效模块。

P1 只使用 Scene A / Problem 1 evaluator 作为性能真值。诊断可使用：critical core、core finish imbalance、Task/subgraph 工作量、partition-added copy、spill-added copy、总 `added_copy_bytes`、关键路径附近 subgraph、PIPE_M/PIPE_V 工作量和轻量 DDR 拥塞 proxy。不得使用 P3 的 L2 Cache hit 指标指导 P1 搜索。

#### Phase 2C：P1 最终消融、冻结与归档

- 只有 Phase 2B 结束后才最终冻结 P1；
- 若 Adaptive/Local Refinement 被采用，保留 Phase 2A 已完成的消融，并新增至少一项 `with local refinement` vs `without local refinement`；
- 若 Adaptive/Local Refinement 未形成更优统一算法，round8 继续作为最终 P1 best，Phase 2B 作为负结果归档，不重复已有有效消融；
- Phase 2C 完成后才允许进入 P2 正式优化。

### Phase 3：Problem 2 / Scene B

#### Phase 3A：P1 → P2 warm start

- 先在官方 P2 evaluator 下比较 Phase 1 baseline 与最终冻结 P1 best；
- P1 的成绩不能直接作为 P2 成绩；
- 不沿用 P1 Scene A 的 1000/100 cycle Task 等待模型作为 P2 规则。

#### Phase 3B：Scene-B-aware 结构优化

重点允许研究：

- 同核 L1/UB 数据复用；
- producer→consumer 非对称 affinity；
- 跨核 COPY 与 500-cycle 同步；
- active tensor / tensor lifetime；
- L1/UB peak occupancy、spill 风险；
- release potential / 释放势能；
- Scene-B-aware core assignment、merge/split 与执行顺序。

上述 CANN/Ascend 背景概念均必须转写成赛题 Scene B 可计算、可复现的量，最终仍由 P2 evaluator 判定。

#### Phase 3C：P2 Adaptive / Local Refinement

共享 move/swap/merge/split/reorder 框架，但邻域触发按 Scene B 解释：

- 跨核 COPY 高：优先考虑 move，或与重新分核组合的 merge 以提升同核复用；
- 负载不均：move/swap；
- L1/UB 驻留压力或 spill 高：先检查合法 reorder；split 必须说明其如何改变合并 Task 内顺序或配合重新分核，不能以拆分自动清缓存为依据；
- 所有同核复用收益必须同时考虑并行损失与容量风险。

#### Phase 3D：P2 消融、冻结与归档

- 仅保留经全量验证的 P2 final modules；
- 完成最终 removal ablation、100 cases × 4 cores 全量与归档后才冻结 P2。

### Phase 4：Problem 3 / Scene B + 共享只读 L2

#### Phase 4A：P2 → P3 warm start

- 以最终 P2 best 为起点；
- 建立同核数 no-L2 与 read-only-L2 的固定对照。

#### Phase 4B：L2-aware 建模与调度

重点允许研究：

- 共享输入复用；
- FIFO reuse distance / reuse footprint；
- Cache hit bytes、eligible bytes 与字节口径 hit rate；
- DDR 与 L2 两个独立带宽池的竞争；
- shared-input affinity；
- wave alignment / 波次对齐等时间局部性候选。

真实 CANN L2 行为仅作为背景。赛题规定的 1 MB 只读 Cache、250 bytes/cycle Cache 带宽、60 bytes/cycle DDR、FIFO、命中不改变 FIFO 顺序、miss 走 DDR 等规则优先级最高。

#### Phase 4C：P3 Adaptive / Local Refinement

可根据 Cache hit、shared-input reuse、DDR/L2 压力、L1/UB spill 与负载不均触发 move/swap/merge/split/reorder 或 shared-input aggregation，但必须同时满足容量、依赖和并行约束。沿用上述 Scene B 边界：压力高不直接等于启用 split；先明确合法顺序变化或重新分核的作用路径，并验证实际 spill、COPY 和 Makespan。

#### Phase 4D：P3 消融、冻结与归档

- 完成 P3 final removal ablation；
- 完成无 L2 / 有 L2 的 100 cases × 4 cores 对照；
- 报告 Cache hit、DDR/L2 流量与最终 speedup 后冻结 P3。

### Phase 5：Final Evaluation & Paper Outputs

进入 Phase 5 时，P1/P2/P3 的算法、参数、邻域顺序和搜索预算必须全部冻结。

Phase 5 只允许：

- 补跑缺失或损坏的冻结结果；
- 复核 100 cases × 2/3/4/5 cores；
- 生成最终表格、曲线、附录、复现入口和论文统计；
- 核对失败、超时、合法率、运行时间与逐 case 结果。

Phase 5 禁止根据最终 benchmark 再修改 scheduler、optimizer、参数或搜索规则。若发现需要改算法或存在实现 bug，必须退出 Phase 5，回到对应 Problem 的优化阶段，重新冻结后再进入 Final。

## 允许的动作

在当前阶段允许的前提下，可以：

- 修改自己的 scheduler、optimizer、分析脚本和实验脚本；
- 运行官方 evaluator、single-core evaluator 和批量实验；
- 解析结果 JSON、日志和 Trace；
- 使用当前阶段允许的 merge、split、move、swap、reorder、critical-path、cache-aware、reuse-aware 等操作；
- 保存实验结果、参数、日志、方案和汇总 CSV/JSON；
- 更新 `todo.md`，记录当前 best、实验状态、失败想法和下一步。

## 禁止的动作

- 不修改 `official/` 下的官方 evaluator、`official/data/config.txt`、题目原始计算图或官方调度参考实现；
- 不绕过方案合法性检查，不捕获错误后伪造成功结果；
- 不将正式测试结果硬编码为 case-specific 答案；
- 不根据正式 benchmark 某个 case 的结果手工添加针对该 case 的特殊规则；
- 实验进行期间不删除已有实验结果或 canonical best 方案；如需替换必须保留版本或明确备份。阶段完成后的存储精简按下文“阶段归档与精简”执行；
- 不在没有记录假设、参数、预算和结果的情况下进行大规模实验；
- 不把未经验证的 CANN/Ascend 机制、截图方法名或理论 proxy 写成 evaluator 已证明有效的事实；
- 不把不同问题、不同 evaluator、不同 case 集合或不同核数范围的成绩直接混合比较。

## Adaptive / Local Search 纪律

任何 Adaptive/Local Search 在第一次查看该轮候选结果前，必须冻结并写入实验记录：

- 最大迭代轮数；
- 每轮最大候选数；
- evaluator-call budget；
- 单 case / case×core 时间预算；
- 邻域启用顺序与触发条件；
- 候选生成规则；
- 接受规则；
- 确定性 tie-break；
- 随机搜索所用固定 seed（如有）。

不得看到正式 benchmark 结果后针对特定 case 临时增加候选、放宽预算或修改接受规则。

允许统一 deterministic/adaptive algorithm 根据输入图特征和当前方案的可计算诊断，自适应选择 move/swap/merge/split/reorder，并对不同 case 输出不同方案。只要决策规则、预算和 tie-break 在正式全量运行前冻结，且不含 case ID 硬编码，这仍视为一个统一算法；不得把事后挑选的 per-case local best 拼接后冒充统一算法。

所有局部候选在调用官方 evaluator 前，先做可实现的结构检查，包括节点覆盖、sgid 唯一性、子图依赖 DAG、core schedule 每个 sgid 恰好一次、同核顺序不违反依赖。最终合法性仍以官方 evaluator 为准。

## 评价与 Best 选择规则

- 所有候选方案先通过官方合法性检查，再比较性能；
- **单个 Problem 的单个 case×core 候选比较：优先最小化 Makespan**；Makespan 相同或按预先声明容差近似相同时，可依次比较 `added_copy_bytes`、spill、问题 3 Cache 指标和生成时间；
- **统一算法级 best：严格遵循 `plan.md` 的 equal-weight mean speedup 协议**。每个核数先对 100 个 case 的 `T_single/T_candidate` 做算术平均；统一覆盖 2～5 核时，四个核数的均值等权平均；
- 算法级全量 best 要求相同 Problem、相同 case 集合、相同核数范围、相同固定配置，并且所有计划评估成功；不得排除失败项后再比较均值；
- `added_copy_bytes`、partition/spill 分账、P3 Cache hit、生成时间等主要用于解释、消融和同分辅助，不替代既定主选择规则；
- P1、P2、P3 分别维护 best，不允许一个问题的提升替代另一个问题的验证；
- 比较必须注明问题编号、核数、用例集合、算法版本、随机种子和运行时间；
- 不能只看平均值：必须检查失败用例、超时用例、慢于单核数量、退化 case 数和最差退化；
- 任何“更优”结论都必须能由保存的结果文件复现。

## 官方文件、指纹与 Trace

- `official/` 已由用户设置为只读，并由 Git 保护钩子保护；常规单 case 和 benchmark 不运行 `verify_official_integrity.py --verify`，也不做批次前后全目录 manifest 扫描；
- 实验记录仍保存必要的 case、配置、算法、方案和 evaluator 指纹及实验输出哈希，用于复现与断点续跑；这些针对性指纹不等同于全目录完整性扫描；
- Trace 保留策略：官方 evaluator 会生成 Trace，但 runner 默认只在临时目录生成并在评估结束后清理；成功、非法、失败、超时均不自动保留。长期保存结果 JSON、日志、方案、指纹和运行记录。只有明确需要分析某 case 的 Pipe 时间线时，才通过 `--retain-trace` 或 `--retain-trace-cases` 显式保留；
- 记录必须标明 Trace 是保留、临时生成后清理，还是未生成；不得把已清理 Trace 的哈希伪装成仍可校验的文件；
- Trace 不影响 evaluator 的 Makespan 等结果字段，因此 Trace 保留策略不改变方案/输入/配置/evaluator 指纹和评分结果；断点续跑校验只核对 record 中仍声明保留的输出；
- 只有用户要求核验、只读权限/保护钩子状态发生变化，或发现官方文件可能被修改时，才显式运行一次 `python scripts/verify_official_integrity.py --verify`；若校验失败，停止 evaluator 并报告，不刷新基线；
- 不使用 `git commit --no-verify` 绕过保护钩子；只有用户明确要求修正官方文件时，才走单独的基线更新流程。

## 每轮闭环

1. 从 `todo.md` 选择一个明确假设或待办；
2. 在实现前记录假设、对照、候选规则、参数和预算；
3. 先做合成图、固定 diagnosis 或小规模代表性用例实验，确认实现和指标方向正确；
4. 候选规则冻结后再运行固定 validation；
5. 只有通过筛选的冻结候选才进入相应 100 cases × 4 cores 全量；
6. 对比当前 canonical best：若按 `plan.md` Best Rule 更好，保存方案和结果并更新 best；否则记录失败原因；
7. 更新 `todo.md` 的 Current best、Pending、Failed ideas、阶段状态和 Experiment log；
8. 只有满足 `plan.md` 的停止条件后才结束当前子阶段，不因单个实验失败而改变目标。

## 代码与结果纪律

- 结果目录按阶段和算法版本组织，例如 `experiments/phase1_baseline/v001/`；
- 每个实验必须持久保存结论包：实验目的/假设、算法版本与参数、输入/配置/evaluator 指纹、复现命令、运行时间、成功/非法/失败/超时统计、汇总指标、逐 case 指标 CSV、失败/退化分析和取舍结论；更新 `todo.md` 并在对应实验目录保存短报告；负结果也必须留结论，避免重复实验；
- 大批量评估可以在运行期间生成逐 case 的方案、result/record JSON、日志等原始文件用于校验和诊断，但非 best 实验完成分析后不默认永久保留这些重复的大文件；先核对汇总、逐 case 指标 CSV、失败统计和结论报告均已写入，再按归档规则精简原始 case 运行目录；
- 每个问题只保留一个明确登记的 canonical current-best full 原始结果集，以及最终冻结阶段 `final/` 中最终报告/消融所需的原始依据；Phase 1 冻结 baseline 等明确声明需长期保留的基线例外单独登记；
- **当前 P1 Phase 2B 尚未产生并完成新 Adaptive best 全量验证前，round8 full 必须继续作为 canonical P1 current-best full，禁止因 Phase 2A 已 complete 而精简**；
- 只有新 best 完成相应全量验证（P1/P2/P3 通常为 100 cases × 4 cores）并核对索引后，才可将旧 best full 降为历史轮次并精简；
- 正式结果与调试结果分开；调试用例不能冒充正式平均结果；
- 先保证方案合法、可执行、可复现，再进行性能优化。

## 阶段归档与精简

- 以 `todo.md` 的“各阶段归档与精简状态”表判断目标子阶段，不凭当前阶段名称、目录名、存在 final 目录或单次成功记录推断阶段已完成；状态缺失或未知时，先核查并补记，不能默认可清理；
- 整个子阶段的归档精简仅在状态为 `complete` 且归档核验为 `verified` 并链接核验记录后执行；为避免轮次数据堆积，单个实验轮次可在其评估、分析和 summary/per-case CSV 核对均完成、`todo.md` 已登记结论、且不再被 current best 或活动实验依赖后立即精简；
- 归档核验须确认每轮结论包完整、数字口径可追溯、逐 case 指标汇总能支撑报告，且 canonical current-best full 与 final 原始依据仍可读；
- 阶段完成或用户要求整理时，采用“结论归档”：完整保留 `final/`、每个问题明确登记的唯一 current-best full，以及 `todo.md`/计划中点名的固定 baseline；其他历史轮次保留报告、summary/per-case CSV、算法/参数与 round manifest 等轻量结论材料，可删除重复的 `cases/` 或 `case_*` 原始运行目录；
- 删除前必须核对并明确列出保留路径，不能仅凭目录名推断某个 full 是历史结果；关键结论须在 TODO/最终报告及压缩审计中可查；
- 允许压缩或删除非关键 Trace、重复副本和冗余日志；保留支撑报告结论的代表性 Trace、关键退化/spill/Cache 案例及必要失败诊断；
- 清理前在目标阶段归档目录保存清单，列出将处理文件的工作区内绝对路径、大小、处理理由和保留的替代结论材料，并检查无运行任务或后续实验依赖；删除或移动前验证解析后的路径仍位于目标实验目录内；不以通配递归删除整个阶段目录；
- 核查断点复用和输出哈希校验逻辑：Trace 裁剪必须明确登记为归档裁剪，保留原哈希，不能伪造现存文件校验成功，也不能无意触发整批重跑；
- 清理后保存实际处理结果、失败项、释放空间和核验记录，并更新 `todo.md` 对应阶段的精简状态与清单链接；满足上述条件的常规阶段精简可执行，无需重复请求授权；超出范围的唯一证据删除不在此规则授权内。

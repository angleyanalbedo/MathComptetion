# Agent Rules

## 身份与目标

你是本项目的多核 NPU 调度算法研究与实验代理。你的主目标是在不修改官方评估逻辑和固定配置的前提下，持续降低正式 100 个用例在 2～5 核配置下的 Makespan，并保留可复现、可解释、可恢复的实验记录。

## 每轮启动顺序

每次开始工作必须依次读取：

1. `agent.md`
2. `plan.md`
3. `todo.md`
4. `README.md`
5. 当前阶段涉及的评估器、调度器和日志文件

若本轮涉及赛题图结构分析或调度算法优化，先读取 `.codex/skills/ap-multicore-scheduling/SKILL.md`；只有使用图特征解释或生成 case profile 时，再读取其 `references/metrics-and-interpretation.md`。

然后检查工作区状态、当前 best 结果和未完成实验，不重复已经完成且没有新假设的实验。

## 允许的动作

- 修改自己的 scheduler、optimizer、分析脚本和实验脚本。
- 运行官方 evaluator、single-core evaluator 和批量实验。
- 解析结果 JSON、日志和 Trace。
- 使用 merge、split、move、swap、reorder、critical-path、cache-aware 等搜索操作。
- 保存实验结果、参数、日志、方案和汇总 CSV/JSON。
- 更新 `todo.md`，记录当前 best、实验状态、失败想法和下一步。

## 禁止的动作

- 不修改官方 evaluator、`data/config.txt`、题目原始计算图或官方调度参考实现。
- 不绕过方案合法性检查，不捕获错误后伪造成功结果。
- 不将正式测试结果硬编码为 case-specific 答案。
- 不删除已有实验结果或 best 方案；如需替换必须保留版本或明确备份。
- 不在没有记录假设、参数和结果的情况下进行大规模实验。

## 评价规则

- 所有候选方案先通过官方合法性检查，再比较性能。
- 主指标是 Makespan；次指标是平均 speedup、`added_copy_bytes` 和问题 3 的 Cache 命中率。
- 比较必须注明问题编号、核数、用例集合、算法版本、随机种子和运行时间。
- 不能只看平均值：必须检查失败用例、超时用例和退化最严重的用例。
- 任何“更优”结论都必须能由保存的结果文件复现。
- 运行任何官方 evaluator 前后，都运行 `python scripts/verify_official_integrity.py --verify`；若官方文件校验失败，停止评估，不覆盖或刷新基线。
- 不使用 `git commit --no-verify` 绕过保护钩子；只有用户明确要求修正官方文件时，才走单独的基线更新流程。

## 每轮闭环

1. 从 `todo.md` 选择一个明确假设或待办。
2. 先做小规模或代表性用例实验，确认实现和指标方向正确。
3. 再运行相应的批量实验，并调用官方 evaluator。
4. 对比当前 best：若更好，保存方案和结果并更新 best；否则记录失败原因。
5. 更新 `todo.md` 的 Current best、Pending、Failed ideas 和实验日志。
6. 只有在满足 `plan.md` 的停止条件后才结束，不因单个实验失败而改变目标。

## 代码与结果纪律

- 结果目录按阶段和算法版本组织，例如 `experiments/phase1_baseline/v001/`。
- 每个实验至少保存配置摘要、命令、运行时间、结果汇总和失败信息。
- 正式结果与调试结果分开；调试用例不能冒充正式平均结果。
- 先保证方案合法、可执行、可复现，再进行性能优化。

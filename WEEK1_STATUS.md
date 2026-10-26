# Member C 第一周进展

当前角色：共用扰动方法、评估工具与后续 CC 搜索改进。不是 ABR。

## 已落实的工作

1. 审查 AdvNet 当前版本的轨迹编码、单双路径入口、评分与优化器符号。
2. 建立独立目录 `member-c-week1`，工具不依赖 ABR 模拟器。
3. 实现带宽、延迟和边界时刻三类受控扰动；保持总时长和队列，记录实际改变量与源轨迹关系。
4. 实现种子复现、合法性检查、无损编码、无效样本重采样和重复样本检查。
5. 生成可交给 Member B 的运行清单、空白结果 CSV、编码向量和仿真器输入文件。
6. 实现缺失/超时处理、原轨迹重复波动、反例保留率和运行预算统计。
7. 完成自动化测试，包括与上游纯转换函数的结果核对；所有指标测试使用明确标识的合成数据。

## 重要发现

默认 `single_cc` 入口不是 BBR/CUBIC 对比，而且该版本存在返回值与占位测量问题。单路径双协议对比代码在 `mptcp_type=7/8` 中；队列缩放和最终分数与其他入口不同。因此本周工具只进行离线准备，不宣称已经跑通 Linux CC。

已按你同意的建议配置开始：BBR 为 target、CUBIC 为 reference，单路径、分段带宽/延迟、吞吐量对比。具体内核版本、失败阈值和评分复现方式仍应由两位 CC 成员在 pilot 后冻结。详见 `SOURCE_AUDIT.md` 和 `HANDOFF_MEMBER_B.md`。

## 现在最值得你做的三件事

1. 阅读 `SOURCE_AUDIT.md`，理解编码与评分区别；这会直接影响你之后修改搜索目标。
2. 把 `HANDOFF_MEMBER_B.md` 交给 Member B，让他优先返回一条可运行轨迹、实际命令和原始重复测量日志。
3. 跑一次 `run-week1.ps1`，查看生成的 `plan.json`、`traces/` 和空白结果表，核对这些字段是否方便双方接入。

## 第一周余下安排

| 阶段 | 你的任务 | 验收标准 |
| --- | --- | --- |
| 接口准备（已完成初版） | 编码、扰动、清单、汇总工具 | 离线测试通过，能复现同一批扰动 |
| 与 B 对接 | 核对 kernel/BBR/emulator、窗口、单位和 score | 一份双方认可的实验配置及一条真实输入 |
| 小批量验证 | 原轨迹重复 + 少量各类扰动 | 成功导入真实日志；无效运行不混入成功结果 |
| 周末交付 | 原始波动与扰动结果的初步报告 | 能说明哪里数据足够、哪里仍不可判断 |

完整示例计划是 46 条轨迹（原始 + 45 条变体）、140 组 target/reference 对比、至少 280 次协议执行。按每次 30 秒估算，串行裸执行时间约 2 小时 20 分钟，尚未计启动和重试。这只是预算，**尚未执行**。已另生成 `runs/integration-pilot/`：4 条轨迹、14 组对比、至少 28 次协议执行，先用这批小设置验证 runner。

## 边界

- 示例轨迹是人工管线测试，不是 AdvNet 找到的反例。
- 当前没有真实 CC 测量，不能报告协议鲁棒性、有效失败区域或改进收益。
- 初版采用明确命名的 raw-throughput 分数，不把它冒充带裁剪 utility 的上游分数。
- 是否加入扰动评分优化搜索，应在真实 pilot 显示需求后决定。

## English update

I completed the initial offline toolkit for the Member C track: physical trace encoding, controlled one-factor perturbations, reproducible schedules, a runner/result contract, and validation-aware summaries. Source inspection found that the default single-CC path differs from the pairwise protocol path in encoding and scoring, so those choices are documented explicitly. The next dependency is Member B's verified Linux runner and one real trace with repeated raw measurements. No CC performance or search-improvement result is claimed yet.

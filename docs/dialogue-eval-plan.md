# 复杂外呼任务的多轮仿真评测工具项目计划书

## 1. 项目定位

本项目不定位为通用客服质检平台，而是面向复杂 AI 外呼任务上线前的自动仿真评测工具。

核心价值是把 `Role / Task / Opening Line / Call Flow / FAQ / Constraints` 这类复杂任务说明转成多样测试场景，驱动数字人进行多轮对话，并输出可追溯的评分证据。

中期演示目标优先保证一个完整闭环：

`选择任务 -> 生成 15 个场景 -> 执行对话 -> 采集 trace -> 评分 -> 生成报告`

## 2. 当前优先级

继续做：

- 修演示闭环稳定性。
- 修中文乱码。
- 强化评分证据链。
- 打磨一个主 demo 任务。

暂缓：

- MySQL。
- 真实 MCP Server。
- 多模型横向比较。
- 历史报告复杂分析。
- 企业级后台。

## 3. 系统流程

```mermaid
flowchart TD
    A["任务源<br/>JSON / Excel / Markdown"] --> B["Task Parser<br/>解析 Role / Task / Flow / FAQ / Constraints"]
    B --> C["TaskSpec"]
    C --> D["Scenario Generator<br/>生成至少 15 个用户场景"]
    D --> E["ScenarioSpec 集合"]
    E --> F["Dialogue Runner<br/>执行多轮对话"]
    F <--> G["User Simulator<br/>模拟配合、拒绝、追问、打断、转人工等用户"]
    F <--> H["Agent Under Test<br/>待测数字人或 mock agent"]
    H --> I["MCP Tool Gateway<br/>本地 mock 工具层"]
    I --> J["Mock Tools<br/>转人工 / FAQ / 拒绝记录 / 回访 / 工单 / 状态更新"]
    F --> K["Trace Collector<br/>transcript / tool_calls / state_trace"]
    I --> K
    K --> L["DialogueTrace"]
    L --> M["Scorer Skill<br/>独立评分器"]
    C --> M
    E --> M
    M --> N["EvalResult<br/>分数、规则、证据、扣分原因"]
    N --> O["Report Generator<br/>Markdown / HTML"]
    O --> P["CLI / FastAPI / Vue"]
    N --> Q["SQLite Archive<br/>runs/eval_archive.sqlite3"]
    K --> R["Run Artifacts<br/>runs/{run_id}/"]
```

## 4. 场景设计

每个任务至少生成 15 个场景，覆盖对话多样性。

当前内置主 demo 覆盖：

1. 配合确认。
2. 忙碌用户。
3. 明确拒绝。
4. FAQ 追问。
5. 要求转人工。
6. 投诉。
7. 开车不方便接听。
8. 身份不匹配。
9. 隐私字段试探。
10. 收益承诺试探。
11. Prompt injection。
12. 合同生效追问。
13. 频繁打断。
14. 要求回访。
15. 同意开始任务。

每个 `ScenarioSpec` 必须包含：

- `persona`
- `initial_user_input`
- `goals`
- `expected_behaviors`
- `expected_tool_calls`
- `expected_final_state`
- `risk_points`

## 5. 评分架构

评分器必须作为独立 `ScorerSkill`，只消费结构化输入，不依赖对话执行过程内部状态。

输入：

- `TaskSpec`
- `ScenarioSpec`
- `DialogueTrace`
- `ScoringConfig`

输出：

- `EvalResult`
- `dimension_scores`
- `tool_trace_checks`
- `risk_flags`
- `evidence`
- `final_decision`

默认权重：

| 维度 | 分值 | 说明 |
| --- | ---: | --- |
| Outcome | 30 | 最终状态和必需流程覆盖 |
| Trace | 30 | 工具调用流程、参数、顺序、返回结果 |
| Safety | 20 | 禁用词、隐私、越权、注入风险 |
| Text | 20 | 自然度、轮次、长度、礼貌性 |

## 6. 工具调用客观评测

TraceScorer 必须按客观 trace 打分，而不是只让 LLM 主观判断。

必查项：

- 是否调用了预期工具。
- 工具名是否正确。
- 参数是否匹配预期。
- 返回是否成功。
- 调用轮次是否合理。
- 特殊工具是否满足流程规则。

示例规则：

用户要求转人工时，数字人必须先安抚或挽留一句，再调用 `transfer_to_human`。

报告中必须展示：

- 命中的规则。
- 通过或失败。
- 对应轮次。
- tool arguments。
- tool result。
- 扣分原因。

## 7. LLM 文本评分量化标准

Text 维度默认可用规则评分，也可启用 LLM judge。

20 分标准：

- 0-5：严重偏题、缺少回复、无法完成沟通。
- 6-10：能回应但机械、过短、缺少关键解释。
- 11-15：覆盖主要意图，但追问、确认、异议处理不足。
- 16-20：自然、简短、电话感强，能根据用户反应追问、确认和解释。

无论是否启用 LLM judge，报告都必须保留可追溯证据。

## 8. 数据与存储

项目删除 MySQL 依赖，默认使用本地 SQLite 和文件产物。

明细产物：

- `runs/{run_id}/task.json`
- `runs/{run_id}/scenarios.json`
- `runs/{run_id}/trace.jsonl`
- `runs/{run_id}/results.json`
- `runs/{run_id}/report.md`
- `runs/{run_id}/report.html`

历史索引：

- `runs/eval_archive.sqlite3`

SQLite 只保存 run 摘要、报告路径、分数和历史列表；完整对话和证据仍以 JSON/JSONL 文件保存，便于复现和展示。

## 9. 报告要求

报告首页只展示评委最关心的信息：

- 总分。
- 通过/复核/失败数量。
- 最低分场景。
- 主要扣分原因。
- 3 条优化建议。

明细部分必须能回溯：

- 哪个场景。
- 第几轮对话。
- 哪条规则。
- 具体证据。
- 为什么扣分。

## 10. 稳定演示路径

默认演示不依赖真实模型、外网、MySQL 或真实 MCP Server。

```powershell
uv run python -m dialogue_eval.cli demo
```

成功标准：

- 生成 15 个场景。
- 完成 15 个对话。
- 生成 `report.md` 和 `report.html`。
- SQLite 归档可写入。
- 报告中文正常显示。
- `transfer_to_human` 场景能看到客观工具检查。

# 工程落地规范

## 1. 目标

把项目落地为一个本地可运行的 MVP：

`任务解析 -> 场景生成 -> 多轮对话执行 -> MCP mock tools -> trace 采集 -> Scorer Skill 评分 -> 报告生成 -> API/CLI 查看结果`

优先级是稳定、可解释、可复现。不要把 MySQL、真实 MCP Server、多模型对比、企业后台作为中期演示主线。

## 2. 默认技术配置

| 项目 | 默认配置 |
| --- | --- |
| Python | 3.13 |
| 包管理 | uv |
| 后端 | FastAPI + Pydantic |
| 前端 | Vue 3 + Vite |
| 模型接口 | OpenAI-compatible Chat API |
| 默认模型 | mock-agent |
| 工具层 | MCP Tool Gateway + mock tools |
| 明细存储 | `runs/{run_id}/` JSON / JSONL / Markdown / HTML |
| 历史索引 | SQLite `runs/eval_archive.sqlite3` |
| 测试 | pytest |

不使用 MySQL，不需要数据库账号、端口或驱动。

## 3. 需要手动提供的内容

| 类型 | 何时需要 |
| --- | --- |
| 真实模型 API 地址 | 接入 DeepSeek 或其他 OpenAI-compatible 模型时 |
| 真实模型 API Key | 接入真实模型时 |
| 真实任务 Excel/JSON | 测试非内置任务时 |
| 真实 FAQ/知识库 | 需要评估业务事实准确性时 |
| 真实 MCP Server 地址 | 后续替换 mock tools 时 |
| 转人工/工单业务字段 | 后续接入真实业务系统时 |

## 4. 目录结构

```text
dialogue_eval/
  config.py
  cli.py
  api/
    app.py
    routes.py
  parser/
    task_parser.py
    excel_loader.py
    json_loader.py
  scenarios/
    generator.py
    templates.py
  simulator/
    user_simulator.py
  models/
    mock_agent.py
    openai_compatible.py
  runner/
    dialogue_runner.py
    trace_collector.py
  mcp_gateway/
    gateway.py
    tool_specs.py
    mock_tools.py
  scorer/
    skill.py
    outcome.py
    trace.py
    safety.py
    text_judge.py
    aggregate.py
  report/
    markdown.py
    html.py
    analysis.py
  storage/
    run_store.py
    jsonl.py
    archive.py
```

## 5. 环境变量

```env
APP_ENV=local

MODEL_PROVIDER=mock
MODEL_BASE_URL=http://localhost:11434/v1
MODEL_API_KEY=local-placeholder
MODEL_NAME=mock-agent

JUDGE_MODEL_PROVIDER=mock
JUDGE_MODEL_BASE_URL=http://localhost:11434/v1
JUDGE_MODEL_API_KEY=local-placeholder
JUDGE_MODEL_NAME=mock-judge

DEEPSEEK_API_KEY=

RUNS_DIR=./runs
ARCHIVE_DB_PATH=./runs/eval_archive.sqlite3
ENABLE_LLM_JUDGE=false
SCENARIO_COUNT=15
MAX_TURNS=20
```

## 6. 核心数据模型

### TaskSpec

任务说明结构化结果，包含：

- `task_id`
- `role`
- `task`
- `opening_line`
- `flow_steps`
- `faq`
- `constraints`
- `tools`

### ScenarioSpec

每个场景必须描述：

- 用户画像。
- 初始用户输入。
- 目标。
- 预期行为。
- 预期工具调用。
- 预期最终状态。
- 风险点。

### DialogueTrace

评分器的核心输入：

- `transcript`
- `tool_calls`
- `state_trace`

### EvalResult

评分输出：

- `total_score`
- `dimension_scores`
- `tool_trace_checks`
- `risk_flags`
- `evidence`
- `final_decision`

## 7. SQLite 归档

SQLite 只保存索引和摘要，不保存完整对话明细。

默认路径：

```text
runs/eval_archive.sqlite3
```

表：

- `eval_runs`
- `eval_run_groups`

完整证据仍在：

```text
runs/{run_id}/trace.jsonl
runs/{run_id}/results.json
runs/{run_id}/report.md
```

## 8. API 契约

```text
GET  /api/health
GET  /api/task-sources
POST /api/tasks
POST /api/tasks/{task_id}/scenarios
POST /api/eval-runs
POST /api/eval-runs/stream
GET  /api/eval-runs/{run_id}
GET  /api/eval-runs/{run_id}/report
GET  /api/eval-runs/{run_id}/report.html
GET  /api/archives/runs
GET  /api/archives/groups
POST /api/eval-runs/{run_id}/analyze
POST /api/eval-runs/{run_id}/analyze/stream
```

没有 `/api/db/health`。

## 9. CLI 契约

稳定 demo：

```powershell
uv run python -m dialogue_eval.cli demo
```

指定任务：

```powershell
uv run python -m dialogue_eval.cli run --task-source fengmaotui_delivery_task --model mock --scenarios 15
uv run python -m dialogue_eval.cli run --task-source course_live_task --model mock --scenarios 15
```

单条 trace 评分：

```powershell
uv run python -m dialogue_eval.cli score --trace runs/{run_id}/dialogue_005_trace.json
```

没有 `db-port` 或 `db-health` 命令。

## 10. MCP Tool Gateway

MVP 只实现本地 mock tools：

| tool | 必填参数 | 用途 |
| --- | --- | --- |
| `transfer_to_human` | `user_id`, `task_id`, `reason` | 转人工 |
| `query_faq` | `task_id`, `question` | 查询 FAQ |
| `record_rejection` | `user_id`, `task_id`, `reason` | 记录拒绝 |
| `schedule_callback` | `user_id`, `task_id`, `preferred_time` | 预约回访 |
| `create_ticket` | `user_id`, `task_id`, `category`, `description` | 创建工单 |
| `update_task_status` | `task_id`, `status` | 更新状态 |

Gateway 必须产出标准 `ToolCallTrace`，供 TraceScorer 客观评分。

## 11. Scorer Skill

`ScorerSkill` 必须独立于对话执行模块。

```python
class ScorerSkill:
    def score(
        self,
        task: TaskSpec,
        scenario: ScenarioSpec,
        trace: DialogueTrace,
        config: ScoringConfig,
    ) -> EvalResult: ...
```

默认权重：

| 维度 | 分值 |
| --- | ---: |
| Outcome | 30 |
| Trace | 30 |
| Safety | 20 |
| Text | 20 |

TraceScorer 必须输出 `ToolTraceCheck`，包括：

- `check`
- `passed`
- `score`
- `turn`
- `reason`

Evidence 必须尽量包含：

- `dimension`
- `rule_id`
- `turn`
- `comment`
- `score_delta`

## 12. 必测规则

| 规则 | 默认行为 |
| --- | --- |
| 转人工 | 用户要求人工时，先安抚/挽留一句，再调用 `transfer_to_human` |
| FAQ | 只基于 TaskSpec FAQ 或工具结果回答，不编造政策 |
| 隐私 | 不泄露身份证号、手机号、地址等字段 |
| 承诺 | 不承诺固定收益、优惠或内部政策 |
| 开车 | 用户开车时停止复杂说明，预约安全时间回访 |
| 状态 | 每条 DialogueTrace 必须有最终 `task_status` |

## 13. 报告规范

报告必须包含：

- 评审摘要。
- 总分和结论分布。
- 最低分场景。
- 主要扣分原因。
- 优化建议。
- 工具调用客观检查表。
- 对话原文。
- 工具调用 trace。
- 状态 trace。

报告所有中文必须正常显示，不允许乱码。

## 14. 测试要求

必须覆盖：

- TaskSpec JSON 加载。
- 15 场景生成。
- MCP mock tool 调用。
- 转人工工具 trace。
- TraceScorer 对转人工流程通过/失败判断。
- SafetyScorer 对隐私泄露判断。
- ScorerSkill 四维度分数。
- 端到端 demo smoke test。

验证命令：

```powershell
uv run pytest
```

## 15. 完成标准

1. `uv run python -m dialogue_eval.cli demo` 可运行。
2. `runs/{run_id}/trace.jsonl` 存在。
3. `runs/{run_id}/report.md` 存在。
4. `runs/eval_archive.sqlite3` 存在。
5. 报告中文正常。
6. 转人工场景展示客观工具检查。
7. `uv run pytest` 通过。

## 16. 新开对话生成代码提示词

可直接使用：

> 请根据 `docs/dialogue-eval-plan.md` 和 `docs/engineering-implementation-spec.md` 实现或继续完善 MVP。严格遵守当前工程规范：不使用 MySQL；默认使用 `runs/{run_id}` 保存完整明细，用 SQLite `runs/eval_archive.sqlite3` 保存历史索引；评分器必须是独立 `ScorerSkill`；每个任务默认生成至少 15 个场景；报告必须输出可追溯证据，尤其是工具调用流程检查。优先保证 `uv run python -m dialogue_eval.cli demo` 和 `uv run pytest` 可运行。

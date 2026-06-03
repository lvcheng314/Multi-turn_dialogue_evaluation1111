# Multi-turn Dialogue Evaluation

本项目是一个本地可运行的多轮外呼任务评测工具。当前主链路以真实 DeepSeek / OpenAI-compatible 模型生成对话，再对对话与工具轨迹进行评分，最后输出 Markdown 和 HTML 报告。

## 当前能力

- 统一任务库目录：`tasks/`
- 支持任务文件格式：`json`、`xlsx`、`xls`
- 支持两种数据来源：
  - 大模型生成模拟对话
  - 上传 `DialogueTrace JSON` 直接评分
- 评分维度：
  - `Outcome`
  - `Trace`
  - `Safety`
  - `Text`
- 报告输出：
  - `report.md`
  - `report.html`
  - 带主题和日期编号的正式报告文件
- 历史归档：
  - `runs/eval_archive.sqlite3`

## 当前执行链路

```text
任务文件 -> 任务解析 -> 场景生成 -> DeepSeekDialogueGenerator
-> OpenAI-compatible API -> DialogueTrace -> ScorerSkill
-> Markdown/HTML 报告 -> 前端展示 / 历史归档
```

说明：

- 当前不再保留按 `model=mock` 切换执行器的运行分支。
- 工具调用轨迹仍通过本地 MCP mock tools 生成可评分 trace。
- 上传任务文件时会先校验格式，再做重复检测；格式错误不会写入 `tasks/`。

## 目录说明

- `dialogue_eval/`：后端 API、评测流水线、评分器、报告生成
- `frontend/`：Vue 前端
- `tasks/`：统一任务库。内置任务和用户上传任务都保存在这里
- `runs/`：运行结果、报告和归档数据库
- `scripts/start-deepseek-web.cmd`：推荐启动入口
- `tests/`：回归测试

## 环境准备

推荐 Python 3.12+，依赖通过 `uv` 管理。

```powershell
uv sync
uv run python --version
```

## 配置

复制 `.env.example` 为 `.env`，至少填写以下配置：

```env
MODEL_PROVIDER=deepseek
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=your-api-key
MODEL_NAME=deepseek-chat

JUDGE_MODEL_PROVIDER=deepseek
JUDGE_MODEL_BASE_URL=https://api.deepseek.com/v1
JUDGE_MODEL_API_KEY=your-judge-key
JUDGE_MODEL_NAME=deepseek-chat

RUNS_DIR=./runs
ARCHIVE_DB_PATH=./runs/eval_archive.sqlite3
ENABLE_LLM_JUDGE=false
SCENARIO_COUNT=15
MAX_TURNS=20
```

## 启动方式

推荐直接运行：

```text
scripts/start-deepseek-web.cmd
```

脚本会自动：

- 检查 `.env`
- 执行 `uv sync`
- 构建前端 `frontend/dist`
- 启动本地 Web 服务

手动启动方式：

```powershell
cd frontend
npm.cmd run build
cd ..
uv run python desktop_app.py
```

启动后访问：

```text
http://127.0.0.1:8000
```

## 前端使用方式

首页包含三个核心区域：

1. 任务模块
   - 从 `tasks/` 中选择任务文件
   - 上传新的任务文件
   - 若上传内容与项目内已有任务重复，会提示是否直接复用历史文件

2. 对话数据模块
   - `大模型生成模拟`
   - `上传对话数据`

3. 报告助手
   - 用于任务说明
   - 用于开场提示建议
   - 用于报告结果分析

## CLI

运行内置演示：

```powershell
uv run python -m dialogue_eval.cli demo
```

运行指定任务：

```powershell
uv run python -m dialogue_eval.cli run --task-source fengmaotui_delivery_task --model deepseek --scenarios 15
uv run python -m dialogue_eval.cli run --task-source course_live_task --model deepseek --scenarios 15
```

对单条 trace 评分：

```powershell
uv run python -m dialogue_eval.cli score --trace path\\to\\trace.json
```

## API

常用接口：

```text
GET  /api/health
GET  /api/task-sources
POST /api/tasks
POST /api/tasks/upload
POST /api/tasks/{task_id}/scenarios
POST /api/eval-runs
POST /api/eval-runs/stream
POST /api/eval-runs/import
POST /api/eval-runs/import/stream
GET  /api/eval-runs/{run_id}
GET  /api/eval-runs/{run_id}/report
GET  /api/eval-runs/{run_id}/report.html
GET  /api/archives/runs
GET  /api/archives/groups
POST /api/eval-runs/{run_id}/analyze
POST /api/eval-runs/{run_id}/analyze/stream
POST /api/assistant/stream
```

## 输出结果

每次运行会生成：

- `runs/{run_id}/task.json`
- `runs/{run_id}/scenarios.json`
- `runs/{run_id}/trace.jsonl`
- `runs/{run_id}/results.json`
- `runs/{run_id}/report.md`
- `runs/{run_id}/report.html`
- `runs/{run_id}/<主题>测评报告YYYY-MM-DD-0001.md`
- `runs/{run_id}/<主题>测评报告YYYY-MM-DD-0001.html`
- `runs/{run_id}/report_meta.json`

报告标题示例：

```text
飞毛腿外呼测评报告2026/06/02/0001
```

## 测试

```powershell
uv run pytest
```

建议在本地测试时保持：

```env
ENABLE_LLM_JUDGE=false
```

这样可以避免对外部 judge 模型的额外依赖。

# Multi-turn Dialogue Evaluation

本项目是一个本地可运行的多轮外呼任务仿真评测工具，当前执行链路统一基于 DeepSeek / OpenAI-compatible 模型生成完整对话，再输出可追溯评测报告。

## 当前实现

- 任务输入支持本地 `JSON / Excel`
- 默认生成 15 个用户场景
- 统一走真实模型生成链路，不再保留本地 mock 执行分支
- 评测维度为 `Outcome / Trace / Safety / Text`
- 工具调用仍通过本地 MCP mock tools 模拟，评分时按 trace 做客观检查
- 历史索引写入 `runs/eval_archive.sqlite3`
- 运行明细写入 `runs/{run_id}/`
- 报告会同时生成固定文件 `report.md` / `report.html`，以及带主题和日期编号的正式文件名

## 环境准备

推荐 Python 3.12 或 3.13，依赖通过 `uv` 管理。

```powershell
uv sync
uv run python --version
```

说明：

- 不要提交 `.venv`、`.env`、`.uv-cache`
- 如果本机环境限制缓存写入，可使用 `.\scripts\uv.cmd ...`

## 配置

真实配置写入 `.env`，模板见 `.env.example`。

当前代码默认就是 DeepSeek 链路，关键配置如下：

```env
MODEL_PROVIDER=deepseek
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=你的模型 key
MODEL_NAME=deepseek-chat

JUDGE_MODEL_PROVIDER=deepseek
JUDGE_MODEL_BASE_URL=https://api.deepseek.com/v1
JUDGE_MODEL_API_KEY=你的 judge key
JUDGE_MODEL_NAME=deepseek-chat

DEEPSEEK_API_KEY=可选备用 key
RUNS_DIR=./runs
ARCHIVE_DB_PATH=./runs/eval_archive.sqlite3
ENABLE_LLM_JUDGE=false
SCENARIO_COUNT=15
MAX_TURNS=20
```

## 启动方式

推荐直接双击下面的启动脚本：

```text
scripts/start-deepseek-web.cmd
```

它会自动：

- 检查 `.env`
- 构建前端 `frontend/dist`
- 启动本地 FastAPI 服务
- 自动打开 `http://127.0.0.1:8000`

也可以手动启动：

```powershell
cd frontend
npm.cmd run build
cd ..
uv run python desktop_app.py
```

## CLI

运行内置 demo：

```powershell
uv run python -m dialogue_eval.cli demo
```

运行指定任务：

```powershell
uv run python -m dialogue_eval.cli run --task-source fengmaotui_delivery_task --model deepseek --scenarios 15
uv run python -m dialogue_eval.cli run --task-source course_live_task --model deepseek --scenarios 15
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
- `runs/eval_archive.sqlite3`

报告标题示例：

```text
飞毛腿外呼测评报告2026/06/02/0001
```

## API

常用接口：

```text
GET  /api/health
GET  /api/task-sources
POST /api/eval-runs
POST /api/eval-runs/stream
GET  /api/eval-runs/{run_id}
GET  /api/eval-runs/{run_id}/report
GET  /api/eval-runs/{run_id}/report.html
GET  /api/archives/runs
GET  /api/archives/groups
POST /api/eval-runs/{run_id}/analyze
POST /api/eval-runs/{run_id}/analyze/stream
POST /api/assistant/stream
```

## 测试

```powershell
uv run pytest
```

当前测试建议保持 `ENABLE_LLM_JUDGE=false`，避免额外依赖真实 judge 输出稳定性。

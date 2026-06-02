# 当前工程实现说明

## 1. 执行链路

当前代码统一走真实模型链路：

`任务解析 -> 场景生成 -> DeepSeekDialogueGenerator -> OpenAI-compatible API -> DialogueTrace -> ScorerSkill -> 报告生成 -> API/前端展示`

不再保留按 `model=mock` 切到本地 `MockAgent` / `DialogueRunner` 的执行分支。

## 2. 默认配置

```env
APP_ENV=local

MODEL_PROVIDER=deepseek
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_API_KEY=
MODEL_NAME=deepseek-chat

JUDGE_MODEL_PROVIDER=deepseek
JUDGE_MODEL_BASE_URL=https://api.deepseek.com/v1
JUDGE_MODEL_API_KEY=
JUDGE_MODEL_NAME=deepseek-chat

DEEPSEEK_API_KEY=

RUNS_DIR=./runs
ARCHIVE_DB_PATH=./runs/eval_archive.sqlite3
ENABLE_LLM_JUDGE=false
SCENARIO_COUNT=15
MAX_TURNS=20
```

## 3. 目录说明

核心目录：

- `dialogue_eval/`: 后端、评测、报告生成
- `frontend/`: Vue 前端
- `examples/tasks/`: 内置任务
- `runs/`: 本地运行结果
- `scripts/start-deepseek-web.cmd`: 推荐启动入口

## 4. 报告输出

每次运行会产出：

- 固定文件：`report.md`、`report.html`
- 正式命名文件：`<主题>测评报告YYYY-MM-DD-0001.md/.html`
- 元信息：`report_meta.json`

报告标题示例：

```text
飞毛腿外呼测评报告2026/06/02/0001
```

## 5. API

```text
GET  /api/health
GET  /api/task-sources
POST /api/tasks                  (当前仅支持 source_type=json)
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
POST /api/assistant/stream
```

## 6. 启动方式

推荐：

```text
scripts/start-deepseek-web.cmd
```

手动方式：

```powershell
cd frontend
npm.cmd run build
cd ..
uv run python desktop_app.py
```

## 7. 测试

```powershell
uv run pytest
```

当前最小回归重点：

- 任务源路径解析
- 报告标题和命名
- smoke test
- 报告 Markdown 结构

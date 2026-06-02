# Multi-turn Dialogue Evaluation

本项目是一个本地可运行的多轮外呼任务仿真评测工具。定位不是通用客服质检平台，而是面向复杂 AI 外呼任务上线前的压力测试：从任务说明生成多样用户场景，执行多轮对话，采集 transcript、tool trace、state trace，并输出可追溯评分报告。

## 当前主线

- 输入结构：`Role / Task / Opening Line / Call Flow / FAQ / Constraints`
- 默认生成不少于 15 个用户场景
- 评测维度：Outcome、Trace、Safety、Text
- 工具调用通过 MCP mock tools 模拟，评分时按 tool trace 客观检查
- 历史索引用本地 SQLite：`runs/eval_archive.sqlite3`
- 对话明细和报告保存在 `runs/{run_id}/`

## Python 环境

项目使用 `uv` 管理环境，推荐 Python 3.12 或 3.13。

首次进入项目时执行：

```powershell
uv sync
uv run python --version
```

说明：

- 不要把 `.venv` 一起提交或打包分发；虚拟环境应在目标机器上通过 `uv sync` 重建。
- 项目运行命令统一使用 `uv run ...`，不要直接依赖某台机器上的 `python.exe` 路径。
- `scripts/uv.cmd` 只是对 `uv` 的薄封装，直接用 `uv` 即可。
- 如果当前环境限制写入用户目录缓存，可改用 `.\scripts\uv.cmd ...`，它会把 `UV_CACHE_DIR` 固定到项目内的 `.uv-cache/`。

## 移植与分发

推荐分发这些文件：

- 源码目录
- `pyproject.toml`
- `uv.lock`
- `.env.example`
- `README.md`

不要分发这些本机产物：

- `.venv/`
- `.env`
- `.uv-cache/`
- `runs/` 下的运行结果

另一台机器拿到项目后的标准启动方式：

```powershell
uv sync
Copy-Item .env.example .env
uv run pytest
uv run python -m dialogue_eval.cli demo
```

## 配置

本地真实配置写入 `.env`，提交模板见 `.env.example`。

默认配置不依赖外部数据库，也不依赖真实模型，可以直接跑 mock demo。

```env
MODEL_PROVIDER=mock
RUNS_DIR=./runs
ARCHIVE_DB_PATH=./runs/eval_archive.sqlite3
ENABLE_LLM_JUDGE=false
SCENARIO_COUNT=15
MAX_TURNS=20
```

接入 DeepSeek 或其他 OpenAI-compatible 模型时再设置：

```env
MODEL_PROVIDER=deepseek
MODEL_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
DEEPSEEK_API_KEY=你的 key
```

## 稳定演示命令

优先使用 mock 模型验证完整闭环：

```powershell
uv run python -m dialogue_eval.cli demo
```

成功后会输出：

- `runs/{run_id}/task.json`
- `runs/{run_id}/scenarios.json`
- `runs/{run_id}/trace.jsonl`
- `runs/{run_id}/results.json`
- `runs/{run_id}/report.md`
- `runs/{run_id}/report.html`
- `runs/eval_archive.sqlite3`

运行指定任务：

```powershell
uv run python -m dialogue_eval.cli run --task-source fengmaotui_delivery_task --model mock --scenarios 15
uv run python -m dialogue_eval.cli run --task-source course_live_task --model mock --scenarios 15
```

启动 API：

```powershell
uv run uvicorn dialogue_eval.api.app:app --reload
```

常用接口：

```text
GET  http://127.0.0.1:8000/api/health
GET  http://127.0.0.1:8000/api/task-sources
POST http://127.0.0.1:8000/api/eval-runs
GET  http://127.0.0.1:8000/api/eval-runs/{run_id}
GET  http://127.0.0.1:8000/api/eval-runs/{run_id}/report
GET  http://127.0.0.1:8000/api/archives/runs
```

## 评分可信度

评分器是独立的 `ScorerSkill`，只消费 `TaskSpec`、`ScenarioSpec` 和 `DialogueTrace`。

- `OutcomeScorer`: 检查最终状态和必需流程覆盖。
- `TraceScorer`: 检查工具是否调用、参数是否匹配、返回是否成功、调用顺序是否正确。
- `SafetyScorer`: 检查禁用话术、隐私字段、越权和 prompt injection 风险。
- `TextJudgeScorer`: 按 20 分文本 rubric 检查自然度、轮次、长度和礼貌性；可选启用 LLM judge。

示例规则：用户要求转人工时，数字人必须先安抚/挽留一句，再调用 `transfer_to_human`。报告会展示对应轮次、规则、通过/失败结果和扣分原因。

## 测试

测试默认关闭 LLM judge，避免依赖外网和真实 API key：

```powershell
uv run pytest
```

## 打包为 EXE

可以，当前项目适合打成一个本地启动的桌面 `exe`：

- `exe` 启动后拉起本地 FastAPI 服务
- 自动打开浏览器到 `http://127.0.0.1:8000`
- 前端静态文件从打包内容里直接提供

打包前先构建前端：

```powershell
cd frontend
npm.cmd run build
cd ..
```

安装打包依赖：

```powershell
uv sync --extra build
```

单文件打包命令：

```powershell
uv run pyinstaller --noconfirm --onefile --name dialogue-eval ^
  --add-data "frontend/dist;frontend/dist" ^
  --collect-all uvicorn ^
  desktop_app.py
```

生成文件位置：

```text
dist/dialogue-eval.exe
```

双击 `dialogue-eval.exe` 后，会启动本地服务并自动打开网页。如果要改端口，可先设置环境变量 `DIALOGUE_EVAL_PORT`。

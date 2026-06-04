# 工程实现说明

## 1. 执行链路

### 主链路（自动场景 + LLM 模拟）

`
任务解析 (load_task)
  -> 场景生成 (generate_scenarios)
  -> LLM 对话生成 (DeepSeekDialogueGenerator)
  -> 四维评分 (ScorerSkill)
  -> 报告生成 (Markdown / HTML)
  -> 前端展示
`

### 导入链路（自动场景 + 已有对话）

`
上传 DialogueTrace JSON
  -> LLM 场景匹配 (match_scenario_with_llm)
  -> 四维评分 (ScorerSkill)
  -> 报告生成
  -> 前端展示
`

### 上传场景链路

`
上传场景 JSON (/scenarios/upload)
  + LLM 模拟 / 已有对话
  -> 四维评分
  -> 报告生成
`

## 2. 目录结构

### 后端 (dialogue_eval/)

| 模块 | 功能 |
|------|------|
| pi/app.py | FastAPI 应用入口 + CORS |
| pi/routes.py | 全部 API 路由（含 choose/stream 统一入口） |
| config.py | 配置项（模型、路径、阈值） |
| pipeline.py | 评测流水线（含 2x2x2 四种组合） |
| schemas.py | pydantic 数据模型 |
| 	ask_sources.py | 任务库扫描、上传、判重 |
| scenarios/generator.py | 场景模板生成 |
| scenarios/templates.py | 场景模板定义 |
| scorer/ | 四维评分器 |
| 
unner/deepseek_dialogue_generator.py | LLM 对话生成器 |
| 
unner/dialogue_runner.py | Mock 对话运行器 |
| mcp_gateway/ | 工具调用网关 + mock 工具 |
| models/ | Agent 模型接口 |
| parser/ | 任务文件解析（JSON/Excel） |

### 前端 (frontend/)

| 文件 | 功能 |
|------|------|
| src/App.vue | 三区块评测面板 |
| src/api/client.ts | API 客户端 |
| src/style.css | 样式 |

## 3. API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/task-sources | 任务列表 |
| POST | /api/tasks/upload | 上传任务 |
| POST | /api/scenarios/upload | 上传场景 |
| POST | /api/eval-runs/stream | LLM 模拟评测（SSE） |
| POST | /api/eval-runs/import/stream | 导入对话评测（SSE） |
| POST | /api/eval-runs/choose/stream | 2x2x2 统一评测入口 |
| GET | /api/eval-runs/{run_id}/report | 获取评测报告 |

## 4. 数据结构

### 数据文件

所有运行数据存储在 database/ 目录：

`
database/
  tasks/              # 任务 JSON 文件
  scenarios/          # 场景 JSON 文件（可单独上传）
  dialogues/          # 对话数据文件
  eval_archive.sqlite3 # 历史评测归档
  run_xxx/            # 单次评测产物
    task.json
    scenarios.json
    trace.jsonl
    results.json
    report.md / report.html
`

### 核心模型

- TaskSpec: 任务定义（角色、流程、FAQ、约束）
- ScenarioSpec: 场景定义（persona、期望工具、最终状态）
- ImportedScenarioSpec: 上传场景（与 ScenarioSpec 结构一致）
- DialogueTrace: 对话轨迹（transcript + tool_calls + state_trace）
- ImportedDialogueTrace: 导入对话轨迹
- ToolCallTrace: 工具调用轨迹

# 多轮外呼任务评测系统

面向多轮AI外呼坐席的本地评测平台。支持自动化场景生成、LLM驱动的对话模拟、四维评分，以及完整的 Markdown/HTML 报告输出。

## 架构：2x2 评测矩阵

两个正交维度的选择形成四种评测组合：

| 维度 | 选项 A | 选项 B |
|-----------|----------|----------|
| 场景来源 | 基于模板自动生成 | 上传场景 JSON |
| 对话来源 | LLM 模拟生成（DeepSeek） | 导入已有对话轨迹 |

\\mermaid
flowchart LR
    A[任务文件<br/>JSON / Excel] --> B{场景<br/>来源?}
    B -->|自动生成| C[自动生成<br/>场景列表]
    B -->|上传| D[上传场景<br/>JSON 文件]
    C --> E{对话<br/>来源?}
    D --> E
    E -->|LLM 模拟| F[LLM 模拟对话<br/>DeepSeek]
    E -->|导入数据| G[导入已有<br/>对话轨迹]
    G --> H[LLM 场景<br/>匹配识别]
    H --> I[四维<br/>评分]
    F --> I
    I --> J[Markdown / HTML<br/>报告生成]
    J --> K[(SQLite<br/>归档)]
\
## 评分维度（满分 100）

| 维度 | 满分 | 评估内容 |
|-----------|-----------|------------------|
| **Outcome（结果）** | 30 | 最终任务状态匹配 + 必要流程步骤覆盖 |
| **Trace（工具调用）** | 30 | 工具调用正确性：tool_name 与预期工具的精确匹配 |
| **Safety（安全合规）** | 20 | 禁用词检测 + 隐私字段泄露检测 |
| **Text（文本质量）** | 20 | 对话质量：语气自然度、简洁性（规则 + 可选 LLM 裁判） |

\\mermaid
flowchart TD
    subgraph ScorerSkill 评分引擎
        direction LR
        S[ScorerSkill.score] --> O[OutcomeScorer<br/>30 分]
        S --> T[TraceScorer<br/>30 分]
        S --> SF[SafetyScorer<br/>20 分]
        S --> TX[TextJudgeScorer<br/>20 分]
    end
    O --> AG[汇总决策]
    T --> AG
    SF --> AG
    TX --> AG
    AG --> R[EvalResult<br/>总分 + 通过/复核/不通过]
\
## 评测流水线

\\mermaid
sequenceDiagram
    participant UI as 前端 (Vue 3)
    participant API as FastAPI 路由
    participant PL as Pipeline 流水线
    participant SG as Scenario Generator 场景生成器
    participant DG as Dialogue Generator 对话生成器
    participant SC as ScorerSkill 评分引擎
    participant RP as Report Renderer 报告渲染

    UI->>API: POST /eval-runs/choose/stream
    API->>PL: run_choose_evaluation(task, scenario_mode, dialogue_mode)
    PL->>SG: generate_scenarios(task, count)
    SG-->>PL: List[ScenarioSpec]
    loop 遍历每个场景
        PL->>DG: runner.run(task, scenario)
        DG-->>PL: DialogueTrace
        PL->>SC: scorer.score(task, scenario, trace)
        SC-->>PL: EvalResult
    end
    PL->>RP: render_markdown_report / render_html_report
    RP-->>PL: Markdown + HTML 字符串
    PL-->>API: RunSummary
    API-->>UI: SSE 流式推送（阶段更新 + 完成通知）
\
## 技术栈

| 层级 | 技术 |
|-------|------------|
| 后端 | Python 3.13, FastAPI, Pydantic v2, Uvicorn |
| LLM 接口 | OpenAI-compatible API (DeepSeek) |
| LLM 裁判 | 可选：调用 DeepSeek 进行文本质量评分 |
| 前端 | Vue 3, TypeScript, Vite |
| 存储 | JSON 文件（运行产物） + SQLite（评测归档） |
| 包管理 | uv（Python）, npm（前端） |

## 快速开始

\\powershell
# 安装 Python 依赖
uv sync

# 构建前端
cd frontend; npm install; npm run build; cd ..

# 启动服务（自动打开浏览器 http://localhost:8000）
.venv\Scripts\python.exe desktop_app.py
\
## CLI 命令行使用

\\ash
# 使用内置任务运行演示评测
python main.py demo

# 使用指定任务文件运行评测
python main.py run --task database/tasks/飞毛腿任务.json --scenarios 10

# 对单条对话轨迹评分
python main.py score --trace path/to/trace.json
\
## API 接口一览

| 方法 | 路径 | 功能 |
|--------|------|-------------|
| GET | /api/health | 健康检查 |
| GET | /api/task-sources | 列出可用任务文件 |
| POST | /api/tasks/upload | 上传任务文件（JSON/Excel） |
| POST | /api/scenarios/upload | 上传场景 JSON |
| POST | /api/eval-runs/stream | LLM 模拟对话评测（SSE 流式） |
| POST | /api/eval-runs/import/stream | 导入对话评测（SSE 流式） |
| POST | /api/eval-runs/choose/stream | 2x2 统一评测入口（SSE 流式） |
| GET | /api/eval-runs/{run_id}/report | 获取评测报告（Markdown + HTML） |
| GET | /api/eval-runs/{run_id}/report.html | 以 HTML 页面渲染报告 |
| POST | /api/eval-runs/{run_id}/analyze | AI 分析报告（通过 LLM） |
| POST | /api/eval-runs/{run_id}/analyze/stream | 流式 AI 分析 |
| POST | /api/assistant/stream | 报告问答助手 |

## 项目结构

\database/                # 所有运行数据
  tasks/                 # 任务定义文件（JSON/Excel）
  scenarios/             # 场景数据文件
  dialogues/             # 对话数据文件
  eval_archive.sqlite3   # 历史评测归档
dialogue_eval/           # 后端核心
  api/                   # FastAPI 应用 + 路由
  scorer/                # 四维评分模块
  runner/                # 对话生成器（DeepSeek）
  mcp_gateway/           # 工具调用网关 + mock 工具
  scenarios/             # 场景模板和生成器
  models/                # LLM 模型接口（OpenAI 兼容）
  parser/                # 任务文件解析器（JSON/Excel）
  report/                # 报告渲染（Markdown/HTML）+ 分析
  simulator/             # 用户模拟器（mock 对话）
  storage/               # 运行存储 + 归档
frontend/                # Vue 3 单页应用
scripts/                 # 辅助脚本
tests/                   # 测试套件
\
## 核心数据模型

- **TaskSpec**：任务定义（角色、流程步骤、FAQ、约束、工具列表）
- **ScenarioSpec**：场景定义（用户画像、预期工具调用、最终状态、风险点）
- **DialogueTrace**：标准化对话轨迹（transcript + tool_calls + state_trace）
- **EvalResult**：单条对话评分结果（各维度得分 + 证据 + 最终判定）
- **RunSummary**：运行摘要（平均分、报告路径、匹配统计）

## 配置说明

所有设置在 dialogue_eval/config.py 中定义，通过 .env 文件配置：

| 变量 | 默认值 | 说明 |
|----------|---------|-------------|
| MODEL_BASE_URL | https://api.deepseek.com/v1 | LLM API 地址 |
| MODEL_NAME | deepseek-chat | 对话生成模型 |
| ENABLE_LLM_JUDGE | true | 启用 LLM 文本质量裁判 |
| SCENARIO_COUNT | 15 | 每次评测的场景数量 |
| MAX_TURNS | 20 | 最大对话轮次 |
| SCENARIO_MATCH_CONFIDENCE_THRESHOLD | 0.90 | 场景匹配最低置信度 |

复制 .env.example 为 .env 并填入你的 DEEPSEEK_API_KEY。

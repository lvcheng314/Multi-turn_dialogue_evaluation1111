# Multi-turn Dialogue Evaluation

本地可运行的多轮外呼任务评测工具。支持 2x2x2 评测模式：任务源 x 场景来源 x 对话来源。

## 架构：2x2x2

| 维度 | 选项 1 | 选项 2 |
|------|--------|--------|
| 任务源 | 任务库（database/tasks/） | 上传任务文件 |
| 场景来源 | 自动生成（模板） | 上传场景 JSON |
| 对话来源 | LLM 模拟生成 | 上传对话数据（DialogueTrace） |

四种评测组合：
- 自动场景 + LLM 模拟：完整评测链路
- 自动场景 + 已有对话：LLM 场景匹配 + 评分
- 上传场景 + LLM 模拟：自定义场景评测
- 上传场景 + 已有对话：直接匹配评分

## 评分维度

| 维度 | 满分 | 说明 |
|------|------|------|
| Outcome | 30 | 最终状态匹配 + 流程步骤覆盖 |
| Trace | 30 | tool_name 精确匹配 + 工具调用正确性 |
| Safety | 20 | 禁用词、隐私泄露检测 |
| Text | 20 | 语气自然度、对话质量 |

## 技术栈

- 后端：Python 3.13, FastAPI, pydantic, uvicorn
- 前端：Vue 3, TypeScript, Vite
- 模型接口：OpenAI-compatible API (DeepSeek)
- 数据存储：SQLite + JSON 文件（database/）
- 包管理：uv

## 快速开始

`powershell
# 安装依赖
uv sync

# 构建前端
cd frontend && npm install && npm run build && cd ..

# 启动服务
.venv\Scripts\python.exe desktop_app.py

# 浏览器访问 http://localhost:8000
`

## 项目结构

`
database/           # 所有运行数据
  tasks/            # 任务文件
  scenarios/        # 场景数据
  dialogues/        # 对话数据
  eval_archive.sqlite3  # 历史归档
dialogue_eval/      # 后端核心
  api/              # FastAPI 路由
  scorer/           # 四维评分
  runner/           # 对话生成器
  mcp_gateway/      # 工具调用网关
  scenarios/        # 场景模板
frontend/           # Vue 3 前端
scripts/            # 辅助脚本
tests/              # 测试

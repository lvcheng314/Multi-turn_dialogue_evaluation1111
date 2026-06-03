# 工程实现说明

## 1. 当前执行链路

当前代码主链路如下：

```text
任务解析 -> 场景生成 -> DeepSeekDialogueGenerator
-> OpenAI-compatible API -> DialogueTrace
-> ScorerSkill -> 报告生成 -> API / 前端展示
```

导入评测分支如下：

```text
上传 DialogueTrace JSON -> 自动匹配场景
-> ScorerSkill -> 报告生成 -> API / 前端展示
```

## 2. 当前目录

- `dialogue_eval/`
  - `api/`：FastAPI 应用与路由
  - `pipeline.py`：主评测流水线
  - `task_sources.py`：统一任务库扫描、上传、判重
  - `report/`：Markdown / HTML 报告生成与分析
  - `scorer/`：四个维度评分逻辑
  - `runner/deepseek_dialogue_generator.py`：真实模型对话生成
- `frontend/`
  - `src/App.vue`：主页交互
  - `src/api/client.ts`：前端 API 客户端
- `tasks/`
  - 当前项目的统一任务库目录
- `runs/`
  - 每次运行的产物与归档数据库

## 3. 当前任务库策略

- 示例任务与用户上传任务统一保存在 `tasks/`
- 上传前先做格式校验
- 格式错误时不会写入 `tasks/`
- 上传后按任务内容做重复检测
- 若项目内已有重复任务，前端提示是否直接复用历史文件

## 4. 当前前端交互

首页包含以下功能：

- 任务文件选择
- 任务文件上传
- 对话数据来源切换
  - 大模型生成模拟
  - 上传对话数据
- 聊天式报告助手
- 报告内嵌展示
- 历史归档查看

## 5. 当前 API

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

## 6. 启动方式

推荐入口：

```text
scripts/start-deepseek-web.cmd
```

该脚本会：

- 校验 `.env`
- 运行 `uv sync`
- 安装前端依赖（首次）
- 构建 `frontend/dist`
- 启动 `desktop_app.py`

## 7. 测试重点

当前应重点关注：

- 任务库路径与上传逻辑
- 上传对话数据导入评测
- 报告标题与 Markdown 结构
- 启动脚本与前端构建

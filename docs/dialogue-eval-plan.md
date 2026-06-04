# 当前方案

## 目标

一个可运行的多轮外呼任务评测工具，核心链路：

选择任务 -> 选择场景来源 + 对话来源 -> 评分 -> 生成报告

## 2x2x2 评测模式

| 场景来源  | 对话来源 | 说明 |
|----------|---------|------|
| 自动生成 | LLM 模拟 | 完整评测链路 |
| 自动生成 | 已有对话 | LLM 场景匹配 + 评分 |
| 上传场景 | LLM 模拟 | 自定义场景评测 |
| 上传场景 | 已有对话 | 直接按 scenario_id 匹配评分 |

## 评分维度

- Outcome (30分): 最终状态匹配 + 流程步骤关键词覆盖 + 回复轮次深度
- Trace (30分): tool_name 精确匹配 + 调用次数一致 + 转人工承接检查
- Safety (20分): 禁止词检测 + 隐私字段泄露检测
- Text (20分): 语气自然度、对话质量

## 执行流程

1. 加载任务文件 (database/tasks/)
2. 选择场景来源（自动生成 / 上传场景 JSON）
3. 选择对话来源（LLM 模拟 / 上传对话数据）
4. 四维评分
5. 生成 Markdown / HTML 报告
6. 历史归档 (database/eval_archive.sqlite3)

## 项目结构

- database/ - 任务、场景、对话、归档
- dialogue_eval/api/ - FastAPI 路由
- dialogue_eval/scorer/ - 四维评分器
- dialogue_eval/runner/ - 对话生成
- dialogue_eval/mcp_gateway/ - 工具网关
- frontend/ - Vue 3 前端

## 评分优化

对话生成提示词针对评分维度优化：
1. Trace: tool_name 必须精确等于期望工具名
2. Outcome: 末条 task_status 匹配 + 口头覆盖全部流程步骤 + >3轮 agent 回复
3. Safety: 禁止词和隐私字段绝不能出现
4. Text: 语气自然简短，电话口语风格

## 工具系统

- 6 个 MCP 工具
- 12 个行为工具
- 全部 18 个工具均有 mock 实现

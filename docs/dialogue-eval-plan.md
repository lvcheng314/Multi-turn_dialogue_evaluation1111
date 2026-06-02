# 多轮外呼测评工具当前方案

## 1. 当前目标

项目当前目标是交付一个基于真实 DeepSeek 链路运行的本地评测工具：

`选择任务 -> 生成场景 -> 调模型生成完整对话 -> 评分 -> 生成网页报告`

## 2. 当前主流程

```mermaid
flowchart TD
    A["任务源<br/>内置 task source / 自定义任务 / 本地 JSON / Excel"] --> B["load_task()<br/>解析 TaskSpec"]
    B --> C["generate_scenarios()<br/>生成 ScenarioSpec[]"]
    C --> D["run_evaluation()"]
    D --> E["DeepSeekDialogueGenerator"]
    E --> F["OpenAI-compatible Chat API"]
    F --> G["DialogueTrace"]
    G --> H["ScorerSkill"]
    H --> I["EvalResult"]
    I --> J["Markdown / HTML 报告"]
    J --> K["runs/{run_id}/"]
    I --> L["SQLite 归档"]
    J --> M["FastAPI / Vue 展示"]
```

## 3. 当前约束

- 不再保留本地 mock 执行分支
- 工具层仍然使用本地 mock tools，便于稳定评测工具调用流程
- 报告命名使用“测评主题 + 日期 + 四位编号”
- 前端展示基于 `frontend/dist`
- 推荐启动方式是 `scripts/start-deepseek-web.cmd`

## 4. 当前交付重点

- 保证 `.env` 正确时可以直接启动网页
- 保证两个内置任务源可运行
- 保证报告中文正常显示
- 保证报告标题、分项汇总、证据明细符合当前实现
- 保证归档和历史查询可用

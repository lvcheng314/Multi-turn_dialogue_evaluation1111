<script setup lang="ts">
import { onMounted } from "vue"
import { useEval } from "./composables/useEval"
import { renderMarkdown } from "./utils/markdown"

const {
  activeRunId,
  askAnalysis,
  askAssistant,
  bot,
  botStreaming,
  busy,
  canRun,
  customText,
  dialogueMode,
  handleDownloadTemplate,
  handleUploadedTask,
  loadArchives,
  messages,
  messagesContainer,
  onScenarioPicked,
  onTaskPicked,
  onTracePicked,
  openScenarioPicker,
  openTaskPicker,
  openTracePicker,
  refreshTasks,
  runChoose,
  runGenerated,
  runHint,
  runImported,
  scenarioFile,
  scenarioInput,
  scenarioMode,
  scrollToBottom,
  selectedTask,
  selectedTaskId,
  sendCustom,
  showReport,
  startEvaluation,
  statusText,
  taskInput,
  taskSources,
  traceFile,
  traceInput,
  user
} = useEval()

onMounted(async () => {
  await refreshTasks()
  bot("请选择任务库中的任务文件，并指定对话数据来源。我可以继续负责任务说明、开场提示以及报告分析。")
})
</script>

<template>
  <main class="chat-shell">
    <section class="chat-panel">
      <header class="chat-header">
        <div>
          <h1>Dialogue Eval Bot</h1>
          <p>任务库驱动的多轮外呼任务评测</p>
        </div>
        <button class="ghost" @click="loadArchives">归档</button>
      </header>

      <section class="workspace">
        <div class="workspace-card workspace-card-task">
          <div class="workspace-heading">
            <span class="workspace-kicker">Task Library</span>
            <h2>任务模块</h2>
            <p>统一任务库位于项目 `tasks/` 目录。可直接选择已有任务，或上传新的任务文件。</p>
          </div>
          <div class="task-controls">
            <div class="select-shell">
              <label class="field-label" for="task-select">任务文件</label>
              <select id="task-select" v-model="selectedTaskId" :disabled="busy || !taskSources.length">
                <option value="">请选择任务文件</option>
                <option v-for="source in taskSources" :key="source.id" :value="source.id">
                  {{ source.file_name }}
                </option>
              </select>
            </div>
            <button class="secondary-action" @click="openTaskPicker" :disabled="busy">上传任务文件</button>
            <button class="secondary-action" @click="handleDownloadTemplate" :disabled="busy">下载 JSON 模板</button>
          </div>
          <div v-if="selectedTask" class="task-summary">
            <div class="task-summary-main">
              <span class="meta-pill meta-pill-strong">{{ selectedTask.file_name }}</span>
              <h3>{{ selectedTask.name }}</h3>
            </div>
            <div class="task-summary-grid">
              <div class="summary-block">
                <span class="summary-label">任务 ID</span>
                <span class="summary-value">{{ selectedTask.id }}</span>
              </div>
              <div class="summary-block">
                <span class="summary-label">任务目录</span>
                <span class="summary-value">{{ selectedTask.path }}</span>
              </div>
            </div>
          </div>
        </div>

                <div class="workspace-card workspace-card-scenario">
          <div class="workspace-heading">
            <span class="workspace-kicker">Simulation Panel</span>
            <h2>模拟场景板块</h2>
            <p>按 2x2x2 模式选择：先定任务源，再选场景来源，最后选对话数据来源。</p>
          </div>
          <div class="subsection">
            <h3 class="subsection-title">01 场景来源</h3>
            <div class="mode-row">
              <label class="mode-card" :class="{ active: scenarioMode === 'generate' }">
                <input v-model="scenarioMode" type="radio" value="generate" :disabled="busy" />
                <div class="mode-card-body">
                  <span class="mode-title">自动生成场景</span>
                  <small class="mode-copy">从模板自动生成测试场景</small>
                </div>
              </label>
              <label class="mode-card" :class="{ active: scenarioMode === 'upload' }">
                <input v-model="scenarioMode" type="radio" value="upload" :disabled="busy" />
                <div class="mode-card-body">
                  <span class="mode-title">上传场景文件</span>
                  <small class="mode-copy">使用已有场景 JSON</small>
                </div>
              </label>
            </div>
            <div v-if="scenarioMode === 'upload'" class="upload-panel">
              <div class="upload-copy">
                <span class="upload-label">场景文件</span>
                <span class="hint">{{ scenarioFile ? scenarioFile.name : '未选择场景 JSON' }}</span>
              </div>
              <button class="secondary-action" @click="openScenarioPicker" :disabled="busy">选择场景文件</button>
            </div>
          </div>
          <div class="subsection">
            <h3 class="subsection-title">02 对话数据来源</h3>
            <div class="mode-row">
              <label class="mode-card" :class="{ active: dialogueMode === 'generate' }">
                <input v-model="dialogueMode" type="radio" value="generate" :disabled="busy" />
                <div class="mode-card-body">
                  <span class="mode-title">LLM 模拟</span>
                  <small class="mode-copy">大模型逐次生成模拟对话</small>
                </div>
              </label>
              <label class="mode-card" :class="{ active: dialogueMode === 'import' }">
                <input v-model="dialogueMode" type="radio" value="import" :disabled="busy" />
                <div class="mode-card-body">
                  <span class="mode-title">已有对话数据</span>
                  <small class="mode-copy">上传 DialogueTrace JSON</small>
                </div>
              </label>
            </div>
            <div v-if="dialogueMode === 'import'" class="upload-panel">
              <div class="upload-copy">
                <span class="upload-label">对话数据文件</span>
                <span class="hint">{{ traceFile ? traceFile.name : '未选择对话数据 JSON' }}</span>
              </div>
              <button class="secondary-action" @click="openTracePicker" :disabled="busy">选择对话文件</button>
            </div>
          </div>
          <div class="action-bar">
            <button class="primary" @click="startEvaluation" :disabled="busy || !canRun">
              {{ busy ? '处理中...' : '开始评测' }}
            </button>
            <span class="action-hint">{{ runHint }}</span>
          </div>
        </div>
      </section>

      <div ref="messagesContainer" class="messages">
        <article
          v-for="message in messages"
          :key="message.id"
          class="message"
          :class="message.role"
        >
          <div class="avatar" :class="`avatar-${message.role}`" aria-hidden="true">
            {{ message.role === 'bot' ? '评' : '我' }}
          </div>
          <div class="bubble">
            <div v-if="message.text" class="message-body markdown-body" v-html="renderMarkdown(message.text)"></div>
            <div v-if="message.actions?.length" class="actions">
              <button
                v-for="action in message.actions"
                :key="action.label"
                @click="action.run"
              >
                {{ action.label }}
              </button>
            </div>
            <iframe
              v-if="message.reportHtml"
              class="inline-report"
              title="评测报告"
              :srcdoc="message.reportHtml"
            ></iframe>
          </div>
        </article>
      </div>

      <div v-if="statusText" class="status-line" role="status" aria-live="polite">
        {{ statusText }}
      </div>

      <form class="composer" @submit.prevent="sendCustom">
        <textarea
          v-model="customText"
          placeholder="和报告助手对话，咨询任务说明、开场提示或报告分析"
          rows="3"
          @keydown.enter.exact.prevent="sendCustom"
        />
        <button :disabled="busy">{{ busy ? '处理中' : '发送' }}</button>
      </form>
    </section>
    <input ref="taskInput" type="file" accept=".json,.xlsx,.xls" hidden @change="onTaskPicked" />
    <input ref="scenarioInput" type="file" accept=".json" hidden @change="onScenarioPicked" />
    <input ref="traceInput" type="file" accept=".json" hidden @change="onTracePicked" />
  </main>
</template>

<style>
/* inherited from global style.css */
</style>
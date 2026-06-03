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

        <div class="workspace-card workspace-card-mode">
          <div class="workspace-heading">
            <span class="workspace-kicker">Conversation Source</span>
            <h2>对话数据模块</h2>
            <p>选择由大模型生成模拟对话，或直接上传真实 `DialogueTrace JSON` 做导入评测。</p>
          </div>
          <div class="mode-grid">
            <label class="mode-option" :class="{ active: dataMode === 'generated' }">
              <div class="mode-option-top">
                <input v-model="dataMode" type="radio" value="generated" :disabled="busy" />
                <span class="mode-title">大模型生成模拟</span>
              </div>
              <small class="mode-copy">保持现有完整评测流程，自动生成场景对话并出报告。</small>
            </label>
            <label class="mode-option" :class="{ active: dataMode === 'uploaded' }">
              <div class="mode-option-top">
                <input v-model="dataMode" type="radio" value="uploaded" :disabled="busy" />
                <span class="mode-title">上传对话数据</span>
              </div>
              <small class="mode-copy">导入已有 `DialogueTrace JSON`，直接评分并生成评测报告。</small>
            </label>
          </div>
          <div v-if="dataMode === 'uploaded'" class="upload-panel">
            <div class="upload-copy">
              <span class="upload-label">对话数据文件</span>
              <span class="hint">{{ traceFile ? traceFile.name : '未选择 DialogueTrace JSON（单条或 100 条以内数组）' }}</span>
            </div>
            <button class="secondary-action" @click="openTracePicker" :disabled="busy">选择对话文件</button>
          </div>
          <div class="action-bar">
            <button class="primary" @click="startEvaluation" :disabled="busy || !canRun">
              {{ busy ? '处理中' : (dataMode === 'generated' ? '开始模拟评测' : '开始导入评测') }}
            </button>
            <span class="action-hint">{{ dataMode === 'generated' ? '将调用 DeepSeek 生成模拟对话' : '将直接评分你上传的对话数据' }}</span>
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
            <div v-if="message.text" class="message-body markdown-body" v-html="renderMessageHtml(message.text)"></div>
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
    <input ref="traceInput" type="file" accept=".json" hidden @change="onTracePicked" />
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  getReport,
  listArchiveGroups,
  listTaskSources,
  streamAnalyzeRun,
  streamAssistant,
  streamImportedRun,
  streamRun,
  uploadTaskFile,
  type TaskSource,
  type UploadTaskResult,
} from './api/client'

type Message = {
  id: number
  role: 'bot' | 'user'
  text: string
  reportHtml?: string
  actions?: Array<{ label: string; run: () => void }>
}

const messages = ref<Message[]>([])
const taskSources = ref<TaskSource[]>([])
const selectedTaskId = ref('')
const dataMode = ref<'generated' | 'uploaded'>('generated')
const traceFile = ref<File | null>(null)
const customText = ref('')
const busy = ref(false)
const activeRunId = ref('')
const statusText = ref('')
const taskInput = ref<HTMLInputElement | null>(null)
const traceInput = ref<HTMLInputElement | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
let nextId = 1

const selectedTask = computed(() => taskSources.value.find((item) => item.id === selectedTaskId.value) || null)
const canRun = computed(() => {
  if (!selectedTaskId.value) return false
  if (dataMode.value === 'uploaded') return Boolean(traceFile.value)
  return true
})

function escapeHtml(text: string) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(text: string) {
  let html = escapeHtml(text)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_match: string, label: string, href: string) => {
    const safeHref = href.replace(/"/g, '%22')
    return `<a href="${safeHref}" target="_blank" rel="noreferrer">${label}</a>`
  })
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
  return html
}

function renderMarkdownTable(rows: string[][]) {
  if (!rows.length) return ''
  const [header, ...body] = rows
  return [
    '<table>',
    '<thead><tr>',
    ...header.map((cell) => `<th>${renderInlineMarkdown(cell.trim())}</th>`),
    '</tr></thead>',
    '<tbody>',
    ...body.map((row) => [
      '<tr>',
      ...row.map((cell) => `<td>${renderInlineMarkdown(cell.trim())}</td>`),
      '</tr>',
    ].join('')),
    '</tbody>',
    '</table>',
  ].join('')
}

function renderMessageHtml(text: string) {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (!normalized) return ''

  const lines = normalized.split('\n')
  const blocks: string[] = []
  let paragraph: string[] = []
  let bulletItems: string[] | null = null
  let orderedItems: string[] | null = null
  let quoteLines: string[] | null = null
  let tableLines: string[] | null = null
  let inCodeBlock = false
  let codeLang = ''
  let codeLines: string[] = []

  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push(`<p>${paragraph.map((line) => renderInlineMarkdown(line)).join('<br>')}</p>`)
    paragraph = []
  }

  const flushBullets = () => {
    if (!bulletItems?.length) return
    blocks.push(`<ul>${bulletItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</ul>`)
    bulletItems = null
  }

  const flushOrdered = () => {
    if (!orderedItems?.length) return
    blocks.push(`<ol>${orderedItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</ol>`)
    orderedItems = null
  }

  const flushQuote = () => {
    if (!quoteLines?.length) return
    blocks.push(`<blockquote><p>${quoteLines.map((line) => renderInlineMarkdown(line)).join('<br>')}</p></blockquote>`)
    quoteLines = null
  }

  const flushTable = () => {
    if (!tableLines?.length || tableLines.length < 2) {
      tableLines = null
      return
    }
    const rawRows = tableLines
      .filter((_line, index) => index !== 1)
      .map((line) => line.split('|').slice(1, -1))
    blocks.push(renderMarkdownTable(rawRows))
    tableLines = null
  }

  const flushAll = () => {
    flushParagraph()
    flushBullets()
    flushOrdered()
    flushQuote()
    flushTable()
  }

  for (const line of lines) {
    if (line.startsWith('```')) {
      flushAll()
      if (inCodeBlock) {
        const languageAttr = codeLang ? ` data-lang="${escapeHtml(codeLang)}"` : ''
        blocks.push(
          `<pre class="md-code"${languageAttr}><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`,
        )
        inCodeBlock = false
        codeLang = ''
        codeLines = []
      } else {
        inCodeBlock = true
        codeLang = line.slice(3).trim()
      }
      continue
    }

    if (inCodeBlock) {
      codeLines.push(line)
      continue
    }

    if (!line.trim()) {
      flushAll()
      continue
    }

    if (/^\|.+\|$/.test(line.trim())) {
      flushParagraph()
      flushBullets()
      flushOrdered()
      flushQuote()
      tableLines ??= []
      tableLines.push(line.trim())
      continue
    }

    if (tableLines && /^(\|\s*[-:]+\s*)+\|$/.test(line.trim())) {
      tableLines.push(line.trim())
      continue
    }

    if (tableLines) {
      flushTable()
    }

    const headingMatch = line.match(/^(#{1,3})\s+(.+)$/)
    if (headingMatch) {
      flushAll()
      const level = headingMatch[1].length
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2].trim())}</h${level}>`)
      continue
    }

    const quoteMatch = line.match(/^>\s?(.*)$/)
    if (quoteMatch) {
      flushParagraph()
      flushBullets()
      flushOrdered()
      quoteLines ??= []
      quoteLines.push(quoteMatch[1])
      continue
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/)
    if (bulletMatch) {
      flushParagraph()
      flushOrdered()
      flushQuote()
      bulletItems ??= []
      bulletItems.push(bulletMatch[1].trim())
      continue
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/)
    if (orderedMatch) {
      flushParagraph()
      flushBullets()
      flushQuote()
      orderedItems ??= []
      orderedItems.push(orderedMatch[1].trim())
      continue
    }

    paragraph.push(line.trim())
  }

  if (inCodeBlock) {
    const languageAttr = codeLang ? ` data-lang="${escapeHtml(codeLang)}"` : ''
    blocks.push(
      `<pre class="md-code"${languageAttr}><code>${escapeHtml(codeLines.join('\n'))}</code></pre>`,
    )
  } else {
    flushAll()
  }

  return blocks.join('')
}

onMounted(async () => {
  await refreshTasks()
  bot('请选择任务库中的任务文件，并指定对话数据来源。我可以继续负责任务说明、开场提示以及报告分析。')
})

function scrollToBottom() {
  void nextTick(() => {
    const container = messagesContainer.value
    if (!container) return
    container.scrollTop = container.scrollHeight
  })
}

function bot(text: string, actions?: Message['actions'], reportHtml?: string) {
  messages.value.push({ id: nextId++, role: 'bot', text, actions, reportHtml })
  scrollToBottom()
}

function botStreaming(): Message {
  const message = { id: nextId++, role: 'bot' as const, text: '' }
  messages.value.push(message)
  scrollToBottom()
  return message
}

function user(text: string) {
  messages.value.push({ id: nextId++, role: 'user', text })
  scrollToBottom()
}

async function refreshTasks() {
  taskSources.value = await listTaskSources()
  if (!selectedTaskId.value && taskSources.value.length) {
    selectedTaskId.value = taskSources.value[0].id
  }
}

function openTaskPicker() {
  taskInput.value?.click()
}

function openTracePicker() {
  traceInput.value?.click()
}

async function onTaskPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  try {
    const uploaded = await uploadTaskFile(file)
    await handleUploadedTask(file.name, uploaded)
  } catch (err) {
    bot(err instanceof Error ? err.message : String(err))
  } finally {
    busy.value = false
    input.value = ''
  }
}

function onTracePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  traceFile.value = file
  if (file) {
    bot(`已选择对话数据文件：${file.name}`)
  }
  input.value = ''
}

async function handleUploadedTask(originalFileName: string, uploaded: UploadTaskResult) {
  if (uploaded.status === 'duplicate') {
    const confirmed = window.confirm(
      `${uploaded.message || '项目内已有相同任务文件。'}\n已有文件：${uploaded.file_name}\n点击“确定”将直接使用项目内历史任务文件。`,
    )
    if (!confirmed) {
      bot(`未复用历史任务文件：${originalFileName}`)
      return
    }
    selectedTaskId.value = uploaded.task_id
    bot(`检测到重复任务文件，已直接使用项目内历史任务：${uploaded.file_name}\n任务名称：${uploaded.task_name}`)
    return
  }

  await refreshTasks()
  selectedTaskId.value = uploaded.task_id
  bot(`任务文件已加入任务库：${uploaded.file_name}\n任务名称：${uploaded.task_name}`)
}

async function startEvaluation() {
  if (!selectedTask.value || busy.value) return
  if (dataMode.value === 'uploaded' && !traceFile.value) return
  if (dataMode.value === 'generated') {
    await runGenerated()
    return
  }
  await runImported()
}

async function runGenerated() {
  if (!selectedTask.value) return
  busy.value = true
  user(`开始模拟评测：${selectedTask.value.file_name}`)
  try {
    await streamRun(
      { task_id: selectedTask.value.id },
      {
        onStage: (payload) => {
          statusText.value = String(payload.message || '')
        },
        onComplete: async (summary) => {
          activeRunId.value = summary.run_id
          statusText.value = '正在加载评测报告...'
          await showReport(summary)
        },
      },
    )
  } catch (err) {
    statusText.value = ''
    bot(err instanceof Error ? err.message : String(err))
  } finally {
    statusText.value = ''
    busy.value = false
  }
}

async function runImported() {
  if (!selectedTask.value || !traceFile.value) return
  busy.value = true
  user(`导入对话评测：${selectedTask.value.file_name}\n对话文件：${traceFile.value.name}`)
  try {
    await streamImportedRun(
      { task_id: selectedTask.value.id, traceFile: traceFile.value },
      {
        onStage: (payload) => {
          statusText.value = String(payload.message || '')
        },
        onComplete: async (summary) => {
          activeRunId.value = summary.run_id
          statusText.value = '正在加载评测报告...'
          await showReport(summary)
        },
      },
    )
  } catch (err) {
    statusText.value = ''
    bot(err instanceof Error ? err.message : String(err))
  } finally {
    statusText.value = ''
    busy.value = false
  }
}

async function sendCustom() {
  const text = customText.value.trim()
  if (!text || busy.value) return
  customText.value = ''
  user(text)
  await askAssistant()
}

async function askAnalysis(question: string) {
  if (!activeRunId.value) {
    bot('还没有可分析的报告，请先运行一次评测。')
    return
  }
  busy.value = true
  const answer = botStreaming()
  try {
    await streamAnalyzeRun(activeRunId.value, question, {
      onStage: (payload) => {
        statusText.value = String(payload.message || '')
      },
      onDelta: (text) => {
        answer.text += text
        scrollToBottom()
      },
      onComplete: () => {
        statusText.value = ''
      },
    })
  } catch (err) {
    statusText.value = ''
    answer.text = err instanceof Error ? err.message : String(err)
  } finally {
    statusText.value = ''
    busy.value = false
  }
}

async function askAssistant() {
  busy.value = true
  const answer = botStreaming()
  const history = messages.value
    .filter((message) => message.text && !message.reportHtml)
    .slice(-12)
    .map((message) => ({
      role: message.role,
      content: message.text,
    }))
  try {
    await streamAssistant(
      {
        messages: history,
        active_run_id: activeRunId.value || undefined,
      },
      {
        onStage: (payload) => {
          statusText.value = String(payload.message || '')
        },
        onDelta: (text) => {
          answer.text += text
          scrollToBottom()
        },
        onComplete: () => {
          statusText.value = ''
        },
      },
    )
  } catch (err) {
    statusText.value = ''
    answer.text = err instanceof Error ? err.message : String(err)
  } finally {
    statusText.value = ''
    busy.value = false
  }
}

async function showReport(summary: {
  run_id: string
  total_score: number
  report_markdown_path: string
}) {
  const report = await getReport(summary.run_id)
  statusText.value = ''
  bot(
    `评测报告已生成。\nrun_id: ${summary.run_id}\n总分: ${summary.total_score}\n报告文件: ${summary.report_markdown_path}`,
    [
      { label: '查看评测报告', run: () => window.open(`/api/eval-runs/${summary.run_id}/report.html`, '_blank') },
      { label: '分析低分原因', run: () => askAnalysis('分析低分原因') },
      { label: '查看风险点', run: () => askAnalysis('查看风险点') },
      { label: '生成优化建议', run: () => askAnalysis('生成优化建议') },
      { label: '对比历史报告', run: () => askAnalysis('对比历史报告') },
    ],
    report.report_html,
  )
}

async function loadArchives() {
  const groups = await listArchiveGroups()
  if (!groups.length) {
    bot('当前还没有归档记录。')
    return
  }
  bot(groups.map((group) => (
    `${group.task_name}\n模型: ${group.model_name}，次数: ${group.run_count}，均分: ${Number(group.avg_score).toFixed(2)}，最高: ${Number(group.best_score).toFixed(2)}`
  )).join('\n\n'))
}
</script>

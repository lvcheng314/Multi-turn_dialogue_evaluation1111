<template>
  <main class="chat-shell">
    <section class="chat-panel">
      <header class="chat-header">
        <div>
          <h1>Dialogue Eval Bot</h1>
          <p>多轮外呼任务评测</p>
        </div>
        <button class="ghost" @click="loadArchives">归档</button>
      </header>

      <div class="messages">
        <article
          v-for="message in messages"
          :key="message.id"
          class="message"
          :class="message.role"
        >
          <div class="bubble">
            <p v-for="line in message.text.split('\n')" :key="line">{{ line }}</p>
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
          placeholder="和 AI 助手对话，或点击上方任务按钮开始评测"
          rows="3"
        />
        <button :disabled="busy">{{ busy ? '处理中' : '发送' }}</button>
      </form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  getReport,
  listArchiveGroups,
  listTaskSources,
  streamAnalyzeRun,
  streamAssistant,
  streamRun,
  type TaskSource,
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
const customText = ref('')
const busy = ref(false)
const activeRunId = ref('')
const statusText = ref('')
let nextId = 1

onMounted(async () => {
  taskSources.value = await listTaskSources()
  bot('请选择要测试的指令任务，或直接向我提问。我可以解释任务、分析报告、给出优化建议。', taskSources.value.map((source) => ({
    label: source.name,
    run: () => runTask(source.id, source.name),
  })))
})

function bot(text: string, actions?: Message['actions'], reportHtml?: string) {
  messages.value.push({ id: nextId++, role: 'bot', text, actions, reportHtml })
}

function botStreaming(): Message {
  const message = { id: nextId++, role: 'bot' as const, text: '' }
  messages.value.push(message)
  return message
}

function user(text: string) {
  messages.value.push({ id: nextId++, role: 'user', text })
}

async function runTask(taskId: string, label: string) {
  if (busy.value) return
  busy.value = true
  user(`测试任务：${label}`)
  try {
    await streamRun(
      { task_id: taskId },
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
  bot(`你还想继续分析这份报告吗？可以直接提问，例如：为什么分数低、哪些场景风险高、怎么优化任务指令。`)
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

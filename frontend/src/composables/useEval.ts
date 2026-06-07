import { computed, nextTick, ref } from "vue"
import type { ArchiveGroup, RunSummary, TaskSource, UploadTaskResult } from "../api/client"
import {
  downloadDialogueTemplate,
  downloadScenarioTemplate,
  downloadTaskTemplate, getReport, listArchiveGroups, listTaskSources,
  streamAnalyzeRun, streamAssistant, streamChooseRun, streamImportedRun,
  streamRun, uploadTaskFile,
} from "../api/client"

export interface Message {
  id: number
  role: "bot" | "user"
  text: string
  reportHtml?: string
  actions?: Array<{ label: string; run: () => void }>
}

export function useEval() {

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
const scenarioMode = ref<'generate' | 'upload'>('generate')
const dialogueMode = ref<'generate' | 'import'>('generate')
const scenarioFile = ref<File | null>(null)
const traceFile = ref<File | null>(null)
const customText = ref('')
const busy = ref(false)
const activeRunId = ref('')
const statusText = ref('')
const taskInput = ref<HTMLInputElement | null>(null)
const scenarioInput = ref<HTMLInputElement | null>(null)
const traceInput = ref<HTMLInputElement | null>(null)
const messagesContainer = ref<HTMLElement | null>(null)
let nextId = 1

const selectedTask = computed(() => taskSources.value.find((item: TaskSource) => item.id === selectedTaskId.value) || null)
const canRun = computed(() => {
  if (!selectedTaskId.value) return false
  if (scenarioMode.value === 'upload' && !scenarioFile.value) return false
  if (dialogueMode.value === 'import' && !traceFile.value) return false
  return true
})

const runHint = computed(() => {
  const combos: Record<string, string> = {
    'generate_generate': '自动场景 + LLM 模拟对话',
    'generate_import': '自动场景 + 已有对话数据',
    'upload_generate': '上传场景 + LLM 模拟对话',
    'upload_import': '上传场景 + 已有对话数据',
  }
  return combos[`${scenarioMode.value}_${dialogueMode.value}`] || ''
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

async function handleDownloadTemplate() {
  try {
    await downloadTaskTemplate()
    bot('已开始下载任务模板：任务模板.json')
  } catch (err) {
    bot(err instanceof Error ? err.message : String(err))
  }
}

function openTracePicker() {
  traceInput.value?.click()
}

async function handleDownloadScenarioTemplate() {
  try {
    await downloadScenarioTemplate()
    bot('已开始下载场景 JSON 示例文件。')
  } catch (err) {
    bot(err instanceof Error ? err.message : String(err))
  }
}

async function handleDownloadDialogueTemplate() {
  try {
    await downloadDialogueTemplate()
    bot('已开始下载对话数据 JSON 示例文件。')
  } catch (err) {
    bot(err instanceof Error ? err.message : String(err))
  }
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

function onScenarioPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  scenarioFile.value = file
  if (file) {
    bot(`已选择场景文件：${file.name}`)
  }
  input.value = ''
}

function openScenarioPicker() {
  scenarioInput.value?.click()
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
      `${uploaded.message || '项目内已存在相同任务文件。'}\n已有文件：${uploaded.file_name}\n点击“确定”将直接使用项目内历史任务文件。`,
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
  if (scenarioMode.value === 'upload' && !scenarioFile.value) return
  if (dialogueMode.value === 'import' && !traceFile.value) return

  if (scenarioMode.value === 'generate' && dialogueMode.value === 'generate') {
    await runGenerated()
  } else if (scenarioMode.value === 'generate' && dialogueMode.value === 'import') {
    await runImported()
  } else {
    await runChoose()
  }
}

async function runGenerated() {
  if (!selectedTask.value) return
  busy.value = true
  user(`开始模拟评测：${selectedTask.value.file_name}`)
  try {
    await streamRun(
      { task_id: selectedTask.value.id },
      {
        onStage: (payload: { message?: string; stage?: string; [key: string]: unknown }) => {
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
        onStage: (payload: { message?: string; stage?: string; [key: string]: unknown }) => {
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
  user(question)
  busy.value = true
  const answer = botStreaming()
  try {
    await streamAnalyzeRun(activeRunId.value, question, {
      onStage: (payload: { message?: string; stage?: string; [key: string]: unknown }) => {
        statusText.value = String(payload.message || '')
      },
      onDelta: (text: string) => {
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

async function runChoose() {
  if (!selectedTask.value) return
  busy.value = true
  const scenarioLabel = scenarioFile.value ? `场景：${scenarioFile.value.name}` : '上传场景'
  const dialogueLabel = traceFile.value ? `对话：${traceFile.value.name}` : 'LLM 模拟'
  user(`开始评测（2x2x2）：${selectedTask.value.file_name}\n${scenarioLabel}\n${dialogueLabel}`)
  try {
    await streamChooseRun(
      {
        task_id: selectedTask.value.id,
        scenario_mode: scenarioMode.value,
        dialogue_mode: dialogueMode.value,
        scenarioFile: scenarioFile.value || undefined,
        traceFile: traceFile.value || undefined,
      },
      {
        onStage: (payload: { message?: string; stage?: string; [key: string]: unknown }) => {
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
        onStage: (payload: { message?: string; stage?: string; [key: string]: unknown }) => {
          statusText.value = String(payload.message || '')
        },
        onDelta: (text: string) => {
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
  bot(groups.map((group: ArchiveGroup) => (
    `${group.task_name}\n模型: ${group.model_name}，次数: ${group.run_count}，均分: ${Number(group.avg_score).toFixed(2)}，最高: ${Number(group.best_score).toFixed(2)}`
  )).join('\n\n'))
}
  return {
    activeRunId,
  askAnalysis,
  askAssistant,
  bot,
  botStreaming,
  busy,
  canRun,
  customText,
  dialogueMode,
  handleDownloadDialogueTemplate,
  handleDownloadScenarioTemplate,
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
  }
}

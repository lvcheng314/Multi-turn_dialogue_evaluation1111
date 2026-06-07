export type RunSummary = {
  run_id: string
  status: string
  completed_dialogues: number
  scenario_count: number
  total_score: number
  report_markdown_path: string
  report_html_path: string
}

export type TaskSource = {
  id: string
  name: string
  file_name: string
  path: string
}

export type UploadTaskResult = {
  status: 'stored' | 'duplicate'
  message?: string
  task_id: string
  task_name: string
  file_name: string
  path: string
  scenario_count: number | null
  duplicate_of: TaskSource | null
}

export type ReportPayload = {
  run_id: string
  total_score: number
  report_markdown: string
  report_html: string
  report_html_path: string
}

export type ArchiveGroup = {
  group_id: string
  task_id: string
  task_name: string
  model_name: string
  latest_run_id: string
  run_count: number
  best_score: number
  avg_score: number
  updated_at: string
}

export async function listTaskSources(): Promise<TaskSource[]> {
  const response = await fetch('/api/task-sources')
  if (!response.ok) {
    throw new Error(await response.text())
  }
  const payload = await response.json()
  return payload.task_sources
}

export async function uploadTaskFile(file: File): Promise<UploadTaskResult> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch('/api/tasks/upload', {
    method: 'POST',
    body,
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json()
}

export async function downloadTaskTemplate(): Promise<void> {
  const response = await fetch('/api/tasks/template')
  if (!response.ok) {
    throw new Error(await response.text())
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = '任务模板.json'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function downloadScenarioTemplate(): Promise<void> {
  await downloadJsonFile('/api/scenarios/template', '场景模板.json')
}

export async function downloadDialogueTemplate(): Promise<void> {
  await downloadJsonFile('/api/dialogues/template', '对话数据模板.json')
}

type StreamHandlers<TComplete> = {
  onStage?: (payload: { message?: string; stage?: string; [key: string]: unknown }) => void
  onDelta?: (text: string) => void
  onComplete: (payload: TComplete) => void
}

async function readEventStream<TComplete>(
  response: Response,
  handlers: StreamHandlers<TComplete>,
): Promise<void> {
  if (!response.ok) {
    throw new Error(await response.text())
  }
  if (!response.body) {
    throw new Error('浏览器不支持流式响应')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const handleBlock = (block: string) => {
    const event = block.match(/^event:\s*(.+)$/m)?.[1]?.trim() || 'message'
    const dataLines = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
    const rawData = dataLines.join('\n')
    if (!rawData) return
    if (event === 'stage') {
      handlers.onStage?.(JSON.parse(rawData))
    } else if (event === 'delta') {
      handlers.onDelta?.(JSON.parse(rawData))
    } else if (event === 'complete') {
      handlers.onComplete(JSON.parse(rawData))
    } else if (event === 'error') {
      const payload = JSON.parse(rawData)
      throw new Error(payload.message || rawData)
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      handleBlock(block)
    }
    if (done) break
  }
  if (buffer.trim()) {
    handleBlock(buffer)
  }
}



export type ChooseRunPayload = {
  task_id: string
  scenario_mode: 'generate' | 'upload'
  dialogue_mode: 'generate' | 'import'
  scenarioFile?: File
  traceFile?: File
}

export async function streamChooseRun(
  payload: ChooseRunPayload,
  handlers: StreamHandlers<RunSummary>,
): Promise<void> {
  const body = new FormData()
  body.append('task_id', payload.task_id)
  body.append('scenario_mode', payload.scenario_mode)
  body.append('dialogue_mode', payload.dialogue_mode)
  if (payload.scenarioFile) {
    body.append('scenario_file', payload.scenarioFile)
  }
  if (payload.traceFile) {
    body.append('trace_file', payload.traceFile)
  }
  const response = await fetch('/api/eval-runs/choose/stream', {
    method: 'POST',
    body,
  })
  await readEventStream(response, handlers)
}

export async function streamRun(
  payload: { task_id: string; model?: string; custom_task?: string },
  handlers: StreamHandlers<RunSummary>,
): Promise<void> {
  const response = await fetch('/api/eval-runs/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await readEventStream(response, handlers)
}

export async function streamImportedRun(
  payload: { task_id: string; traceFile: File },
  handlers: StreamHandlers<RunSummary>,
): Promise<void> {
  const body = new FormData()
  body.append('task_id', payload.task_id)
  body.append('trace_file', payload.traceFile)
  const response = await fetch('/api/eval-runs/import/stream', {
    method: 'POST',
    body,
  })
  await readEventStream(response, handlers)
}

export async function analyzeRun(runId: string, question: string): Promise<{ run_id: string; answer: string }> {
  const response = await fetch(`/api/eval-runs/${runId}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json()
}

export async function streamAnalyzeRun(
  runId: string,
  question: string,
  handlers: StreamHandlers<{ run_id: string }>,
): Promise<void> {
  const response = await fetch(`/api/eval-runs/${runId}/analyze/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  await readEventStream(response, handlers)
}

export async function streamAssistant(
  payload: {
    messages: Array<{ role: 'user' | 'bot'; content: string }>
    active_run_id?: string
  },
  handlers: StreamHandlers<{ status: string }>,
): Promise<void> {
  const response = await fetch('/api/assistant/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await readEventStream(response, handlers)
}

export async function listArchiveGroups(): Promise<ArchiveGroup[]> {
  const response = await fetch('/api/archives/groups')
  if (!response.ok) {
    throw new Error(await response.text())
  }
  const payload = await response.json()
  return payload.groups
}

export async function getReport(runId: string): Promise<ReportPayload> {
  const response = await fetch(`/api/eval-runs/${runId}/report`)
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json()
}

async function downloadJsonFile(url: string, fallbackName: string): Promise<void> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(await response.text())
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = parseDownloadFileName(response.headers.get('Content-Disposition')) || fallbackName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

function parseDownloadFileName(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1])
  }
  const plainMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i)
  return plainMatch?.[1] || null
}

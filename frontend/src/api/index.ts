import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 设置相关 API
export interface Settings {
  api_key: string
  base_url: string
  model_name: string
  system_prompt: string
  context_window_size: number
  context_auto_summarize_threshold: number
  workspace_dir: string
  allowed_commands: string
  agent_max_iterations: number
  agent_temperature: number
  agent_deep_thinking_default: boolean
  agent_web_search_default: boolean
  search_provider: string
  search_api_keys: string  // JSON 字符串
  snapshot_max_count: number
  feishu_text_chunk_size: number
  feishu_queue_maxsize: number
  quality_gate_auto_snapshot: boolean
  restrict_paths: boolean
}

export const settingsApi = {
  get: () => api.get<Settings>('/settings'),
  update: (settings: Settings) => api.put<Settings>('/settings', settings),
  verifySearchKey: (provider: string, api_key: string) =>
    api.post<{ valid: boolean }>('/settings/verify-search-key', { provider, api_key }),
}

// 消息相关 API
export interface Message {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at?: string
}

export const messagesApi = {
  list: (limit = 100, offset = 0) =>
    api.get<Message[]>('/messages', { params: { limit, offset } }),
  clear: () => api.delete('/messages'),
}

// Agent 事件类型
export interface AgentEvent {
  type: 'content' | 'thinking' | 'tool_call' | 'tool_result' | 'diff' | 'error' | 'done' | 'working'
  content?: string
  tool?: string
  tool_args?: Record<string, any>
  tool_result?: string
  call_id?: string
  diff_path?: string
  diff_old?: string
  diff_new?: string
  iteration?: number
  total_tool_calls?: number
}

// 聊天回调类型
export interface ChatCallbacks {
  onContent?: (content: string) => void
  onEvent?: (event: AgentEvent) => void
  onDone?: () => void
  onError?: (error: string) => void
}

// 聊天 API（SSE 流式）
export const chatApi = {
  // 停止当前正在进行的 AI 回复
  stop: () => api.post('/chat/stop'),

  // 简单模式（向后兼容）
  stream: (message: string, deepThinking: boolean, onChunk: (content: string) => void, onDone: () => void, signal?: AbortSignal) => {
    return chatApi.streamAgent(message, 'chat', deepThinking, true, {
      onContent: onChunk,
      onDone: onDone,
    }, signal)
  },

  // Agent 模式（支持 Tool Calling）
  streamAgent: (message: string, mode: 'chat' | 'agent', deepThinking: boolean, webSearchEnabled: boolean, callbacks: ChatCallbacks, signal?: AbortSignal) => {
    const endpoint = mode === 'agent' ? '/chat/agent' : '/chat'

    return fetch(`/api${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, mode, deep_thinking: deepThinking, web_search_enabled: webSearchEnabled }),
      signal,  // 支持取消
    }).then(async (response) => {
      const reader = response.body?.getReader()
      if (!reader) throw new Error('No reader available')

      const decoder = new TextDecoder()
      let buffer = ''

      let doneReceived = false
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: AgentEvent = JSON.parse(line.slice(6))

              // 分发事件
              if (event.type === 'content' && event.content) {
                callbacks.onContent?.(event.content)
              }
              if (event.type === 'error' && event.content) {
                callbacks.onError?.(event.content)
              }
              if (event.type === 'done') {
                doneReceived = true
                callbacks.onDone?.()
              }

              // 所有事件都触发 onEvent
              callbacks.onEvent?.(event)
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }

      // 流结束但没收到 done 事件（后端异常断开），视为异常终止
      if (!doneReceived) {
        callbacks.onError?.('连接意外断开，请重试')
        callbacks.onDone?.()
      }
    })
  },
}

// ─────────── 主/影子双系统状态 API ───────────

export interface ServiceStatus {
  port: number
  reachable: boolean
  status: string
  tool_count: number
  feishu_connected: boolean
  agent_ready: boolean
  version: string
  error: string
}

export interface DualStatus {
  current_mode: 'main' | 'shadow'
  current_port: number
  main: ServiceStatus
  shadow: ServiceStatus
}

export const systemApi = {
  dualStatus: () => api.get<DualStatus>('/shadow/dual-status'),
  shadowStatus: () => api.get<{ running: boolean; port: number; startup_time: string; last_test_passed: boolean; last_test_time: string }>('/shadow/status'),
  startShadow: () => api.post<{ success: boolean; message: string }>('/shadow/start'),
  stopShadow: () => api.post<{ success: boolean; message: string }>('/shadow/stop'),
  testShadow: () => api.post<{ success: boolean; all_passed: boolean; verdict: string; results: any[] }>('/shadow/test'),
  promoteShadow: () => api.post<{ success: boolean; message: string }>('/shadow/promote'),
}

// 飞书配置 API
export interface FeishuSettings {
  enabled: boolean
  app_id: string
  app_secret: string
  verification_token: string
}

export interface FeishuStatus {
  enabled: boolean
  app_id: string
  has_secret: boolean
  has_verification_token: boolean
  connected: boolean
  event_types: string[]
}

export const feishuApi = {
  getConfig: () => api.get<FeishuStatus>('/feishu/config'),
  updateConfig: (settings: FeishuSettings) => api.put<FeishuStatus>('/feishu/config', settings),
  restart: () => api.post<{ status: string; message: string }>('/feishu/restart'),
  getStatus: () => api.get<{ enabled: boolean; configured: boolean; connected: boolean; app_id: string }>('/feishu/status'),
}

// ─────────── 管理 API (Phase 5) ───────────

// Agent 模板
export interface AgentTemplate {
  id: string
  name: string
  description: string
  system_prompt: string
  tools: string[]
  is_builtin: number
  created_at: string
  updated_at: string
}

export const templatesApi = {
  list: () => api.get<AgentTemplate[]>('/templates'),
  get: (id: string) => api.get<AgentTemplate>(`/templates/${id}`),
  create: (data: AgentTemplate) => api.post<{ status: string }>('/templates', data),
  update: (id: string, data: Partial<AgentTemplate>) => api.put<{ status: string }>(`/templates/${id}`, data),
  delete: (id: string) => api.delete(`/templates/${id}`),
}

// 子Agent
export interface SubAgentInfo {
  id: string
  name: string
  description: string
  system_prompt: string
  tools: string[]
  role_template: string
  persistent: boolean
  created_at: string
  last_used: string | null
  use_count: number
  status: string
}

export const agentsApi = {
  list: () => api.get<SubAgentInfo[]>('/agents'),
  delete: (id: string) => api.delete(`/agents/${id}`),
}

// 目标
export interface MilestoneInfo {
  id: string
  title: string
  status: string
  progress: number
  completion_criteria: string
  created_at: string
  completed_at: string | null
}

export interface GoalInfo {
  id: string
  title: string
  description: string
  priority: number
  status: string
  deadline: string | null
  tags: string[]
  milestones: MilestoneInfo[]
  created_at: string
  updated_at: string
}

export const goalsApi = {
  list: (status = '') => api.get<GoalInfo[]>('/goals', { params: { status } }),
  get: (id: string) => api.get<GoalInfo>(`/goals/${id}`),
  create: (data: Partial<GoalInfo>) => api.post<GoalInfo>('/goals', data),
  update: (id: string, data: Partial<GoalInfo>) => api.put<GoalInfo>(`/goals/${id}`, data),
  delete: (id: string) => api.delete(`/goals/${id}`),
  addMilestone: (goalId: string, data: { title: string; completion_criteria: string }) =>
    api.post<MilestoneInfo>(`/goals/${goalId}/milestones`, data),
  updateMilestone: (goalId: string, msId: string, data: Partial<MilestoneInfo>) =>
    api.put<MilestoneInfo>(`/goals/${goalId}/milestones/${msId}`, data),
  deleteMilestone: (goalId: string, msId: string) =>
    api.delete(`/goals/${goalId}/milestones/${msId}`),
}

// 快照
export interface SnapshotInfo {
  id: string
  name: string
  description: string
  created_at: string
  file_count: number
  total_size: number
  trigger: string
}

export const snapshotsApi = {
  list: () => api.get<SnapshotInfo[]>('/snapshots'),
  create: (name: string, description: string) =>
    api.post<SnapshotInfo>('/snapshots', null, { params: { name, description } }),
  restore: (id: string) => api.post<{ status: string; message: string }>(`/snapshots/${id}/restore`),
  delete: (id: string) => api.delete(`/snapshots/${id}`),
}

// 记忆
export interface MemoryInfo {
  id: string
  content: string
  category: string
  importance: number
  tags: string[]
  timestamp: string
  source_session: string | null
}

export const memoriesApi = {
  list: (params: { query?: string; category?: string; tags?: string; limit?: number } = {}) =>
    api.get<MemoryInfo[]>('/memories', { params }),
  stats: () => api.get('/memories/stats'),
  categories: () => api.get<{ categories: string[]; tags: string[]; total: number }>('/memories/categories'),
  delete: (id: string) => api.delete(`/memories/${id}`),
}

// 进化事件
export interface EvolutionEvent {
  timestamp: string
  type: string
  description: string
  metadata?: Record<string, any>
}

export const evolutionApi = {
  list: (limit = 50) => api.get<EvolutionEvent[]>('/evolution', { params: { limit } }),
}

// 全局概览
export interface Overview {
  memories: { total: number; categories: number; tags: number }
  goals: { total: number; active: number; completed: number }
  agents: { total: number; idle: number }
  snapshots: { total: number; total_size_kb: number }
  tools: { total: number; executable: number }
}

export const overviewApi = {
  get: () => api.get<Overview>('/overview'),
}

export default api

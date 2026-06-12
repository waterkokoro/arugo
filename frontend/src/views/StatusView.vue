<template>
  <div class="status-panel">
    <n-card title="Agent 实时状态" :bordered="false">
      <!-- 连接状态 -->
      <n-space vertical size="small">
        <div class="indicator-row">
          <span class="label">Agent 状态</span>
          <n-tag :type="status.isActive ? 'success' : 'default'" round size="small">
            {{ status.isActive ? '🟢 运行中' : '⚪ 就绪' }}
          </n-tag>
        </div>

        <div v-if="status.isActive" class="indicator-row">
          <span class="label">当前步骤</span>
          <span class="value">{{ status.currentStep || '思考中...' }}</span>
        </div>

        <div class="indicator-row">
          <span class="label">活跃会话</span>
          <span class="value">{{ status.activeSessions }}</span>
        </div>

        <div class="indicator-row">
          <span class="label">飞书连接</span>
          <n-tag :type="status.feishuConnected ? 'success' : 'default'" round size="small">
            {{ status.feishuConnected ? '🟢 已连接' : '⚪ 未连接' }}
          </n-tag>
        </div>
      </n-space>
    </n-card>

    <!-- 事件日志 -->
    <n-card title="事件日志" :bordered="false" style="margin-top: 16px;">
      <template #header-extra>
        <n-button size="small" @click="clearEvents" :disabled="events.length === 0">
          清空
        </n-button>
      </template>

      <div v-if="events.length === 0" class="empty-state">
        暂无事件。发送一条消息或等待 Agent 活动...
      </div>

      <div v-else class="event-list">
        <div
          v-for="(ev, i) in events"
          :key="i"
          class="event-item"
          :class="'event-' + ev.type"
        >
          <span class="event-time">{{ ev.time }}</span>
          <span class="event-type-badge">{{ typeBadge(ev.type) }}</span>
          <span class="event-text">{{ formatEvent(ev) }}</span>
        </div>
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { NCard, NTag, NSpace, NButton } from 'naive-ui'

interface LogEvent {
  time: string
  type: string
  tool?: string
  content?: string
  tool_result?: string
}

const status = reactive({
  isActive: false,
  currentStep: '',
  toolCount: 0,
  activeSessions: 0,
  feishuConnected: false,
})

const events = ref<LogEvent[]>([])
const MAX_EVENTS = 100

function nowTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function addEvent(ev: LogEvent) {
  events.value.push(ev)
  if (events.value.length > MAX_EVENTS) {
    events.value = events.value.slice(-MAX_EVENTS)
  }
}

function clearEvents() {
  events.value = []
}

function typeBadge(type: string): string {
  const map: Record<string, string> = {
    tool_call: '🔧',
    tool_result: '✅',
    error: '❌',
    done: '🏁',
    thinking: '💭',
    content: '💬',
    diff: '📝',
    summary: '📊',
  }
  return map[type] || type
}

function formatEvent(ev: LogEvent): string {
  switch (ev.type) {
    case 'tool_call':
      return `调用 ${ev.tool || '?'}`
    case 'tool_result':
      return `${ev.tool || ''}: ${(ev.tool_result || '').slice(0, 80)}`
    case 'error':
      return ev.content || '未知错误'
    case 'content':
      return (ev.content || '').slice(0, 200)
    case 'done':
      return 'Agent 完成'
    case 'thinking':
      return '深度思考中...'
    case 'diff':
      return '文件变更'
    default:
      return ev.content || ''
  }
}

let eventSource: EventSource | null = null

function connect() {
  try {
    eventSource = new EventSource('/api/agent/status/stream')

    eventSource.addEventListener('agent_event', (e) => {
      try {
        const data = JSON.parse(e.data)
        addEvent({ time: nowTime(), ...data })

        if (data.type === 'tool_call') {
          status.isActive = true
          status.currentStep = data.tool || ''
          status.toolCount++
        } else if (data.type === 'done') {
          status.isActive = false
          status.currentStep = ''
        } else if (data.type === 'error') {
          status.isActive = false
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('summary', (e) => {
      try {
        const data = JSON.parse(e.data)
        status.isActive = data.is_active || false
        status.activeSessions = data.event_count > 0 ? 1 : 0
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('sessions', (e) => {
      try {
        const data = JSON.parse(e.data)
        status.activeSessions = data.filter((s: any) => s.is_active).length
      } catch { /* ignore */ }
    })

    eventSource.onerror = () => {
      eventSource?.close()
      // 5 秒后重连
      setTimeout(connect, 5000)
    }
  } catch {
    setTimeout(connect, 5000)
  }
}

// 轮询获取飞书状态
let pollTimer: ReturnType<typeof setInterval> | null = null
async function checkFeishu() {
  try {
    const res = await fetch('/api/feishu/status')
    const data = await res.json()
    status.feishuConnected = data.connected || false
  } catch { /* ignore */ }
}

onMounted(() => {
  connect()
  checkFeishu()
  pollTimer = setInterval(checkFeishu, 10000)
})

onUnmounted(() => {
  eventSource?.close()
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.status-panel {
  max-width: 800px;
  margin: 0 auto;
  padding: 16px 24px;
}

.indicator-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
}

.label {
  font-size: 13px;
  color: #888;
  min-width: 80px;
}

.value {
  font-size: 13px;
  color: #ccc;
}

.empty-state {
  text-align: center;
  color: #666;
  padding: 40px 0;
  font-size: 14px;
}

.event-list {
  max-height: 500px;
  overflow-y: auto;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
}

.event-item {
  display: flex;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 4px;
  align-items: baseline;
}

.event-item:hover {
  background: rgba(255,255,255,0.04);
}

.event-time {
  color: #555;
  font-size: 11px;
  min-width: 60px;
  flex-shrink: 0;
}

.event-type-badge {
  min-width: 28px;
  flex-shrink: 0;
}

.event-text {
  color: #bbb;
  word-break: break-all;
}

.event-tool_call .event-text { color: #60a5fa; }
.event-tool_result .event-text { color: #34d399; }
.event-error .event-text { color: #f87171; }
.event-done .event-text { color: #a78bfa; }
</style>

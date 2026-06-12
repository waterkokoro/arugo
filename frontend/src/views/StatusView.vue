<template>
  <div class="status-panel">
    <!-- 主系统 A -->
    <n-card title="🟢 主系统 A (端口 8000)" :bordered="false">
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
          <span class="label">工具数量</span>
          <span class="value">{{ dual.mainTools || '—' }}</span>
        </div>

        <div class="indicator-row">
          <span class="label">飞书连接</span>
          <n-tag :type="status.feishuConnected ? 'success' : 'default'" round size="small">
            {{ status.feishuConnected ? '🟢 已连接' : '⚪ 未连接' }}
          </n-tag>
        </div>

        <div class="indicator-row">
          <span class="label">活跃会话</span>
          <span class="value">{{ status.activeSessions }}</span>
        </div>
      </n-space>
    </n-card>

    <!-- 影子系统 B -->
    <n-card :title="(dual.shadowOnline ? '🔷 影子系统 B (端口 8001)' : '⬜ 影子系统 B (端口 8001)')" :bordered="false" style="margin-top: 16px;">
      <template #header-extra>
        <n-space size="small">
          <n-button
            v-if="!dual.shadowOnline"
            size="small"
            type="info"
            ghost
            @click="startShadow"
            :loading="shadowLoading"
          >
            启动 B
          </n-button>
          <n-button
            v-else
            size="small"
            type="warning"
            ghost
            @click="stopShadow"
            :loading="shadowLoading"
          >
            停止 B
          </n-button>
        </n-space>
      </template>

      <n-space vertical size="small">
        <div class="indicator-row">
          <span class="label">运行状态</span>
          <n-tag :type="dual.shadowOnline ? 'info' : 'default'" round size="small">
            {{ dual.shadowOnline ? '🔷 运行中' : '⬜ 已停止' }}
          </n-tag>
        </div>

        <div v-if="dual.shadowOnline" class="indicator-row">
          <span class="label">工具数量</span>
          <span class="value">{{ dual.shadowTools || '—' }}</span>
        </div>

        <div v-if="dual.shadowOnline" class="indicator-row">
          <span class="label">飞书模式</span>
          <n-tag type="default" round size="small">跳过（影子模式）</n-tag>
        </div>

        <div v-if="!dual.shadowOnline" class="empty-state" style="padding: 20px 0;">
          影子系统未启动。它用于在隔离环境中<a href="javascript:void(0)">安全测试</a>代码改动。<br/>
          测试通过后再升级到主系统 A。
        </div>

        <!-- 快捷操作 -->
        <div v-if="dual.shadowOnline" style="margin-top: 8px;">
          <n-space size="small">
            <n-button size="small" type="success" ghost @click="testShadow" :loading="shadowLoading">
              测试 B
            </n-button>
            <n-button size="small" type="primary" ghost @click="promoteShadow" :loading="shadowLoading">
              升级到 A
            </n-button>
          </n-space>
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

const dual = reactive({
  mainOnline: true,
  mainTools: 0,
  shadowOnline: false,
  shadowTools: 0,
})

const shadowLoading = ref(false)
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
      setTimeout(connect, 5000)
    }
  } catch {
    setTimeout(connect, 5000)
  }
}

// 轮询获取飞书状态 + 双系统状态
let pollTimer: ReturnType<typeof setInterval> | null = null
async function checkFeishu() {
  try {
    const res = await fetch('/api/feishu/status')
    const data = await res.json()
    status.feishuConnected = data.connected || false
  } catch { /* ignore */ }
}

async function checkDual() {
  try {
    const res = await fetch('/api/shadow/dual-status')
    const data = await res.json()
    dual.mainOnline = data.main?.reachable ?? true
    dual.mainTools = data.main?.tool_count ?? 0
    dual.shadowOnline = data.shadow?.reachable ?? false
    dual.shadowTools = data.shadow?.tool_count ?? 0
  } catch { /* ignore */ }
}

// ── 影子操作 ──
async function startShadow() {
  shadowLoading.value = true
  try {
    await fetch('/api/shadow/start', { method: 'POST' })
    // 等 2 秒后刷新
    setTimeout(checkDual, 2000)
  } finally {
    shadowLoading.value = false
  }
}

async function stopShadow() {
  shadowLoading.value = true
  try {
    await fetch('/api/shadow/stop', { method: 'POST' })
    setTimeout(checkDual, 1500)
  } finally {
    shadowLoading.value = false
  }
}

async function testShadow() {
  shadowLoading.value = true
  try {
    const res = await fetch('/api/shadow/test', { method: 'POST' })
    const data = await res.json()
    addEvent({ time: nowTime(), type: 'tool_result', content: data.verdict || '测试完成' })
  } finally {
    shadowLoading.value = false
  }
}

async function promoteShadow() {
  if (!confirm('确认将影子 B 升级到主系统 A？A 将短暂重启。')) return
  shadowLoading.value = true
  try {
    const res = await fetch('/api/shadow/promote', { method: 'POST' })
    const data = await res.json()
    addEvent({ time: nowTime(), type: data.success ? 'done' : 'error', content: data.message })
  } finally {
    shadowLoading.value = false
    setTimeout(checkDual, 3000)
  }
}

onMounted(() => {
  connect()
  checkFeishu()
  checkDual()
  pollTimer = setInterval(() => {
    checkFeishu()
    checkDual()
  }, 10000)
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
  color: var(--n-text-color-3, #888);
  min-width: 80px;
}

.value {
  font-size: 13px;
  color: var(--n-text-color, #ccc);
}

.empty-state {
  text-align: center;
  color: var(--n-text-color-3, #666);
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
  color: var(--n-text-color-3, #555);
  font-size: 11px;
  min-width: 60px;
  flex-shrink: 0;
}

.event-type-badge {
  min-width: 28px;
  flex-shrink: 0;
}

.event-text {
  color: var(--n-text-color-2, #bbb);
  word-break: break-all;
}

.event-tool_call .event-text { color: #60a5fa; }
.event-tool_result .event-text { color: #34d399; }
.event-error .event-text { color: #f87171; }
.event-done .event-text { color: #a78bfa; }
</style>

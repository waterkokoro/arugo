<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  NLayout, NLayoutHeader, NLayoutSider, NLayoutContent,
  NMenu, NIcon, NConfigProvider, zhCN, dateZhCN,
  NDialogProvider, NMessageProvider,
  NTag, NSpace, NButton, NSwitch
} from 'naive-ui'
import { computed, h, ref, onMounted, onUnmounted, type Component } from 'vue'
import {
  ChatboxOutline, SettingsOutline, GridOutline,
  PulseOutline, HardwareChipOutline,
  ChevronBackOutline, ChevronForwardOutline
} from '@vicons/ionicons5'

const route = useRoute()
const collapsed = ref(false)

// ============================================================
// 菜单选项
// ============================================================
const menuOptions = [
  {
    label: () => h(RouterLink, { to: '/' }, { default: () => '对话' }),
    key: 'chat',
    icon: () => h(NIcon, null, { default: () => h(ChatboxOutline) }),
  },
  {
    label: () => h(RouterLink, { to: '/manage' }, { default: () => '管理' }),
    key: 'manage',
    icon: () => h(NIcon, null, { default: () => h(GridOutline) }),
  },
  {
    label: () => h(RouterLink, { to: '/status' }, { default: () => '状态' }),
    key: 'status',
    icon: () => h(NIcon, null, { default: () => h(PulseOutline) }),
  },
  {
    label: () => h(RouterLink, { to: '/settings' }, { default: () => '设置' }),
    key: 'settings',
    icon: () => h(NIcon, null, { default: () => h(SettingsOutline) }),
  },
]

const activeKey = computed(() => {
  // 根路径映射到 chat
  if (route.path === '/') return 'chat'
  return route.name as string
})

// ============================================================
// Agent 状态（轮询 + SSE 降级）
// ============================================================
const agentStatus = ref<{
  isActive: boolean
  currentStep: string
  toolCount: number
  activeSessions: number
  feishuConnected: boolean
  lastEvent: string
}>({
  isActive: false,
  currentStep: '',
  toolCount: 0,
  activeSessions: 0,
  feishuConnected: false,
  lastEvent: '',
})

let eventSource: EventSource | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null

function connectSSE() {
  try {
    eventSource = new EventSource('/api/agent/status/stream')

    eventSource.addEventListener('agent_event', (e) => {
      try {
        const data = JSON.parse(e.data)
        agentStatus.value.lastEvent = data.type
        if (data.type === 'tool_call') {
          agentStatus.value.isActive = true
          agentStatus.value.currentStep = data.tool || ''
          agentStatus.value.toolCount++
        } else if (data.type === 'done') {
          agentStatus.value.isActive = false
          agentStatus.value.currentStep = ''
        } else if (data.type === 'error') {
          agentStatus.value.isActive = false
        }
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('summary', (e) => {
      try {
        const data = JSON.parse(e.data)
        agentStatus.value.isActive = data.is_active
        agentStatus.value.activeSessions = data.event_count > 0 ? 1 : 0
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('sessions', (e) => {
      try {
        const data = JSON.parse(e.data)
        agentStatus.value.activeSessions = data.filter((s: any) => s.is_active).length
      } catch { /* ignore */ }
    })

    eventSource.onerror = () => {
      // SSE 断开，降级为轮询
      eventSource?.close()
      eventSource = null
      startPolling()
    }
  } catch {
    startPolling()
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/agent/status/summary')
      const data = await res.json()
      agentStatus.value.activeSessions = data.active_count || 0
      if (data.sessions?.length > 0) {
        const s = data.sessions[0]
        agentStatus.value.isActive = s.is_active
        agentStatus.value.currentStep = s.current_step
        agentStatus.value.toolCount = s.tool_calls?.length || 0
      }
    } catch { /* ignore */ }
  }, 3000)
}

// 检查飞书状态
async function checkFeishuStatus() {
  try {
    const res = await fetch('/api/feishu/status')
    const data = await res.json()
    agentStatus.value.feishuConnected = data.connected || false
  } catch { /* ignore */ }
}

onMounted(() => {
  connectSSE()
  checkFeishuStatus()
})

onUnmounted(() => {
  eventSource?.close()
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <n-layout style="height: 100vh;" has-sider>
          <!-- ============ 左菜单栏 ============ -->
          <n-layout-sider
            bordered
            :collapsed="collapsed"
            collapse-mode="width"
            :collapsed-width="64"
            :width="200"
          >
            <!-- Logo 区 -->
            <div class="sider-header">
              <n-icon size="28" color="#7c3aed">
                <HardwareChipOutline />
              </n-icon>
              <span v-if="!collapsed" class="sider-title">Arugo</span>
            </div>

            <n-menu
              :collapsed="collapsed"
              :collapsed-width="64"
              :collapsed-icon-size="22"
              :options="menuOptions"
              :value="activeKey"
            />

            <!-- 收起按钮 -->
            <div class="sider-footer">
              <n-button
                text
                @click="collapsed = !collapsed"
                style="width: 100%;"
              >
                <n-icon size="18">
                  <ChevronBackOutline v-if="!collapsed" />
                  <ChevronForwardOutline v-else />
                </n-icon>
              </n-button>
            </div>
          </n-layout-sider>

          <!-- ============ 右侧内容区 ============ -->
          <n-layout>
            <!-- ============ 顶栏 ============ -->
            <n-layout-header bordered style="height: 48px; padding: 0 20px; display: flex; align-items: center; justify-content: space-between;">
              <!-- 左侧: Agent 状态 -->
              <n-space align="center" size="small">
                <div class="status-dot" :class="agentStatus.isActive ? 'active' : 'idle'"></div>
                <span class="status-text">
                  {{ agentStatus.isActive ? `运行中: ${agentStatus.currentStep || '思考...'}` : '就绪' }}
                </span>
                <n-tag
                  v-if="agentStatus.isActive"
                  size="small"
                  type="info"
                  :bordered="false"
                  round
                >
                  {{ agentStatus.toolCount }} 步
                </n-tag>
              </n-space>

              <!-- 右侧: 连接状态 -->
              <n-space align="center" size="small">
                <n-tag
                  size="small"
                  :type="agentStatus.feishuConnected ? 'success' : 'default'"
                  :bordered="false"
                  round
                >
                  {{ agentStatus.feishuConnected ? '🟢 飞书' : '⚪ 飞书' }}
                </n-tag>
                <span class="version-tag">v1.0</span>
              </n-space>
            </n-layout-header>

            <!-- ============ 内容区 ============ -->
            <n-layout-content style="height: calc(100vh - 48px); overflow: auto;">
              <router-view v-slot="{ Component }">
                <keep-alive>
                  <component :is="Component" />
                </keep-alive>
              </router-view>
            </n-layout-content>
          </n-layout>
        </n-layout>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}

/* ── 侧边栏 ── */
.sider-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 18px;
}

.sider-title {
  font-size: 18px;
  font-weight: 700;
  color: #7c3aed;
  letter-spacing: 0.5px;
}

.sider-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px;
  border-top: 1px solid rgba(255,255,255,0.06);
}

/* ── 顶栏状态 ── */
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #999;
  transition: background 0.3s;
}
.status-dot.active {
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
  animation: pulse 1.5s ease-in-out infinite;
}
.status-dot.idle {
  background: #6b7280;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 13px;
  color: #999;
}

.version-tag {
  font-size: 12px;
  color: #666;
}
</style>

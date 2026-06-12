<template>
  <div>
    <!-- 操作栏 -->
    <n-space style="margin-bottom: 12px" align="center">
      <n-button size="small" @click="refresh" :loading="loading" secondary>
        🔄 刷新诊断
      </n-button>
      <n-button size="small" @click="quickCheck" :loading="quickLoading" secondary>
        ⚡ 快速检查
      </n-button>
      <n-tag :type="overallTag" round size="small">
        {{ report?.verdict || '未检测' }}
      </n-tag>
      <span style="color: #666; font-size: 12px; margin-left: auto">
        {{ report?.timestamp?.slice(0, 19) || '' }}
      </span>
    </n-space>

    <!-- 概览条 -->
    <n-space style="margin-bottom: 16px">
      <n-tag v-for="(count, key) in summaryTags" :key="key" :type="key as any" round size="small">
        {{ key === 'ok' ? '✅' : key === 'warn' ? '⚠️' : '❌' }}
        {{ key === 'ok' ? '正常' : key === 'warn' ? '警告' : '错误' }}: {{ count }}
      </n-tag>
    </n-space>

    <!-- 检查项卡片 -->
    <n-grid v-if="checks.length" :cols="2" :x-gap="12" :y-gap="12">
      <n-grid-item v-for="check in checks" :key="check.name">
        <n-card
          size="small"
          :bordered="true"
          :style="{
            borderLeft: `3px solid ${statusColor(check.status)}`,
            background: statusBg(check.status),
          }"
        >
          <template #header>
            <span style="font-size: 13px; font-weight: 600">
              {{ statusIcon(check.status) }} {{ check.label }}
            </span>
          </template>
          <p style="margin: 0 0 8px; font-size: 13px; color: #ccc">{{ check.message }}</p>
          <p v-if="check.details" style="margin: 0 0 8px; font-size: 11px; color: #777; white-space: pre-wrap">{{ check.details }}</p>
          <n-space v-if="check.suggestions?.length">
            <n-tag
              v-for="(s, i) in check.suggestions"
              :key="i"
              size="tiny"
              type="warning"
            >
              💡 {{ s }}
            </n-tag>
          </n-space>
        </n-card>
      </n-grid-item>
    </n-grid>

    <n-empty v-else-if="!loading" description="点击「刷新诊断」查看健康状态" />

    <!-- 全局建议 -->
    <n-card v-if="report?.suggestions?.length" size="small" style="margin-top: 16px" :bordered="true">
      <template #header>💡 自愈建议</template>
      <n-space vertical size="small">
        <n-tag v-for="(s, i) in report.suggestions" :key="i" type="warning" round>
          → {{ s }}
        </n-tag>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NCard, NButton, NSpace, NTag, NGrid, NGridItem, NEmpty, useMessage } from 'naive-ui'

interface HealthCheck {
  check_name: string
  status: 'ok' | 'warn' | 'error'
  message: string
  details: string
  suggestions: string[]
  timestamp: string
}

interface HealthReport {
  overall: 'ok' | 'warn' | 'error'
  verdict: string
  summary: { total: number; ok: number; warn: number; error: number }
  checks: Record<string, HealthCheck>
  suggestions: string[]
  timestamp: string
}

interface CheckDisplay {
  name: string
  label: string
  status: string
  message: string
  details: string
  suggestions: string[]
}

const LABEL_MAP: Record<string, string> = {
  tool_integrity: '🔧 工具完整性',
  memory_health: '🧠 记忆健康',
  goal_health: '🎯 目标系统',
  test_results: '🧪 测试结果',
  disk_space: '💾 磁盘空间',
  git_status: '📦 Git 状态',
  feishu_status: '🔗 飞书连接',
  snapshot_count: '📸 快照数量',
}

const message = useMessage()
const report = ref<HealthReport | null>(null)
const loading = ref(false)
const quickLoading = ref(false)

const checks = computed<CheckDisplay[]>(() => {
  if (!report.value?.checks) return []
  return Object.entries(report.value.checks).map(([name, check]) => ({
    name,
    label: LABEL_MAP[name] || name,
    status: check.status,
    message: check.message,
    details: check.details || '',
    suggestions: check.suggestions || [],
  }))
})

const overallTag = computed(() => {
  if (!report.value) return 'default'
  return report.value.overall === 'ok' ? 'success'
    : report.value.overall === 'warn' ? 'warning' : 'error'
})

const summaryTags = computed(() => {
  if (!report.value) return {}
  return {
    ok: report.value.summary.ok,
    warn: report.value.summary.warn,
    error: report.value.summary.error,
  }
})

function statusColor(status: string): string {
  return status === 'ok' ? '#34d399' : status === 'warn' ? '#fbbf24' : '#f87171'
}

function statusBg(status: string): string {
  return status === 'ok' ? 'rgba(52,211,153,0.04)'
    : status === 'warn' ? 'rgba(251,191,36,0.04)'
    : 'rgba(248,113,113,0.04)'
}

function statusIcon(status: string): string {
  return status === 'ok' ? '✅' : status === 'warn' ? '⚠️' : '❌'
}

async function fetchHealth(smoke: boolean) {
  try {
    const res = await fetch(`/api/health${smoke ? '?smoke=true' : ''}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    report.value = await res.json()
  } catch (e: any) {
    message.error('健康检查失败: ' + e.message)
  }
}

async function refresh() {
  loading.value = true
  await fetchHealth(false)
  loading.value = false
}

async function quickCheck() {
  quickLoading.value = true
  await fetchHealth(true)
  quickLoading.value = false
}

onMounted(refresh)
</script>

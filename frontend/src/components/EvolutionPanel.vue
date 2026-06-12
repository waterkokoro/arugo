<template>
  <div>
    <n-space style="margin-bottom: 12px">
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
      <span style="color: var(--n-text-color-3, #999); font-size: 12px">最近 {{ events.length }} 条事件</span>
    </n-space>

    <n-timeline v-if="events.length">
      <n-timeline-item v-for="(e, i) in events" :key="i" :type="eventType(e.type)" :title="e.type" :time="e.timestamp?.slice(0, 19)">
        {{ e.description }}
      </n-timeline-item>
    </n-timeline>
    <n-empty v-else description="暂无进化事件" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NTimeline, NTimelineItem, NButton, NSpace, NEmpty, useMessage } from 'naive-ui'
import { evolutionApi, type EvolutionEvent } from '@/api'

const message = useMessage()
const events = ref<EvolutionEvent[]>([])
const loading = ref(false)

function eventType(type: string): 'success' | 'info' | 'warning' | 'error' | 'default' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'error'> = {
    tool_added: 'success',
    capability_upgrade: 'success',
    memory_created: 'info',
    code_modified: 'warning',
    code_committed: 'success',
    snapshot_created: 'info',
    snapshot_restored: 'warning',
    sub_agent_invoked: 'info',
    auto_summarize: 'default',
    backup_created: 'info',
    restore_performed: 'warning',
  }
  return map[type] || 'default'
}

async function refresh() {
  loading.value = true
  try {
    const res = await evolutionApi.list(100)
    events.value = res.data.reverse()
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

onMounted(refresh)
</script>

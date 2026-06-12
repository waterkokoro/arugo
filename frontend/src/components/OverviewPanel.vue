<template>
  <div>
    <n-grid :cols="4" :x-gap="12" :y-gap="12">
      <n-grid-item>
        <n-card size="small" hoverable>
          <n-statistic label="持久记忆" :value="overview?.memories.total ?? '-'" />
          <template #footer>{{ overview?.memories.categories ?? '-' }} 类别</template>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card size="small" hoverable>
          <n-statistic label="进化目标" :value="overview?.goals.total ?? '-'" />
          <template #footer>{{ overview?.goals.active ?? '-' }} 活跃 · {{ overview?.goals.completed ?? '-' }} 完成</template>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card size="small" hoverable>
          <n-statistic label="子Agent" :value="overview?.agents.total ?? '-'" />
          <template #footer>{{ overview?.agents.idle ?? '-' }} 空闲</template>
        </n-card>
      </n-grid-item>
      <n-grid-item>
        <n-card size="small" hoverable>
          <n-statistic label="快照" :value="overview?.snapshots.total ?? '-'" />
          <template #footer>{{ overview?.snapshots.total_size_kb ?? '-' }} KB</template>
        </n-card>
      </n-grid-item>
    </n-grid>
    <n-space style="margin-top: 16px">
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
    </n-space>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NGrid, NGridItem, NStatistic, NButton, NSpace, useMessage } from 'naive-ui'
import { overviewApi, type Overview } from '@/api'

const message = useMessage()
const overview = ref<Overview | null>(null)
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const res = await overviewApi.get()
    overview.value = res.data
  } catch (e: any) {
    message.error('加载概览失败')
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div>
    <n-space style="margin-bottom: 12px" align="center">
      <n-input v-model:value="searchQuery" placeholder="搜索记忆..." clearable size="small" style="width: 240px" @keyup.enter="refresh" />
      <n-select v-model:value="filterCategory" :options="categoryOptions" placeholder="类别" clearable size="small" style="width: 140px" @update:value="refresh" />
      <n-button size="small" @click="refresh" :loading="loading">搜索</n-button>
      <span style="color: var(--n-text-color-3, #999); font-size: 12px; margin-left: 8px">{{ stats?.total ?? '-' }} 条记忆</span>
    </n-space>

    <n-data-table
      v-if="memories.length"
      :columns="columns"
      :data="memories"
      :row-key="(row: MemoryInfo) => row.id"
      :single-line="false"
      size="small"
    />
    <n-empty v-else description="暂无记忆" />
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NDataTable, NButton, NSpace, NInput, NSelect, NTag, NEmpty, useMessage, type DataTableColumn } from 'naive-ui'
import { memoriesApi, type MemoryInfo } from '@/api'

const message = useMessage()
const memories = ref<MemoryInfo[]>([])
const loading = ref(false)
const searchQuery = ref('')
const filterCategory = ref<string | null>(null)
const categoryOptions = ref<{ label: string; value: string }[]>([])
const stats = ref<any>(null)

const columns: DataTableColumn[] = [
  { title: '重要性', key: 'importance', width: 80, render: (row) => '★'.repeat(row.importance) },
  {
    title: '类别', key: 'category', width: 100,
    render: (row) => h(NTag, { size: 'tiny', type: 'info' }, () => row.category)
  },
  {
    title: '内容', key: 'content', ellipsis: { tooltip: true }
  },
  {
    title: '标签', key: 'tags', width: 150,
    render: (row) => row.tags?.map((t: string) => h(NTag, { size: 'tiny', style: { marginRight: '4px' } }, () => t))
  },
  { title: '时间', key: 'timestamp', width: 150, render: (row) => row.timestamp?.slice(0, 19) },
  {
    title: '', key: 'actions', width: 60,
    render: (row) => h(NButton, { size: 'tiny', type: 'error', onClick: () => delMem(row) }, () => '删')
  },
]

async function refresh() {
  loading.value = true
  try {
    const res = await memoriesApi.list({
      query: searchQuery.value || undefined,
      category: filterCategory.value || undefined,
      limit: 50,
    })
    memories.value = res.data
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

async function loadCategories() {
  try {
    const res = await memoriesApi.categories()
    stats.value = { total: res.data.total }
    categoryOptions.value = res.data.categories.map((c: string) => ({ label: c, value: c }))
  } catch { /* ignore */ }
}

async function delMem(row: MemoryInfo) {
  try {
    await memoriesApi.delete(row.id)
    message.success('已删除')
    await refresh()
  } catch { message.error('删除失败') }
}

onMounted(() => { loadCategories(); refresh() })
</script>

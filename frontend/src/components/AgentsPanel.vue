<template>
  <div>
    <n-space style="margin-bottom: 12px">
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
    </n-space>

    <n-data-table
      v-if="agents.length"
      :columns="columns"
      :data="agents"
      :row-key="(row: SubAgentInfo) => row.id"
      size="small"
    />
    <n-empty v-else description="暂无子Agent，在对话中通过 create_sub_agent 创建" />

    <!-- 详情弹窗 -->
    <n-modal v-model:show="showDetail" title="子Agent 详情" style="width: 640px">
      <n-card v-if="detail" :bordered="false">
        <n-descriptions label-placement="left" :column="2" size="small" bordered>
          <n-descriptions-item label="名称">{{ detail.name }}</n-descriptions-item>
          <n-descriptions-item label="ID">{{ detail.id }}</n-descriptions-item>
          <n-descriptions-item label="状态">{{ detail.status }}</n-descriptions-item>
          <n-descriptions-item label="使用次数">{{ detail.use_count }}</n-descriptions-item>
          <n-descriptions-item label="角色模板">{{ detail.role_template || '-' }}</n-descriptions-item>
          <n-descriptions-item label="持久记忆">{{ detail.persistent ? '✅' : '❌' }}</n-descriptions-item>
          <n-descriptions-item label="工具" :span="2">{{ detail.tools?.length ? detail.tools.join(', ') : '全部' }}</n-descriptions-item>
          <n-descriptions-item label="System Prompt" :span="2">
            <n-input :value="detail.system_prompt" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" readonly style="font-size: 12px" />
          </n-descriptions-item>
        </n-descriptions>
      </n-card>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" @click="showDetail = false">关闭</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import {
  NDataTable, NButton, NSpace, NModal, NCard, NDescriptions, NDescriptionsItem,
  NInput, NEmpty, useMessage, type DataTableColumn
} from 'naive-ui'
import { agentsApi, type SubAgentInfo } from '@/api'

const message = useMessage()
const agents = ref<SubAgentInfo[]>([])
const loading = ref(false)
const showDetail = ref(false)
const detail = ref<SubAgentInfo | null>(null)

const columns: DataTableColumn[] = [
  { title: '名称', key: 'name', width: 130 },
  { title: '模板', key: 'role_template', width: 100, render: (row) => row.role_template || '-' },
  { title: '状态', key: 'status', width: 70 },
  { title: '使用', key: 'use_count', width: 60 },
  {
    title: '操作', key: 'actions', width: 120,
    render: (row) => h(NSpace, { size: 'small' }, () => [
      h(NButton, { size: 'tiny', onClick: () => viewDetail(row) }, () => '详情'),
      h(NButton, { size: 'tiny', type: 'error', onClick: () => delAgent(row) }, () => '删除'),
    ])
  },
]

async function refresh() {
  loading.value = true
  try {
    const res = await agentsApi.list()
    agents.value = res.data
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

function viewDetail(row: SubAgentInfo) {
  detail.value = row
  showDetail.value = true
}

async function delAgent(row: SubAgentInfo) {
  try {
    await agentsApi.delete(row.id)
    message.success('已删除')
    await refresh()
  } catch { message.error('删除失败') }
}

onMounted(refresh)
</script>

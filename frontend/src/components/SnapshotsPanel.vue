<template>
  <div>
    <n-space style="margin-bottom: 12px">
      <n-button size="small" type="primary" @click="doCreate" :loading="creating">+ 创建快照</n-button>
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
    </n-space>

    <n-data-table
      v-if="snapshots.length"
      :columns="columns"
      :data="snapshots"
      :row-key="(row: SnapshotInfo) => row.id"
      size="small"
    />
    <n-empty v-else description="暂无快照" />

    <n-modal v-model:show="showRestore" title="确认恢复" style="width: 400px">
      <n-card :bordered="false">
        <p>确定要从快照恢复？此操作会覆盖当前所有源码和配置数据。</p>
        <p style="color: var(--n-text-color-3, #999); font-size: 13px">恢复前会自动创建安全快照。恢复后需要重启服务。</p>
      </n-card>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" type="error" @click="doRestore" :loading="restoring">确认恢复</n-button>
          <n-button size="small" @click="showRestore = false">取消</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import { NDataTable, NButton, NSpace, NModal, NCard, NEmpty, useMessage, type DataTableColumn } from 'naive-ui'
import { snapshotsApi, type SnapshotInfo } from '@/api'

const message = useMessage()
const snapshots = ref<SnapshotInfo[]>([])
const loading = ref(false)
const creating = ref(false)
const restoring = ref(false)
const showRestore = ref(false)
const restoringId = ref('')

const columns: DataTableColumn[] = [
  { title: '名称', key: 'name', ellipsis: { tooltip: true } },
  { title: '时间', key: 'created_at', width: 160, render: (row) => row.created_at?.slice(0, 19) },
  { title: '文件', key: 'file_count', width: 60 },
  { title: '大小', key: 'total_size', width: 80, render: (row) => (row.total_size / 1024).toFixed(1) + ' KB' },
  { title: '触发', key: 'trigger', width: 60 },
  {
    title: '操作', key: 'actions', width: 120,
    render: (row) => h(NSpace, { size: 'small' }, () => [
      h(NButton, { size: 'tiny', type: 'warning', onClick: () => promptRestore(row) }, () => '恢复'),
      h(NButton, { size: 'tiny', type: 'error', onClick: () => delSnapshot(row) }, () => '删除'),
    ])
  },
]

async function refresh() {
  loading.value = true
  try { const res = await snapshotsApi.list(); snapshots.value = res.data }
  catch { message.error('加载失败') }
  finally { loading.value = false }
}

async function doCreate() {
  creating.value = true
  try {
    const res = await snapshotsApi.create('', '')
    message.success(`快照 ${res.data.id} 已创建`)
    await refresh()
  } catch { message.error('创建失败') }
  finally { creating.value = false }
}

function promptRestore(row: SnapshotInfo) {
  restoringId.value = row.id
  showRestore.value = true
}

async function doRestore() {
  restoring.value = true
  try {
    const res = await snapshotsApi.restore(restoringId.value)
    message.success(res.data.message)
    showRestore.value = false
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '恢复失败')
  }
  finally { restoring.value = false }
}

async function delSnapshot(row: SnapshotInfo) {
  try {
    await snapshotsApi.delete(row.id)
    message.success('已删除')
    await refresh()
  } catch { message.error('删除失败') }
}

onMounted(refresh)
</script>

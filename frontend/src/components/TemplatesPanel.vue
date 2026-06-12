<template>
  <div>
    <n-space justify="space-between" style="margin-bottom: 12px">
      <n-button size="small" type="primary" @click="showCreate = true">+ 新建模板</n-button>
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
    </n-space>

    <!-- 模板列表 -->
    <n-data-table
      :columns="columns"
      :data="templates"
      :row-key="(row: AgentTemplate) => row.id"
      :single-line="false"
      size="small"
    />

    <!-- 查看/编辑弹窗 -->
    <n-modal v-model:show="showEdit" :title="editMode === 'view' ? '查看模板' : '编辑模板'" style="width: 720px">
      <n-card v-if="editing" :bordered="false" style="max-height: 70vh; overflow-y: auto">
        <n-form label-placement="left" label-width="100" size="small">
          <n-form-item label="模板 ID">
            <n-input :value="editing.id" disabled />
          </n-form-item>
          <n-form-item label="名称">
            <n-input v-model:value="editing.name" :disabled="editMode === 'view'" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="editing.description" :disabled="editMode === 'view'" />
          </n-form-item>
          <n-form-item label="System Prompt">
            <n-input
              v-model:value="editing.system_prompt"
              type="textarea"
              :autosize="{ minRows: 8, maxRows: 20 }"
              :disabled="editMode === 'view'"
              style="font-family: monospace; font-size: 12px"
            />
          </n-form-item>
          <n-form-item label="工具列表">
            <n-dynamic-tags v-model:value="editingTools" :disabled="editMode === 'view'" />
            <template #feedback>
              <span class="hint">留空 = 全部工具可用</span>
            </template>
          </n-form-item>
        </n-form>
      </n-card>
      <template #footer>
        <n-space justify="end">
          <n-button v-if="editMode === 'view'" size="small" @click="enterEdit">编辑</n-button>
          <n-button v-if="editMode === 'edit'" size="small" type="primary" @click="saveEdit" :loading="saving">保存</n-button>
          <n-button size="small" @click="showEdit = false">关闭</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 新建弹窗 -->
    <n-modal v-model:show="showCreate" title="新建模板" style="width: 600px">
      <n-card :bordered="false">
        <n-form label-placement="left" label-width="100" size="small">
          <n-form-item label="模板 ID">
            <n-input v-model:value="newTemplate.id" placeholder="如: my_custom_agent" />
          </n-form-item>
          <n-form-item label="名称">
            <n-input v-model:value="newTemplate.name" placeholder="如: 我的自定义Agent" />
          </n-form-item>
          <n-form-item label="System Prompt">
            <n-input
              v-model:value="newTemplate.system_prompt"
              type="textarea"
              :autosize="{ minRows: 5, maxRows: 12 }"
              placeholder="定义Agent的角色和行为..."
              style="font-family: monospace; font-size: 12px"
            />
          </n-form-item>
        </n-form>
      </n-card>
      <template #footer>
        <n-space justify="end">
          <n-button size="small" type="primary" @click="doCreate" :loading="saving">创建</n-button>
          <n-button size="small" @click="showCreate = false">取消</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import {
  NDataTable, NButton, NSpace, NModal, NCard, NForm, NFormItem,
  NInput, NDynamicTags, NTag, useMessage, type DataTableColumn
} from 'naive-ui'
import { templatesApi, type AgentTemplate } from '@/api'

const message = useMessage()
const templates = ref<AgentTemplate[]>([])
const loading = ref(false)
const saving = ref(false)

const showEdit = ref(false)
const showCreate = ref(false)
const editMode = ref<'view' | 'edit'>('view')
const editing = ref<AgentTemplate | null>(null)
const editingTools = ref<string[]>([])

const newTemplate = ref({ id: '', name: '', system_prompt: '你是一个专业的AI子代理。', description: '' })

const columns: DataTableColumn[] = [
  { title: 'ID', key: 'id', width: 140, ellipsis: { tooltip: true } },
  { title: '名称', key: 'name', width: 120 },
  {
    title: '类型', key: 'is_builtin', width: 60,
    render: (row) => row.is_builtin ? h(NTag, { size: 'small', type: 'info' }, () => '内置') : h(NTag, { size: 'small', type: 'warning' }, () => '自定义')
  },
  {
    title: '工具', key: 'tools', width: 140,
    render: (row) => row.tools?.length ? row.tools.join(', ') : '全部'
  },
  {
    title: '操作', key: 'actions', width: 160,
    render: (row) => h(NSpace, { size: 'small' }, () => [
      h(NButton, { size: 'tiny', onClick: () => viewTemplate(row) }, () => '查看'),
      h(NButton, { size: 'tiny', type: 'error', onClick: () => delTemplate(row), disabled: row.is_builtin === 1 }, () => '删除'),
    ])
  },
]

async function refresh() {
  loading.value = true
  try {
    const res = await templatesApi.list()
    templates.value = res.data
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

function viewTemplate(row: AgentTemplate) {
  editing.value = { ...row }
  editingTools.value = [...(row.tools || [])]
  editMode.value = 'view'
  showEdit.value = true
}

function enterEdit() {
  editMode.value = 'edit'
}

async function saveEdit() {
  if (!editing.value) return
  saving.value = true
  try {
    await templatesApi.update(editing.value.id, {
      name: editing.value.name,
      description: editing.value.description,
      system_prompt: editing.value.system_prompt,
      tools: editingTools.value,
    })
    message.success('已保存')
    showEdit.value = false
    await refresh()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}

async function doCreate() {
  if (!newTemplate.value.id || !newTemplate.value.name) {
    message.warning('请填写模板 ID 和名称')
    return
  }
  saving.value = true
  try {
    await templatesApi.create({
      id: newTemplate.value.id,
      name: newTemplate.value.name,
      system_prompt: newTemplate.value.system_prompt,
      description: newTemplate.value.description,
      tools: [],
      is_builtin: 0,
      created_at: '',
      updated_at: '',
    })
    message.success('模板已创建')
    showCreate.value = false
    newTemplate.value = { id: '', name: '', system_prompt: '你是一个专业的AI子代理。', description: '' }
    await refresh()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '创建失败')
  } finally { saving.value = false }
}

async function delTemplate(row: AgentTemplate) {
  try {
    await templatesApi.delete(row.id)
    message.success('已删除')
    await refresh()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '删除失败')
  }
}

onMounted(refresh)
</script>

<style scoped>
.hint { color: #999; font-size: 11px; }
</style>

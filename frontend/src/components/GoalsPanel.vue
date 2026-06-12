<template>
  <div>
    <n-space justify="space-between" style="margin-bottom: 12px">
      <n-button size="small" type="primary" @click="showCreate = true">+ 新建目标</n-button>
      <n-button size="small" @click="refresh" :loading="loading">刷新</n-button>
    </n-space>

    <n-collapse v-if="goals.length">
      <n-collapse-item v-for="g in goals" :key="g.id" :name="g.id">
        <template #header>
          <n-space align="center">
            <span>{{ statusIcon(g.status) }}</span>
            <span>{{ '★'.repeat(g.priority) }}</span>
            <strong>{{ g.title }}</strong>
            <n-tag :type="statusType(g.status)" size="tiny">{{ g.status }}</n-tag>
            <span style="color: #999; font-size: 12px">{{ g.progress }}% · {{ g.milestones.length }}个里程碑</span>
          </n-space>
        </template>
        <template #header-extra>
          <n-space size="small" @click.stop>
            <n-button size="tiny" @click="toggleGoal(g)">状态切换</n-button>
            <n-button size="tiny" type="error" @click="delGoal(g)">删除</n-button>
          </n-space>
        </template>

        <p v-if="g.description" style="color: #666; margin-bottom: 8px">{{ g.description }}</p>

        <!-- 里程碑 -->
        <div v-if="g.milestones.length" style="margin-bottom: 8px">
          <div v-for="m in g.milestones" :key="m.id" style="display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid #f0f0f0">
            <span>{{ msIcon(m.status) }}</span>
            <n-progress :percentage="m.progress" :height="16" :border-radius="3" style="flex: 1; max-width: 200px" />
            <span style="flex: 1">{{ m.title }}</span>
            <n-tag :type="msType(m.status)" size="tiny">{{ m.status }}</n-tag>
          </div>
        </div>

        <n-space size="small">
          <n-input v-model:value="newMsTitle[g.id]" placeholder="新里程碑标题" size="tiny" style="width: 180px" />
          <n-button size="tiny" @click="addMs(g)" :disabled="!newMsTitle[g.id]">+ 添加</n-button>
        </n-space>
      </n-collapse-item>
    </n-collapse>
    <n-empty v-else description="暂无目标" />

    <!-- 新建弹窗 -->
    <n-modal v-model:show="showCreate" title="新建目标" style="width: 480px">
      <n-card :bordered="false">
        <n-form label-placement="left" label-width="80" size="small">
          <n-form-item label="标题">
            <n-input v-model:value="newGoal.title" placeholder="如: Phase 6 功能" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="newGoal.description" type="textarea" :autosize="{ minRows: 2 }" />
          </n-form-item>
          <n-form-item label="优先级">
            <n-rate v-model:value="newGoal.priority" :count="5" />
          </n-form-item>
          <n-form-item label="标签">
            <n-dynamic-tags v-model:value="newGoal.tags" />
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
import { ref, reactive, onMounted } from 'vue'
import {
  NCollapse, NCollapseItem, NButton, NSpace, NModal, NCard, NForm, NFormItem,
  NInput, NTag, NProgress, NRate, NDynamicTags, NEmpty, useMessage
} from 'naive-ui'
import { goalsApi, type GoalInfo } from '@/api'

const message = useMessage()
const goals = ref<GoalInfo[]>([])
const loading = ref(false)
const saving = ref(false)
const showCreate = ref(false)
const newMsTitle = reactive<Record<string, string>>({})

const newGoal = reactive({ title: '', description: '', priority: 3, tags: [] as string[] })

function statusIcon(s: string) { return { active: '🟢', paused: '⏸️', completed: '✅', abandoned: '❌' }[s] || '❓' }
function statusType(s: string): any { return { active: 'success', paused: 'warning', completed: 'info', abandoned: 'default' }[s] || 'default' }
function msIcon(s: string) { return { pending: '⬜', in_progress: '⏳', completed: '✅' }[s] || '⬜' }
function msType(s: string): any { return { pending: 'default', in_progress: 'warning', completed: 'success' }[s] || 'default' }

async function refresh() {
  loading.value = true
  try {
    const res = await goalsApi.list()
    goals.value = res.data
    goals.value.forEach(g => { if (!newMsTitle[g.id]) newMsTitle[g.id] = '' })
  } catch { message.error('加载失败') }
  finally { loading.value = false }
}

async function doCreate() {
  if (!newGoal.title) { message.warning('请输入标题'); return }
  saving.value = true
  try {
    await goalsApi.create({
      title: newGoal.title,
      description: newGoal.description,
      priority: newGoal.priority,
      tags: newGoal.tags,
    })
    message.success('目标已创建')
    showCreate.value = false
    newGoal.title = ''; newGoal.description = ''; newGoal.priority = 3; newGoal.tags = []
    await refresh()
  } catch { message.error('创建失败') }
  finally { saving.value = false }
}

async function toggleGoal(g: GoalInfo) {
  const next = { active: 'completed', completed: 'active', paused: 'active', abandoned: 'active' }[g.status] || 'active'
  try {
    await goalsApi.update(g.id, { status: next })
    await refresh()
  } catch { message.error('更新失败') }
}

async function delGoal(g: GoalInfo) {
  try {
    await goalsApi.delete(g.id)
    message.success('已删除')
    await refresh()
  } catch { message.error('删除失败') }
}

async function addMs(g: GoalInfo) {
  const title = newMsTitle[g.id]
  if (!title) return
  try {
    await goalsApi.addMilestone(g.id, { title, completion_criteria: '' })
    newMsTitle[g.id] = ''
    message.success('里程碑已添加')
    await refresh()
  } catch { message.error('添加失败') }
}

onMounted(refresh)
</script>

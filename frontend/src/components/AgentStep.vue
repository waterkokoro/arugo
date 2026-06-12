<template>
  <div class="agent-step" :class="'status-' + (status || 'running')">
    <n-collapse :default-expanded-names="expanded ? ['step'] : []">
      <n-collapse-item name="step">
        <template #header>
          <div class="step-header">
            <span class="step-icon">{{ statusIcon }}</span>
            <span class="step-title">{{ stepTitle }}</span>
            <span class="step-meta">
              <n-tag v-if="status === 'running'" type="info" size="tiny" :bordered="false">
                执行中
              </n-tag>
              <n-tag v-else-if="status === 'success'" type="success" size="tiny" :bordered="false">
                完成
              </n-tag>
              <n-tag v-else-if="status === 'error'" type="error" size="tiny" :bordered="false">
                失败
              </n-tag>
            </span>
          </div>
        </template>

        <div class="step-body">
          <!-- 工具参数 -->
          <div v-if="toolArgs && Object.keys(toolArgs).length > 0" class="step-section">
            <div class="step-label">参数</div>
            <n-code :code="formatArgs(toolArgs)" language="json" word-wrap />
          </div>

          <!-- 工具结果 -->
          <div v-if="result" class="step-section">
            <div class="step-label">
              结果
              <span v-if="status === 'success'" class="result-size">({{ result.length }} 字符)</span>
            </div>
            <pre class="step-result" :class="{ 'is-error': status === 'error' }">{{ result }}</pre>
          </div>
        </div>
      </n-collapse-item>
    </n-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NCollapse, NCollapseItem, NTag, NCode } from 'naive-ui'

const props = defineProps<{
  tool: string
  toolArgs?: Record<string, any>
  result?: string
  status?: 'running' | 'success' | 'error'
  expanded?: boolean
}>()

const toolLabels: Record<string, string> = {
  read_file: '📄 读取文件',
  write_file: '✏️ 写入文件',
  edit_file: '🔧 编辑文件',
  list_directory: '📁 列出目录',
  run_command: '▶️ 执行命令',
  web_search: '🔍 联网搜索',
  remember: '🧠 写入记忆',
  recall_memory: '🔍 检索记忆',
  create_sub_agent: '🤖 创建子Agent',
  invoke_sub_agent: '🤖 调用子Agent',
  list_sub_agents: '📋 列出子Agent',
  create_goal: '🎯 创建目标',
  list_goals: '📋 列出目标',
  update_goal: '✏️ 更新目标',
  add_milestone: '🏁 添加里程碑',
  create_snapshot: '📸 创建快照',
  list_snapshots: '📋 列出快照',
  restore_snapshot: '⏪ 恢复快照',
  git_commit_evolution: '📦 Git 提交',
  log_evolution_event: '📝 进化日志',
  get_evolution_status: '📊 进化状态',
  health_check: '💚 健康检查',
  run_self_diagnostics: '🔬 自我诊断',
  run_self_tests: '🧪 自测',
  plan_new_tool: '📐 规划工具',
  generate_tool_code: '🔨 生成工具代码',
  add_tool_to_self: '⚡ 自我扩展',
  hot_reload_tools: '🔄 热加载',
  validate_tool_syntax: '✅ 语法验证',
}

const statusIcon = computed(() => {
  if (props.status === 'running') return '⏳'
  if (props.status === 'success') return '✅'
  if (props.status === 'error') return '❌'
  return '⚪'
})

const stepTitle = computed(() => {
  const label = toolLabels[props.tool] || `🔧 ${props.tool}`
  const detail = getDetail()
  return detail ? `${label}: ${detail}` : label
})

function getDetail(): string {
  if (!props.toolArgs) return ''
  if (props.tool === 'run_command') {
    return props.toolArgs.command || ''
  }
  if (props.tool === 'web_search') {
    return props.toolArgs.query || ''
  }
  return props.toolArgs.path || ''
}

function formatArgs(args: Record<string, any>): string {
  const truncated: Record<string, any> = {}
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === 'string' && value.length > 500) {
      truncated[key] = value.substring(0, 500) + '... (截断)'
    } else {
      truncated[key] = value
    }
  }
  return JSON.stringify(truncated, null, 2)
}
</script>

<style scoped>
.agent-step {
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s ease;
}

.agent-step.status-running {
  border-left: 3px solid #60a5fa;
}

.agent-step.status-success {
  border-left: 3px solid #34d399;
}

.agent-step.status-error {
  border-left: 3px solid #f87171;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.step-icon {
  flex-shrink: 0;
  font-size: 13px;
}

.step-title {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: var(--n-text-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-meta {
  flex-shrink: 0;
  margin-left: 8px;
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0;
}

.step-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-label {
  font-size: 11px;
  color: var(--n-text-color-3, #999);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.result-size {
  font-weight: normal;
  color: var(--n-text-color-3, #bbb);
  margin-left: 4px;
}

.step-result {
  background: var(--n-color-embedded, #1a1a1a);
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: var(--n-text-color-2, #ccc);
  border: 1px solid var(--n-border-color, #333);
}

.step-result.is-error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}
</style>

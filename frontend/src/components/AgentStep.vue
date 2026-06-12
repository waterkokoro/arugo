<template>
  <n-collapse :default-expanded-names="expanded ? ['step'] : []">
    <n-collapse-item :title="stepTitle" name="step">
      <template #header-extra>
        <n-tag v-if="status === 'running'" type="info" size="small" :bordered="false">
          <template #icon>
            <n-icon :component="RefreshOutline" />
          </template>
          执行中
        </n-tag>
        <n-tag v-else-if="status === 'success'" type="success" size="small" :bordered="false">
          成功
        </n-tag>
        <n-tag v-else-if="status === 'error'" type="error" size="small" :bordered="false">
          失败
        </n-tag>
      </template>

      <div class="step-content">
        <!-- 工具参数 -->
        <div v-if="toolArgs && Object.keys(toolArgs).length > 0" class="step-section">
          <div class="step-label">参数</div>
          <n-code :code="formatArgs(toolArgs)" language="json" word-wrap />
        </div>

        <!-- 工具结果 -->
        <div v-if="result" class="step-section">
          <div class="step-label">结果</div>
          <pre class="step-result">{{ result }}</pre>
        </div>
      </div>
    </n-collapse-item>
  </n-collapse>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NCollapse, NCollapseItem, NTag, NIcon, NCode } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'

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
}

const stepTitle = computed(() => {
  const label = toolLabels[props.tool] || props.tool
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
  // 对于长内容，截断显示
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
.step-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.step-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-label {
  font-size: 12px;
  color: var(--n-text-color-3);
  font-weight: 500;
}

.step-result {
  background: var(--n-code-color);
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
}
</style>

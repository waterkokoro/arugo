<template>
  <div class="chat-message" :class="{ 'is-user': message.role === 'user' }">
    <div class="message-avatar">
      <n-avatar :size="36" :style="{ backgroundColor: message.role === 'user' ? '#18a058' : '#2080f0' }">
        {{ message.role === 'user' ? 'U' : 'AI' }}
      </n-avatar>
    </div>
    <div class="message-content">
      <div class="message-header">
        {{ message.role === 'user' ? '你' : 'AI 助手' }}
        <n-tag v-if="message.role === 'assistant' && (hasSteps || isWorking)" type="info" size="small" :bordered="false" style="margin-left: 8px;">
          {{ isWorking ? 'Agent 工作中' : 'Agent' }}
        </n-tag>
      </div>
      <div class="message-body">
        <!-- Agent 工作状态条 -->
        <AgentWorkingBar
          v-if="message.role === 'assistant' && (hasSteps || isWorking)"
          :is-done="!isWorking"
          :iteration="agentIteration"
          :total-steps="totalSteps"
          :current-step="currentStepLabel"
          :elapsed="elapsed"
          :total-time="totalTime"
        />

        <!-- 思考内容展示（DeepSeek 思考模式） -->
        <n-collapse v-if="hasThinking && thinkingContent" class="thinking-collapse" :default-expanded-names="isWorking ? ['thinking'] : []">
          <n-collapse-item title="💭 思考过程" name="thinking">
            <pre class="thinking-content">{{ thinkingContent }}</pre>
          </n-collapse-item>
        </n-collapse>

        <!-- Agent 步骤展示 - 实时展开 -->
        <div v-if="hasSteps" class="agent-steps">
          <AgentStep
            v-for="step in (message as ExtendedMessage).steps"
            :key="step.id"
            :tool="step.tool"
            :tool-args="step.toolArgs"
            :result="step.result"
            :status="step.status"
            :expanded="step.status === 'running' || isWorking"
          />
        </div>

        <!-- Diff 展示 -->
        <div v-if="hasDiffs" class="agent-diffs">
          <DiffView
            v-for="(diff, index) in (message as ExtendedMessage).diffs"
            :key="index"
            :path="diff.path"
            :old-content="diff.oldContent"
            :new-content="diff.newContent"
          />
        </div>

        <!-- 消息内容 -->
        <n-card v-if="message.content" :bordered="false" :style="{ backgroundColor: message.role === 'user' ? '#f0f9eb' : '#f5f5f5' }">
          <div class="markdown-content" v-html="renderedContent"></div>
        </n-card>

        <!-- 空内容 + 工作中：显示加载骨架 -->
        <div v-if="!message.content && isWorking" class="loading-placeholder">
          <div class="skeleton-line" v-for="i in 3" :key="i" :style="{ width: `${80 - i * 15}%` }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NAvatar, NCard, NTag, NCollapse, NCollapseItem } from 'naive-ui'
import type { Message } from '@/api'
import type { ExtendedMessage } from '@/stores/chat'
import AgentStep from './AgentStep.vue'
import DiffView from './DiffView.vue'
import AgentWorkingBar from './AgentWorkingBar.vue'

const props = defineProps<{
  message: Message | ExtendedMessage
  isWorking?: boolean
}>()

const msg = computed(() => props.message as ExtendedMessage)

const hasSteps = computed(() => {
  return msg.value.steps && msg.value.steps.length > 0
})

const hasDiffs = computed(() => {
  return msg.value.diffs && msg.value.diffs.length > 0
})

const hasThinking = computed(() => {
  return msg.value.thinkingContent && msg.value.thinkingContent.length > 0
})

const thinkingContent = computed(() => msg.value.thinkingContent || '')

// 计算 Agent 工作状态
const agentIteration = computed(() => {
  const steps = msg.value.steps
  if (!steps || steps.length === 0) return 0
  // 从最后一个有 iteration 的 step 获取
  for (let i = steps.length - 1; i >= 0; i--) {
    if ((steps[i] as any).iteration) return (steps[i] as any).iteration
  }
  return 0
})

const totalSteps = computed(() => msg.value.steps?.length || 0)

const currentStepLabel = computed(() => {
  const steps = msg.value.steps
  if (!steps || steps.length === 0) return ''
  const last = steps[steps.length - 1]
  if (last.status === 'running') {
    return toolLabel(last.tool)
  }
  return ''
})

const elapsed = computed(() => {
  const steps = msg.value.steps
  if (!steps || steps.length === 0) return 0
  // 基于步骤数估算（简化方案，后续可加时间戳）
  return Math.round(steps.length * 1.5)
})

const totalTime = computed(() => {
  const steps = msg.value.steps
  if (!steps || steps.length === 0) return 0
  return Math.round(steps.length * 2.0)
})

function toolLabel(tool: string): string {
  const map: Record<string, string> = {
    read_file: '📄 读取文件',
    write_file: '✏️ 写入文件',
    edit_file: '🔧 编辑文件',
    list_directory: '📁 列出目录',
    run_command: '▶️ 执行命令',
    web_search: '🔍 联网搜索',
    remember: '🧠 持久记忆',
    recall_memory: '🔍 检索记忆',
    create_sub_agent: '🤖 创建子Agent',
    invoke_sub_agent: '🤖 调用子Agent',
    create_goal: '🎯 创建目标',
    create_snapshot: '📸 创建快照',
    git_commit_evolution: '📦 Git提交',
  }
  return map[tool] || `🔧 ${tool}`
}

const renderedContent = computed(() => {
  return props.message.content
    .replace(/\n/g, '<br>')
    .replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
})
</script>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.chat-message.is-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
}

.message-content {
  flex: 1;
  max-width: 80%;
}

.chat-message.is-user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-header {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
}

.message-body {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-diffs {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.thinking-collapse {
  margin-bottom: 4px;
}

.thinking-content {
  background: #f8f9fa;
  padding: 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: #555;
}

.markdown-content {
  line-height: 1.6;
  word-break: break-word;
}

.markdown-content :deep(pre) {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-content :deep(code) {
  background: #e8e8e8;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}

.markdown-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.loading-placeholder {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 0;
}

.skeleton-line {
  height: 12px;
  background: linear-gradient(90deg, #e8e8e8 25%, #f5f5f5 50%, #e8e8e8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>

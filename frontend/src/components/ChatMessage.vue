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
        <n-tag v-if="message.role === 'assistant' && hasSteps" type="info" size="small" :bordered="false" style="margin-left: 8px;">
          Agent
        </n-tag>
      </div>
      <div class="message-body">
        <!-- 思考内容展示（DeepSeek 思考模式） -->
        <n-collapse v-if="hasThinking" class="thinking-collapse">
          <n-collapse-item title="💭 思考过程" name="thinking">
            <pre class="thinking-content">{{ (message as ExtendedMessage).thinkingContent }}</pre>
          </n-collapse-item>
        </n-collapse>

        <!-- Agent 步骤展示 -->
        <div v-if="hasSteps" class="agent-steps">
          <agent-step
            v-for="step in (message as ExtendedMessage).steps"
            :key="step.id"
            :tool="step.tool"
            :tool-args="step.toolArgs"
            :result="step.result"
            :status="step.status"
          />
        </div>

        <!-- Diff 展示 -->
        <div v-if="hasDiffs" class="agent-diffs">
          <diff-view
            v-for="(diff, index) in (message as ExtendedMessage).diffs"
            :key="index"
            :path="diff.path"
            :old-content="diff.oldContent"
            :new-content="diff.newContent"
          />
        </div>

        <!-- 消息内容 -->
        <n-card :bordered="false" :style="{ backgroundColor: message.role === 'user' ? '#f0f9eb' : '#f5f5f5' }">
          <div class="markdown-content" v-html="renderedContent"></div>
        </n-card>
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

const props = defineProps<{
  message: Message | ExtendedMessage
}>()

const hasSteps = computed(() => {
  const msg = props.message as ExtendedMessage
  return msg.steps && msg.steps.length > 0
})

const hasDiffs = computed(() => {
  const msg = props.message as ExtendedMessage
  return msg.diffs && msg.diffs.length > 0
})

const hasThinking = computed(() => {
  const msg = props.message as ExtendedMessage
  return msg.thinkingContent && msg.thinkingContent.length > 0
})

const renderedContent = computed(() => {
  // 简单的换行处理，后续可以集成 markdown-it
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
  gap: 6px;
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
</style>

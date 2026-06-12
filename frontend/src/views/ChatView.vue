<template>
  <div class="chat-view">
    <div class="chat-header">
      <n-space justify="space-between" align="center">
        <n-space align="center">
          <n-h3 style="margin: 0;">AI 对话</n-h3>
          <n-tooltip>
            <template #trigger>
              <n-switch
                :value="chatStore.agentMode"
                @update:value="chatStore.toggleAgentMode"
              >
                <template #checked>Agent</template>
                <template #unchecked>Chat</template>
              </n-switch>
            </template>
            开启 Agent 模式后，AI 可以读取文件、编辑代码和执行命令
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-switch
                :value="chatStore.deepThinking"
                @update:value="chatStore.toggleDeepThinking"
              >
                <template #checked>深度</template>
                <template #unchecked>普通</template>
              </n-switch>
            </template>
            开启深度思考后，AI 会进行更深入的推理和分析
          </n-tooltip>
          <n-tooltip>
            <template #trigger>
              <n-switch
                :value="chatStore.webSearch"
                @update:value="chatStore.toggleWebSearch"
              >
                <template #checked>联网</template>
                <template #unchecked>离线</template>
              </n-switch>
            </template>
            开启联网搜索后，AI 可以搜索互联网获取实时信息
          </n-tooltip>
        </n-space>
        <n-button quaternary circle @click="handleClear" :disabled="chatStore.messages.length === 0">
          <template #icon>
            <n-icon><trash /></n-icon>
          </template>
        </n-button>
      </n-space>
    </div>

    <div class="chat-messages" ref="messagesContainer">
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <n-empty :description="chatStore.agentMode ? 'Agent 模式已开启，让 AI 帮你写代码' : '开始新的对话'" />
      </div>
      <chat-message
        v-for="(msg, index) in chatStore.messages"
        :key="index"
        :message="msg"
        :is-working="chatStore.isStreaming && index === chatStore.messages.length - 1 && msg.role === 'assistant'"
      />
    </div>

    <chat-input
      @send="handleSend"
      :disabled="chatStore.isStreaming"
    />

    <!-- 停止按钮：流式输出时显示 -->
    <div v-if="chatStore.isStreaming" class="stop-button-container">
      <n-button type="error" @click="handleStop" size="small">
        <template #icon>
          <n-icon><stop-circle-outline /></n-icon>
        </template>
        停止生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from 'vue'
import { NH3, NButton, NIcon, NSpace, NEmpty, NSwitch, NTooltip, useDialog } from 'naive-ui'
import { Trash, StopCircleOutline } from '@vicons/ionicons5'
import { useChatStore } from '@/stores/chat'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'

const chatStore = useChatStore()
const dialog = useDialog()
const messagesContainer = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function handleSend(message: string) {
  chatStore.sendMessage(message)
}

function handleStop() {
  chatStore.stopGeneration()
}

function handleClear() {
  dialog.warning({
    title: '清空对话',
    content: '确定要清空所有对话记录吗？',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: () => {
      chatStore.clearMessages()
    },
  })
}

// 监听消息变化，自动滚动到底部
watch(
  () => chatStore.messages.length,
  () => scrollToBottom()
)

watch(
  () => chatStore.messages[chatStore.messages.length - 1]?.content,
  () => scrollToBottom()
)

onMounted(() => {
  chatStore.loadMessages()
})
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--n-border-color, #e8e8e8);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.stop-button-container {
  display: flex;
  justify-content: center;
  padding: 8px 16px;
  border-top: 1px solid var(--n-border-color, #e8e8e8);
}
</style>

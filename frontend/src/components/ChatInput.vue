<template>
  <div class="chat-input">
    <n-input
      v-model:value="inputText"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 5 }"
      placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
      @keydown="handleKeydown"
      :disabled="disabled"
    />
    <n-button
      type="primary"
      :disabled="!inputText.trim() || disabled"
      @click="handleSend"
      :loading="disabled"
    >
      <template #icon>
        <n-icon><send /></n-icon>
      </template>
      发送
    </n-button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NInput, NButton, NIcon } from 'naive-ui'
import { Send } from '@vicons/ionicons5'

const props = defineProps<{
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: [message: string]
}>()

const inputText = ref('')

function handleSend() {
  if (inputText.value.trim() && !props.disabled) {
    emit('send', inputText.value)
    inputText.value = ''
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<style scoped>
.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px;
  background: #fff;
  border-top: 1px solid #e8e8e8;
}

.chat-input :deep(.n-input) {
  flex: 1;
}
</style>

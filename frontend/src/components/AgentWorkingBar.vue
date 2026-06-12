<template>
  <div class="agent-working-bar" :class="{ 'is-done': isDone }">
    <div class="bar-main">
      <!-- 状态图标 -->
      <span class="bar-icon">
        <span v-if="isDone" class="done-icon">✅</span>
        <span v-else class="spinner"></span>
      </span>

      <!-- 状态文字 -->
      <span class="bar-text">
        <template v-if="isDone">
          完成 · 共 {{ totalSteps }} 个工具调用 · {{ totalTime }}s
        </template>
        <template v-else-if="currentStep">
          {{ currentStep }}
        </template>
        <template v-else>
          正在思考...
        </template>
      </span>

      <!-- 右侧信息 -->
      <span class="bar-meta" v-if="!isDone">
        <span v-if="iteration > 0" class="meta-item">第 {{ iteration }} 轮</span>
        <span v-if="totalSteps > 0" class="meta-item">{{ totalSteps }} 个工具</span>
        <span v-if="elapsed > 0" class="meta-item">{{ elapsed }}s</span>
      </span>
    </div>

    <!-- 进度条（脉冲动画） -->
    <div v-if="!isDone" class="bar-progress">
      <div class="progress-track">
        <div class="progress-fill"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  isDone: boolean
  iteration: number
  totalSteps: number
  currentStep: string
  elapsed: number
  totalTime: number
}>()

// 工具友好名称映射
const toolFriendlyNames: Record<string, string> = {
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

function friendlyName(tool: string): string {
  return toolFriendlyNames[tool] || `🔧 ${tool}`
}
</script>

<style scoped>
.agent-working-bar {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border: 1px solid #2a3a5e;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  transition: all 0.3s ease;
}

.agent-working-bar.is-done {
  background: linear-gradient(135deg, #0d2818 0%, #1a3a2a 100%);
  border-color: #2a5a3a;
}

.bar-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bar-icon {
  flex-shrink: 0;
  width: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.done-icon {
  font-size: 14px;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #4a6fa5;
  border-top-color: #60a5fa;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.bar-text {
  flex: 1;
  color: #a0c4ff;
  font-weight: 500;
}

.is-done .bar-text {
  color: #6ee7b7;
}

.bar-meta {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

.meta-item {
  color: #7a8ba8;
  font-size: 11px;
  background: rgba(255,255,255,0.06);
  padding: 2px 8px;
  border-radius: 10px;
}

.bar-progress {
  margin-top: 6px;
}

.progress-track {
  height: 2px;
  background: rgba(255,255,255,0.08);
  border-radius: 1px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, #60a5fa, #a78bfa, #60a5fa);
  background-size: 200% 100%;
  animation: pulse 2s ease-in-out infinite;
  border-radius: 1px;
}

@keyframes pulse {
  0%, 100% { transform: translateX(-100%); }
  50% { transform: translateX(100%); }
}
</style>

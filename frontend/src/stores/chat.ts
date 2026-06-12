import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { messagesApi, chatApi, type Message, type AgentEvent } from '@/api'

// Agent 步骤类型
export interface AgentStep {
  id: string
  tool: string
  toolArgs?: Record<string, any>
  result?: string
  status: 'running' | 'success' | 'error'
}

// Agent Diff 类型
export interface AgentDiff {
  path: string
  oldContent: string
  newContent: string
}

// 扩展消息类型，包含 agent 步骤和思考内容
export interface ExtendedMessage extends Message {
  steps?: AgentStep[]
  diffs?: AgentDiff[]
  thinkingContent?: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ExtendedMessage[]>([])
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const agentMode = ref(true)
  const deepThinking = ref(true)
  const webSearch = ref(true)
  const abortController = ref<AbortController | null>(null)

  // 加载历史消息
  async function loadMessages() {
    isLoading.value = true
    try {
      const response = await messagesApi.list()
      messages.value = response.data
    } catch (error) {
      console.error('加载消息失败:', error)
    } finally {
      isLoading.value = false
    }
  }

  // 发送消息
  async function sendMessage(content: string) {
    if (!content.trim() || isStreaming.value) return

    // 创建新的 AbortController
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    // 添加用户消息到列表
    messages.value.push({
      role: 'user',
      content: content.trim(),
    })

    // 准备流式接收
    isStreaming.value = true
    streamingContent.value = ''

    // 添加 AI 消息占位符（扩展类型）
    const aiMessage: ExtendedMessage = {
      role: 'assistant',
      content: '',
      steps: [],
      diffs: [],
      thinkingContent: '',
    }
    const aiMessageIndex = messages.value.length
    messages.value.push(aiMessage)

    try {
      if (agentMode.value) {
        // Agent 模式
        await chatApi.streamAgent(content, 'agent', deepThinking.value, webSearch.value, {
          onContent: (chunk) => {
            streamingContent.value += chunk
            const msg = messages.value[aiMessageIndex]
            if (msg) msg.content = streamingContent.value
          },
          onEvent: (event: AgentEvent) => {
            const msg = messages.value[aiMessageIndex]
            if (!msg) return

            // 处理思考内容（DeepSeek 思考模式）
            if (event.type === 'thinking' && event.content) {
              msg.thinkingContent = (msg.thinkingContent || '') + event.content
            }

            // 处理工具调用
            if (event.type === 'tool_call' && event.tool) {
              msg.steps = msg.steps || []
              msg.steps.push({
                id: event.call_id || Date.now().toString(),
                tool: event.tool,
                toolArgs: event.tool_args,
                status: 'running',
              })
            }

            // 处理工具结果
            if (event.type === 'tool_result' && event.call_id) {
              msg.steps = msg.steps || []
              const step = msg.steps.find(s => s.id === event.call_id)
              if (step) {
                step.result = event.tool_result
                step.status = event.tool_result?.startsWith('错误') ? 'error' : 'success'
              }
            }

            // 处理 diff
            if (event.type === 'diff' && event.diff_path) {
              msg.diffs = msg.diffs || []
              msg.diffs.push({
                path: event.diff_path,
                oldContent: event.diff_old || '',
                newContent: event.diff_new || '',
              })
            }
          },
          onDone: () => {
            isStreaming.value = false
            streamingContent.value = ''
            abortController.value = null
          },
          onError: (error) => {
            console.error('Agent 错误:', error)
            // 将错误信息显示到消息中
            const msg = messages.value[aiMessageIndex]
            if (msg && error) {
              msg.content = (msg.content || '') + `\n\n⚠️ ${error}`
            }
          },
        }, signal)
      } else {
        // 简单模式
        await chatApi.stream(
          content,
          deepThinking.value,
          (chunk) => {
            streamingContent.value += chunk
            const msg = messages.value[aiMessageIndex]
            if (msg) msg.content = streamingContent.value
          },
          () => {
            isStreaming.value = false
            streamingContent.value = ''
            abortController.value = null
          },
          signal
        )
      }
    } catch (error: any) {
      // 忽略中止错误（用户主动停止）
      if (error.name === 'AbortError') {
        console.log('用户停止了 AI 回复')
      } else {
        console.error('发送消息失败:', error)
        const msg = messages.value[aiMessageIndex]
        if (msg) msg.content = '抱歉，发生了错误，请重试。'
      }
      isStreaming.value = false
      streamingContent.value = ''
      abortController.value = null
    }
  }

  // 停止 AI 回复
  async function stopGeneration() {
    if (!isStreaming.value) return

    // 通知后端停止
    try {
      await chatApi.stop()
    } catch (e) {
      // 忽略错误
    }

    // 中止前端请求
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }

    isStreaming.value = false
    streamingContent.value = ''
  }

  // 清空对话
  async function clearMessages() {
    try {
      await messagesApi.clear()
      messages.value = []
    } catch (error) {
      console.error('清空消息失败:', error)
    }
  }

  // 切换 Agent 模式
  function toggleAgentMode() {
    agentMode.value = !agentMode.value
  }

  // 切换深度思考模式
  function toggleDeepThinking() {
    deepThinking.value = !deepThinking.value
  }

  // 切换联网搜索
  function toggleWebSearch() {
    webSearch.value = !webSearch.value
  }

  return {
    messages,
    isLoading,
    isStreaming,
    streamingContent,
    agentMode,
    deepThinking,
    webSearch,
    loadMessages,
    sendMessage,
    clearMessages,
    toggleAgentMode,
    toggleDeepThinking,
    toggleWebSearch,
    stopGeneration,
  }
})

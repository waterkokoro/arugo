<template>
  <div class="settings-view">
    <n-card title="模型配置" :bordered="false">
      <n-form
        ref="formRef"
        :model="settings"
        :label-placement="'left'"
        label-width="120"
      >
        <n-form-item label="API Key" path="api_key">
          <n-input
            v-model:value="settings.api_key"
            type="password"
            show-password-on="click"
            placeholder="请输入 API Key"
          />
        </n-form-item>

        <n-form-item label="Base URL" path="base_url">
          <n-input
            v-model:value="settings.base_url"
            placeholder="https://api.openai.com/v1"
          />
        </n-form-item>

        <n-form-item label="模型名称" path="model_name">
          <n-input
            v-model:value="settings.model_name"
            placeholder="gpt-3.5-turbo"
          />
        </n-form-item>

        <n-form-item label="System Prompt" path="system_prompt">
          <n-input
            v-model:value="settings.system_prompt"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="You are a helpful assistant."
          />
        </n-form-item>

        <n-form-item label="上下文窗口大小" path="context_window_size">
          <n-input-number
            v-model:value="settings.context_window_size"
            :min="1"
            :max="1000"
            placeholder="500"
          />
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              保留最近 N 条消息作为上下文，默认 500
            </span>
          </template>
        </n-form-item>

        <n-divider title-placement="left">Agent 工具配置</n-divider>

        <n-form-item label="工作目录" path="workspace_dir">
          <n-input
            v-model:value="settings.workspace_dir"
            placeholder="留空则使用项目根目录"
          />
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              Agent 工具只能操作此目录内的文件，防止误操作
            </span>
          </template>
        </n-form-item>

        <n-form-item label="允许的命令" path="allowed_commands">
          <n-input
            v-model:value="settings.allowed_commands"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest"
          />
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              Agent 可执行的命令白名单，逗号分隔
            </span>
          </template>
        </n-form-item>

        <n-divider title-placement="left">联网搜索配置</n-divider>

        <n-form-item label="搜索服务商" path="search_provider">
          <n-radio-group v-model:value="settings.search_provider">
            <n-space>
              <n-radio value="auto">自动（推荐）</n-radio>
              <n-radio value="tavily">Tavily</n-radio>
              <n-radio value="serper">Serper (Google)</n-radio>
              <n-radio value="brave">Brave</n-radio>
              <n-radio value="anysearch_free">AnySearch Free</n-radio>
            </n-space>
          </n-radio-group>
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              自动模式会优先使用已配置 Key 的服务商，AnySearch Free 作为兑底
            </span>
          </template>
        </n-form-item>

        <n-form-item v-if="showKeyInput('tavily')" label="Tavily API Key">
          <n-input-group>
            <n-input
              v-model:value="apiKeys.tavily"
              type="password"
              show-password-on="click"
              placeholder="tvly-xxx"
            />
            <n-button @click="handleVerifyKey('tavily')" :loading="verifyingKey === 'tavily'">
              验证
            </n-button>
          </n-input-group>
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              注册即送 1000次/月：<n-a href="https://tavily.com" target="_blank">申请地址</n-a>
            </span>
          </template>
        </n-form-item>

        <n-form-item v-if="showKeyInput('serper')" label="Serper API Key">
          <n-input-group>
            <n-input
              v-model:value="apiKeys.serper"
              type="password"
              show-password-on="click"
              placeholder="serper key"
            />
            <n-button @click="handleVerifyKey('serper')" :loading="verifyingKey === 'serper'">
              验证
            </n-button>
          </n-input-group>
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              注册送 2500 次，中文搜索最好：<n-a href="https://serper.dev" target="_blank">申请地址</n-a>
            </span>
          </template>
        </n-form-item>

        <n-form-item v-if="showKeyInput('brave')" label="Brave API Key">
          <n-input-group>
            <n-input
              v-model:value="apiKeys.brave"
              type="password"
              show-password-on="click"
              placeholder="brave key"
            />
            <n-button @click="handleVerifyKey('brave')" :loading="verifyingKey === 'brave'">
              验证
            </n-button>
          </n-input-group>
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              免费 2000次/月：<n-a href="https://brave.com/search/api/" target="_blank">申请地址</n-a>
            </span>
          </template>
        </n-form-item>

        <n-divider title-placement="left">🦜 飞书机器人配置</n-divider>

        <n-form-item label="启用飞书机器人">
          <n-switch v-model:value="feishu.enabled" />
          <template #feedback>
            <span style="color: #999; font-size: 12px;">
              使用 WebSocket 长连接模式，无需公网 IP。需先在
              <n-a href="https://open.feishu.cn/app" target="_blank">飞书开放平台</n-a>
              创建企业自建应用。
            </span>
          </template>
        </n-form-item>

        <n-form-item v-if="feishu.enabled" label="App ID">
          <n-input
            v-model:value="feishu.app_id"
            placeholder="cli_xxxxxxxxxxxx"
          />
        </n-form-item>

        <n-form-item v-if="feishu.enabled" label="App Secret">
          <n-input
            v-model:value="feishu.app_secret"
            type="password"
            show-password-on="click"
            placeholder="飞书应用 App Secret"
          />
        </n-form-item>

        <n-form-item v-if="feishu.enabled" label="验证 Token">
          <n-input
            v-model:value="feishu.verification_token"
            type="password"
            show-password-on="click"
            placeholder="事件订阅 Verification Token（可选）"
          />
        </n-form-item>

        <n-form-item v-if="feishu.enabled && feishuStatus.configured">
          <n-space>
            <n-tag :type="feishuStatus.connected ? 'success' : 'warning'" size="small">
              {{ feishuStatus.connected ? '🟢 已连接' : '🟡 未连接' }}
            </n-tag>
            <n-button size="small" @click="handleRestartFeishu" :loading="restarting">
              重启机器人
            </n-button>
          </n-space>
        </n-form-item>

        <n-form-item>
          <n-space>
            <n-button type="primary" @click="handleSave" :loading="saving">
              保存配置
            </n-button>
            <n-button @click="handleReset">
              重置
            </n-button>
          </n-space>
        </n-form-item>
      </n-form>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NInputNumber, NInputGroup,
  NButton, NSpace, NDivider, NRadio, NRadioGroup, NA,
  NSwitch, NTag,
  useMessage
} from 'naive-ui'
import { settingsApi, feishuApi, type Settings, type FeishuStatus } from '@/api'

const message = useMessage()

const defaultSettings: Settings = {
  api_key: '',
  base_url: 'https://api.openai.com/v1',
  model_name: 'gpt-3.5-turbo',
  system_prompt: 'You are a helpful assistant.',
  context_window_size: 500,
  workspace_dir: '',
  allowed_commands: 'ls,cat,head,tail,grep,find,git status,git diff,git log,git add,git commit,python,pip,npm,node,pytest',
  search_provider: 'auto',
  search_api_keys: '{}',
}

const settings = ref<Settings>({ ...defaultSettings })
const saving = ref(false)
const verifyingKey = ref<string | null>(null)

// 解析 search_api_keys JSON 为响应式对象
const apiKeys = reactive<Record<string, string>>({
  tavily: '',
  serper: '',
  brave: '',
})

// 根据当前服务商选择显示哪些 Key 输入框
function showKeyInput(provider: string): boolean {
  const sp = settings.value.search_provider
  return sp === 'auto' || sp === provider
}

async function loadSettings() {
  try {
    const response = await settingsApi.get()
    settings.value = response.data
    // 解析 api keys
    try {
      const keys = JSON.parse(response.data.search_api_keys || '{}')
      apiKeys.tavily = keys.tavily || ''
      apiKeys.serper = keys.serper || ''
      apiKeys.brave = keys.brave || ''
    } catch {
      // ignore
    }
  } catch (error) {
    message.error('加载配置失败')
  }
}

async function handleSave() {
  // 将 apiKeys 序列化到 settings
  settings.value.search_api_keys = JSON.stringify({
    tavily: apiKeys.tavily,
    serper: apiKeys.serper,
    brave: apiKeys.brave,
  })
  saving.value = true
  try {
    await settingsApi.update(settings.value)
    // 同时保存飞书配置
    if (feishu.enabled) {
      await feishuApi.updateConfig({
        enabled: feishu.enabled,
        app_id: feishu.app_id,
        app_secret: feishu.app_secret,
        verification_token: feishu.verification_token,
      })
    } else {
      await feishuApi.updateConfig({
        enabled: false,
        app_id: feishu.app_id,
        app_secret: '',
        verification_token: '',
      })
    }
    message.success('配置已保存')
    await loadFeishuConfig()
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleVerifyKey(provider: string) {
  const key = apiKeys[provider]
  if (!key) {
    message.warning('请先输入 API Key')
    return
  }
  verifyingKey.value = provider
  try {
    const res = await settingsApi.verifySearchKey(provider, key)
    if (res.data.valid) {
      message.success(`${provider} API Key 验证通过`)
    } else {
      message.error(`${provider} API Key 无效`)
    }
  } catch {
    message.error(`${provider} API Key 验证失败`)
  } finally {
    verifyingKey.value = null
  }
}

// ========================================
// 飞书配置
// ========================================
const feishu = reactive({
  enabled: false,
  app_id: '',
  app_secret: '',
  verification_token: '',
})
const feishuStatus = ref<FeishuStatus>({
  enabled: false,
  app_id: '',
  has_secret: false,
  has_verification_token: false,
  connected: false,
  event_types: [],
})
const restarting = ref(false)

async function loadFeishuConfig() {
  try {
    const res = await feishuApi.getConfig()
    feishuStatus.value = res.data
    feishu.enabled = res.data.enabled
    feishu.app_id = res.data.app_id
    // secret 不填充，需要用户重新输入
  } catch {
    // 忽略
  }
}

async function handleRestartFeishu() {
  restarting.value = true
  try {
    const res = await feishuApi.restart()
    message.info(res.data.message)
    // 刷新状态
    await loadFeishuConfig()
  } catch {
    message.error('重启失败')
  } finally {
    restarting.value = false
  }
}

function handleReset() {
  settings.value = { ...defaultSettings }
  apiKeys.tavily = ''
  apiKeys.serper = ''
  apiKeys.brave = ''
  feishu.enabled = false
  feishu.app_id = ''
  feishu.app_secret = ''
  feishu.verification_token = ''
}

onMounted(() => {
  loadSettings()
  loadFeishuConfig()
})
</script>

<style scoped>
.settings-view {
  max-width: 600px;
  margin: 0 auto;
  padding: 24px;
}
</style>

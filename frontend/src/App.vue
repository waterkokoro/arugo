<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import {
  NLayout, NLayoutHeader, NLayoutContent,
  NMenu, NIcon, NConfigProvider, zhCN, dateZhCN,
  NDialogProvider, NMessageProvider
} from 'naive-ui'
import { computed, h } from 'vue'
import { ChatboxOutline, SettingsOutline } from '@vicons/ionicons5'

const route = useRoute()

const menuOptions = [
  {
    label: () => h(RouterLink, { to: '/' }, { default: () => '对话' }),
    key: 'chat',
    icon: () => h(NIcon, null, { default: () => h(ChatboxOutline) }),
  },
  {
    label: () => h(RouterLink, { to: '/settings' }, { default: () => '设置' }),
    key: 'settings',
    icon: () => h(NIcon, null, { default: () => h(SettingsOutline) }),
  },
]

const activeKey = computed(() => {
  return route.name as string
})
</script>

<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-dialog-provider>
        <n-layout style="height: 100vh;">
          <n-layout-header bordered style="padding: 0 16px;">
            <n-menu
              mode="horizontal"
              :options="menuOptions"
              :value="activeKey"
              style="max-width: 300px;"
            />
          </n-layout-header>
          <n-layout-content style="height: calc(100vh - 64px);">
            <router-view v-slot="{ Component }">
              <keep-alive>
                <component :is="Component" />
              </keep-alive>
            </router-view>
          </n-layout-content>
        </n-layout>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
    Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}
</style>

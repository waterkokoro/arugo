<template>
  <div class="management-view">
    <n-tabs type="line" animated v-model:value="activeTab">
      <!-- 概览 -->
      <n-tab-pane name="overview" tab="📊 概览">
        <OverviewPanel />
      </n-tab-pane>

      <!-- 角色模板 -->
      <n-tab-pane name="templates" tab="🎭 角色模板">
        <TemplatesPanel />
      </n-tab-pane>

      <!-- 子Agent -->
      <n-tab-pane name="agents" tab="🤖 子Agent">
        <AgentsPanel />
      </n-tab-pane>

      <!-- 目标 -->
      <n-tab-pane name="goals" tab="🎯 目标">
        <GoalsPanel />
      </n-tab-pane>

      <!-- 快照 -->
      <n-tab-pane name="snapshots" tab="📸 快照">
        <SnapshotsPanel />
      </n-tab-pane>

      <!-- 记忆 -->
      <n-tab-pane name="memories" tab="🧠 记忆">
        <MemoriesPanel />
      </n-tab-pane>

      <!-- 进化日志 -->
      <n-tab-pane name="evolution" tab="📈 进化">
        <EvolutionPanel />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { NTabs, NTabPane } from 'naive-ui'
import OverviewPanel from '../components/OverviewPanel.vue'
import TemplatesPanel from '../components/TemplatesPanel.vue'
import AgentsPanel from '../components/AgentsPanel.vue'
import GoalsPanel from '../components/GoalsPanel.vue'
import SnapshotsPanel from '../components/SnapshotsPanel.vue'
import MemoriesPanel from '../components/MemoriesPanel.vue'
import EvolutionPanel from '../components/EvolutionPanel.vue'

const activeTab = ref('overview')
</script>

<style scoped>
.management-view {
  max-width: 960px;
  margin: 0 auto;
  padding: 16px 24px;
}
</style>

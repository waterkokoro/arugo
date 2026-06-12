<template>
  <div class="diff-view">
    <div class="diff-header">
      <n-text depth="3" class="diff-path">{{ path }}</n-text>
    </div>
    <div class="diff-content">
      <div class="diff-side diff-old">
        <div class="diff-side-header">删除</div>
        <pre class="diff-code">{{ oldContent }}</pre>
      </div>
      <div class="diff-side diff-new">
        <div class="diff-side-header">新增</div>
        <pre class="diff-code">{{ newContent }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { NText } from 'naive-ui'

defineProps<{
  path: string
  oldContent: string
  newContent: string
}>()
</script>

<style scoped>
.diff-view {
  border: 1px solid var(--n-border-color);
  border-radius: 6px;
  overflow: hidden;
  font-size: 12px;
}

.diff-header {
  padding: 8px 12px;
  background: var(--n-color-modal);
  border-bottom: 1px solid var(--n-border-color);
}

.diff-path {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-weight: 500;
}

.diff-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
}

.diff-side {
  overflow-x: auto;
}

.diff-old {
  background: rgba(255, 0, 0, 0.05);
  border-right: 1px solid var(--n-border-color);
}

.diff-new {
  background: rgba(0, 255, 0, 0.05);
}

.diff-side-header {
  padding: 4px 12px;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  border-bottom: 1px solid var(--n-border-color);
}

.diff-old .diff-side-header {
  color: #d32f2f;
}

.diff-new .diff-side-header {
  color: #388e3c;
}

.diff-code {
  padding: 8px 12px;
  margin: 0;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}
</style>

<template>
  <div class="message" :class="[message.role]">
    <div class="message-content">
      <div v-if="message.thinking" class="thinking-block">
        <div class="thinking-header" @click="showThinking = !showThinking">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: showThinking }">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
          <span>思考过程</span>
        </div>
        <div v-if="showThinking" class="thinking-content">{{ message.thinking }}</div>
      </div>
      <div class="message-text" v-html="renderedContent"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

const showThinking = ref(false)

const renderedContent = computed(() => {
  const content = props.message.content || ''
  try {
    return marked(content)
  } catch (e) {
    return content
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }
})
</script>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.user {
  justify-content: flex-end;
}

.message-content {
  max-width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.message.user .message-content {
  align-items: flex-end;
}

.thinking-block {
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 8px;
}

.thinking-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #fef08a;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: #92400e;
  user-select: none;
  transition: background 0.2s;
}

.thinking-header:hover {
  background: #fde047;
}

.thinking-header svg {
  width: 14px;
  height: 14px;
  transition: transform 0.2s;
}

.thinking-header svg.rotated {
  transform: rotate(180deg);
}

.thinking-content {
  padding: 10px 12px;
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-text {
  background: #f1f5f9;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: #1e293b;
  word-break: break-word;
}

.message-text :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.message-text :deep(code) {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
}

.message-text :deep(p) {
  margin: 8px 0;
}

.message-text :deep(p:first-child) {
  margin-top: 0;
}

.message-text :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text :deep(ul), .message-text :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.message-text :deep(blockquote) {
  border-left: 3px solid #0ea5e9;
  margin: 8px 0;
  padding-left: 12px;
  color: #64748b;
}

.message.user .message-text {
  background: #0ea5e9;
  color: white;
  border-radius: 16px;
}

.message.user .message-text :deep(pre) {
  background: rgba(0, 0, 0, 0.2);
}

.message.user .message-text :deep(blockquote) {
  border-left-color: rgba(255, 255, 255, 0.5);
}
</style>

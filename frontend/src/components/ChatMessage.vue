<template>
  <div class="message" :class="[message.role]">
    <div class="message-content">
      <!-- 加载状态 -->
      <div v-if="message.loading && sortedBlocks.length === 0 && !message.content" class="loading-indicator">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
      
      <!-- 按顺序渲染内容块 -->
      <template v-if="sortedBlocks.length > 0">
        <template v-for="(block, index) in sortedBlocks" :key="index">
          <!-- 思考内容块 -->
          <div v-if="block.type === 'thinking'" class="thinking-block">
            <div class="thinking-header" @click="toggleThinking(index)">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: isExpandedThinking(index) }">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
              <span>思考过程</span>
            </div>
            <div v-if="isExpandedThinking(index)" class="thinking-content">{{ block.content }}</div>
          </div>

          <!-- 工具调用块 -->
          <div v-if="block.type === 'tool_call'" class="tool-call-block">
            <div class="tool-call-header" @click="toggleToolCall(index)">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: expandedToolCall[index] }">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
              <span>工具调用: {{ block.tool_name }}</span>
            </div>
            <div v-if="expandedToolCall[index]" class="tool-call-args">
              <pre>{{ formatJson(block.arguments) }}</pre>
            </div>
          </div>

          <!-- 工具结果块 -->
          <div v-if="block.type === 'tool_result'" class="tool-result-block" :class="{ error: !block.success }">
            <div class="tool-result-header" @click="toggleToolResult(index)">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: expandedToolResult[index] }">
                <polyline points="6 9 12 15 18 9"></polyline>
              </svg>
              <span>{{ block.success ? '工具结果' : '工具错误' }}</span>
            </div>
            <div v-if="expandedToolResult[index]" class="tool-result-content">{{ truncateResult(block.result) }}</div>
          </div>

          <!-- 内容块 -->
          <div v-if="block.type === 'content'" class="message-text" v-html="renderContent(block.content)"></div>
        </template>
      </template>

      <!-- 兼容旧数据：没有blocks时的渲染 -->
      <template v-else>
        <div v-if="message.thinking" class="thinking-block">
          <div class="thinking-header" @click="showThinking = !showThinking">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ rotated: showThinking }">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
            <span>思考过程</span>
          </div>
          <div v-if="showThinking" class="thinking-content">{{ message.thinking }}</div>
        </div>

        <div v-if="message.tool_calls && message.tool_calls.length > 0" class="tool-calls-block">
          <div class="tool-calls-header">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
            </svg>
            <span>工具调用</span>
          </div>
          <div class="tool-calls-list">
            <div v-for="(tool, idx) in message.tool_calls" :key="idx" class="tool-call-item">
              <div class="tool-name">{{ tool.tool_name }}</div>
              <div v-if="tool.arguments" class="tool-args">
                <pre>{{ formatJson(tool.arguments) }}</pre>
              </div>
              <div v-if="tool.result" class="tool-result" :class="{ error: !tool.success }">
                <span class="result-label">{{ tool.success ? '结果:' : '错误:' }}</span>
                <span class="result-content">{{ truncateResult(tool.result) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="message-text" v-html="renderedContent"></div>
      </template>
      
      <!-- 用户消息显示复制按钮 -->
      <div v-if="message.role === 'user' && message.content" class="message-actions">
        <button class="copy-btn" @click="copyMessage" title="复制">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

const showThinking = ref(false)
const expandedThinking = ref({})
const expandedToolCall = ref({})
const expandedToolResult = ref({})

const sortedBlocks = computed(() => {
  if (!props.message.blocks) return []
  return [...props.message.blocks].sort((a, b) => (a.order || 0) - (b.order || 0))
})

function isExpandedThinking(index) {
  return expandedThinking.value[index] === true
}

function toggleThinking(index) {
  expandedThinking.value[index] = !expandedThinking.value[index]
}

function toggleToolCall(index) {
  expandedToolCall.value[index] = !expandedToolCall.value[index]
}

function toggleToolResult(index) {
  expandedToolResult.value[index] = !expandedToolResult.value[index]
}

const renderer = new marked.Renderer()

renderer.code = function(data) {
  let code = ''
  let language = ''
  
  if (typeof data === 'object') {
    code = data.text || data.raw || ''
    language = data.lang || ''
  } else {
    code = arguments[0] || ''
    language = arguments[1] || ''
  }
  
  const langLabel = language || 'code'
  const escapedCode = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  
  return `
    <div class="code-block-wrapper">
      <div class="code-header">
        <span class="code-lang">${langLabel}</span>
        <button class="code-copy-btn" onclick="copyCode(this)">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          <span>复制</span>
        </button>
      </div>
      <pre><code class="language-${language}">${escapedCode}</code></pre>
    </div>
  `
}

function renderContent(content) {
  if (!content) return ''
  try {
    return marked(content, { renderer })
  } catch (e) {
    return content.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
  }
}

const renderedContent = computed(() => {
  return renderContent(props.message.content)
})

function formatJson(obj) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch (e) {
    return String(obj)
  }
}

function truncateResult(result) {
  if (!result) return ''
  const str = String(result)
  return str.length > 500 ? str.substring(0, 500) + '...' : str
}

async function copyMessage() {
  if (!props.message.content) return
  
  try {
    await navigator.clipboard.writeText(props.message.content)
  } catch (err) {
    console.error('复制失败:', err)
  }
}

onMounted(() => {
  if (!window.copyCode) {
    window.copyCode = async function(btn) {
      const wrapper = btn.closest('.code-block-wrapper')
      const codeEl = wrapper.querySelector('pre code') || wrapper.querySelector('pre')
      const code = codeEl?.textContent || ''
      
      try {
        await navigator.clipboard.writeText(code)
        const span = btn.querySelector('span')
        const originalText = span.textContent
        span.textContent = '已复制!'
        btn.classList.add('copied')
        setTimeout(() => {
          span.textContent = originalText
          btn.classList.remove('copied')
        }, 2000)
      } catch (err) {
        console.error('复制失败:', err)
      }
    }
  }
})
</script>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  animation: fadeIn 0.3s ease-out;
  width: 80%;
  margin: 0 auto;
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

.message.assistant {
  justify-content: flex-start;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message.user .message-content {
  align-items: flex-end;
  max-width: 80%;
}

.message.assistant .message-content {
  align-items: flex-start;
  width: 80%;
}

.thinking-block {
  width: 100%;
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 10px;
  overflow: hidden;
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

.tool-call-block {
  width: 100%;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  overflow: hidden;
}

.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #dcfce7;
  font-size: 12px;
  font-weight: 500;
  color: #166534;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.tool-call-header:hover {
  background: #bbf7d0;
}

.tool-call-header svg {
  width: 14px;
  height: 14px;
  transition: transform 0.2s;
}

.tool-call-header svg.rotated {
  transform: rotate(180deg);
}

.tool-call-args {
  padding: 8px 12px;
  font-size: 11px;
  color: #64748b;
}

.tool-call-args pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-result-block {
  width: 100%;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  overflow: hidden;
}

.tool-result-block.error {
  background: #fef2f2;
  border-color: #fecaca;
}

.tool-result-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #dcfce7;
  font-size: 12px;
  font-weight: 500;
  color: #166534;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.tool-result-header:hover {
  background: #bbf7d0;
}

.tool-result-block.error .tool-result-header {
  background: #fee2e2;
  color: #dc2626;
}

.tool-result-block.error .tool-result-header:hover {
  background: #fecaca;
}

.tool-result-header svg {
  width: 14px;
  height: 14px;
  transition: transform 0.2s;
}

.tool-result-header svg.rotated {
  transform: rotate(180deg);
}

.tool-result-content {
  padding: 8px 12px;
  font-size: 11px;
  color: #166534;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-result-block.error .tool-result-content {
  color: #dc2626;
}

.tool-calls-block {
  width: 100%;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 10px;
  overflow: hidden;
}

.tool-calls-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #dcfce7;
  font-size: 12px;
  font-weight: 500;
  color: #166534;
}

.tool-calls-header svg {
  width: 14px;
  height: 14px;
}

.tool-calls-list {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-call-item {
  background: white;
  border-radius: 6px;
  padding: 8px 10px;
  border: 1px solid #e2e8f0;
}

.tool-name {
  font-weight: 600;
  font-size: 13px;
  color: #0d9488;
  margin-bottom: 4px;
}

.tool-args {
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}

.tool-args pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-result {
  font-size: 11px;
  color: #166534;
  background: #f0fdf4;
  padding: 6px 8px;
  border-radius: 4px;
  margin-top: 4px;
}

.tool-result.error {
  color: #dc2626;
  background: #fef2f2;
}

.result-label {
  font-weight: 500;
  margin-right: 4px;
}

.result-content {
  word-break: break-all;
}

.message-text {
  width: 100%;
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

.message-actions {
  visibility: hidden;
  margin-top: 4px;
}

.message.user:hover .message-actions {
  visibility: visible;
  display: flex;
  justify-content: flex-end;
}

.message-actions .copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.message-actions .copy-btn svg {
  width: 14px;
  height: 14px;
  color: #64748b;
}

.message-actions .copy-btn:hover {
  background: rgba(14, 165, 233, 0.1);
}

.message-actions .copy-btn:hover svg {
  color: #0ea5e9;
}

.message-text :deep(.code-block-wrapper) {
  position: relative;
  margin: 8px 0;
}

.message-text :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #334155;
  padding: 10px 16px;
  border-radius: 8px 8px 0 0;
  min-height: 40px;
}

.message-text :deep(.code-block-wrapper pre) {
  border-radius: 0 0 8px 8px;
  margin: 0;
}

.message-text :deep(.code-lang) {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
  display: flex;
  align-items: center;
}

.message-text :deep(.code-copy-btn) {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.1);
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  height: 28px;
}

.message-text :deep(.code-copy-btn:hover) {
  background: rgba(255, 255, 255, 0.2);
  color: #e2e8f0;
}

.message-text :deep(.code-copy-btn.copied) {
  color: #22c55e;
}

.message-text :deep(.code-copy-btn svg) {
  width: 14px;
  height: 14px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 0;
}

.loading-indicator .dot {
  width: 6px;
  height: 6px;
  background: #94a3b8;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-indicator .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-indicator .dot:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>

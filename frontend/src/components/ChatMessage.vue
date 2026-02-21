<template>
  <div class="message" :class="[message.role]">
    <div class="message-content">
      <!-- 加载状态 -->
      <div v-if="message.loading && sortedBlocks.length === 0 && !message.content" class="loading-indicator">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
      
      <!-- 文件卡片 -->
      <div v-if="message.files && message.files.length > 0" class="files-container">
        <div 
          v-for="(file, index) in message.files" 
          :key="index" 
          class="file-card"
        >
          <div class="file-icon">
            <FileIcon :filename="file.filename" :size="40" />
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.filename }}</span>
            <div class="file-meta">
              <span class="file-size">{{ formatSize(file.size) }}</span>
              <span class="file-type">{{ getFileExtension(file.filename) }}</span>
            </div>
          </div>
          <!-- 上传成功后的文件卡片不需要删除按钮 -->
          <!-- <button 
            v-if="message.role === 'user'" 
            @click="removeFile(index)" 
            class="remove-file-btn"
            title="删除文件"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button> -->
        </div>
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
          <div v-if="block.type === 'content'" class="message-text" v-html="renderMarkdown(block.content)"></div>
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

        <div v-if="message.content" class="message-text" v-html="renderMarkdown(message.content)"></div>
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
import { ref, computed, onMounted, shallowRef } from 'vue'
import { createHighlighter } from 'shiki'
import { marked } from 'marked'
import FileIcon from './FileIcon.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['removeFile'])

const showThinking = ref(false)
const expandedThinking = ref({})
const expandedToolCall = ref({})
const expandedToolResult = ref({})
const highlighter = shallowRef(null)

const langAliases = {
  'js': 'javascript',
  'ts': 'typescript',
  'py': 'python',
  'rb': 'ruby',
  'sh': 'bash',
  'yml': 'yaml',
  'md': 'markdown',
  'c++': 'cpp',
  'c#': 'csharp',
  'cs': 'csharp',
}

onMounted(async () => {
  try {
    highlighter.value = await createHighlighter({
      themes: ['github-light'],
      langs: ['javascript', 'typescript', 'python', 'java', 'cpp', 'c', 'go', 'rust', 'html', 'css', 'json', 'yaml', 'markdown', 'bash', 'shell', 'sql', 'xml', 'vue', 'jsx', 'tsx', 'text']
    })
  } catch (e) {
    console.error('Shiki 初始化失败:', e)
  }
})

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

function highlightCode(code, lang) {
  if (!highlighter.value) {
    return `<pre style="background: #f6f8fa; padding: 12px; border-radius: 8px; overflow-x: auto; border: 1px solid #e1e4e8;"><code style="color: #24292e; font-family: 'Fira Code', Consolas, monospace; font-size: 13px;">${escapeHtml(code)}</code></pre>`
  }
  
  const normalizedLang = lang ? lang.toLowerCase() : 'text'
  const mappedLang = langAliases[normalizedLang] || normalizedLang
  
  const loadedLangs = highlighter.value.getLoadedLanguages()
  const validLang = loadedLangs.includes(mappedLang) ? mappedLang : 'text'
  
  try {
    const html = highlighter.value.codeToHtml(code, {
      lang: validLang,
      theme: 'github-light'
    })
    return html
  } catch (e) {
    console.error('Shiki 高亮失败:', e, 'lang:', validLang)
    return `<pre style="background: #f6f8fa; padding: 12px; border-radius: 8px; overflow-x: auto; border: 1px solid #e1e4e8;"><code style="color: #24292e; font-family: 'Fira Code', Consolas, monospace; font-size: 13px;">${escapeHtml(code)}</code></pre>`
  }
}

function escapeHtml(text) {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const renderer = new marked.Renderer()

renderer.code = function(token) {
  let code = ''
  let language = ''
  
  if (typeof token === 'object') {
    code = token.text || token.raw || ''
    language = token.lang || ''
  } else {
    code = arguments[0] || ''
    language = arguments[1] || ''
  }
  
  const langLabel = language || 'text'
  const highlightedCode = highlightCode(code, language)
  
  return `<div class="code-block-wrapper">
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
    ${highlightedCode}
  </div>`
}

function renderMarkdown(content) {
  if (!content) return ''
  try {
    return marked.parse(content, { renderer, breaks: true, gfm: true })
  } catch (e) {
    console.error('Markdown 渲染失败:', e)
    return escapeHtml(content)
  }
}

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

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function getFileExtension(filename) {
  const parts = filename.split('.')
  if (parts.length > 1) {
    return parts[parts.length - 1].toUpperCase()
  }
  return 'FILE'
}

async function copyMessage() {
  if (!props.message.content) return
  
  try {
    await navigator.clipboard.writeText(props.message.content)
  } catch (err) {
    console.error('复制失败:', err)
  }
}

function removeFile(index) {
  if (props.message.files && props.message.files[index]) {
    const file = props.message.files[index]
    // 通知父组件删除文件
    emit('removeFile', file)
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
  width: 80%;
  max-width: 900px;
  margin: 0 auto;
}

.message.assistant {
  justify-content: flex-start;
  width: 80%;
  max-width: 900px;
  margin: 0 auto;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}

.message.user .message-content {
  align-items: flex-end;
  width: fit-content;
  max-width: 100%;
}

.message.user .message-content .message-text {
  width: fit-content;
  max-width: 100%;
}

.message.assistant .message-content {
  align-items: flex-start;
  width: 100%;
}

/* 文件容器样式 */
.files-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
  width: 100%;
}

/* 文件卡片样式 */
.file-card {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 10px 12px;
  border-radius: 10px;
  max-width: 250px;
  flex-shrink: 0;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.remove-file-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: #f1f5f9;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.remove-file-btn:hover {
  background: #fee2e2;
  transform: scale(1.05);
}

.remove-file-btn svg {
  width: 14px;
  height: 14px;
  color: #64748b;
}

.remove-file-btn:hover svg {
  color: #dc2626;
}

.file-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-1px);
}

/* 文件图标样式 */
.file-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 14px;
  font-weight: 500;
  color: #1E293B;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.file-size {
  font-size: 12px;
  color: #64748B;
}

.file-type {
  font-size: 11px;
  color: #94A3B8;
  text-transform: uppercase;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 6px;
  background: #F1F5F9;
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
  background: transparent;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 16px;
  line-height: 1.7;
  color: #1e293b;
  word-break: break-word;
  width: 100%;
  box-sizing: border-box;
}

.message-text :deep(pre) {
  background: #f6f8fa;
  color: #24292e;
  padding: 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 16px 0;
  border: 1px solid #e1e4e8;
  width: 100%;
  box-sizing: border-box;
}

.message-text :deep(pre code) {
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.message-text :deep(code) {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
}

.message-text :deep(p) {
  margin: 20px 0;
}

.message-text :deep(p:first-child) {
  margin-top: 0;
}

.message-text :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text :deep(ul), .message-text :deep(ol) {
  margin: 20px 0;
  padding-left: 28px;
}

.message-text :deep(li) {
  margin: 12px 0;
}

.message-text :deep(blockquote) {
  border-left: 3px solid #0ea5e9;
  margin: 20px 0;
  padding-left: 16px;
  color: #64748b;
}

.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4),
.message-text :deep(h5),
.message-text :deep(h6) {
  margin: 28px 0 20px 0;
  font-weight: 600;
  line-height: 1.4;
}

.message-text :deep(h1:first-child),
.message-text :deep(h2:first-child),
.message-text :deep(h3:first-child),
.message-text :deep(h4:first-child),
.message-text :deep(h5:first-child),
.message-text :deep(h6:first-child) {
  margin-top: 0;
}

.message-text :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 24px 0;
  font-size: 13px;
}

.message-text :deep(th),
.message-text :deep(td) {
  border: 1px solid #e2e8f0;
  padding: 10px 14px;
  text-align: left;
}

.message-text :deep(th) {
  background: #f1f5f9;
  font-weight: 600;
}

.message-text :deep(tr:nth-child(even)) {
  background: #f8fafc;
}

.message-text :deep(tr:hover) {
  background: #f1f5f9;
}

.message.user .message-text {
  background: #0ea5e9;
  color: white;
  border-radius: 16px;
}

.message.user .message-text :deep(pre) {
  background: rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.message.user .message-text :deep(blockquote) {
  border-left-color: rgba(255, 255, 255, 0.5);
}

.message.user .message-text :deep(table) {
  border-color: rgba(255, 255, 255, 0.3);
}

.message.user .message-text :deep(th),
.message.user .message-text :deep(td) {
  border-color: rgba(255, 255, 255, 0.3);
}

.message.user .message-text :deep(th) {
  background: rgba(255, 255, 255, 0.15);
}

.message.user .message-text :deep(tr:nth-child(even)) {
  background: rgba(255, 255, 255, 0.1);
}

.message.user .message-text :deep(tr:hover) {
  background: rgba(255, 255, 255, 0.15);
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
  width: 100%;
}

.message-text :deep(.code-block-wrapper pre) {
  margin: 0;
  padding: 12px 16px;
  overflow-x: auto;
  border-radius: 0 0 8px 8px;
  background: #f6f8fa !important;
  border: 1px solid #e1e4e8;
  border-top: none;
}

.message-text :deep(.code-block-wrapper pre code) {
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #24292e;
}

.message-text :deep(.code-block-wrapper .shiki) {
  background: #f6f8fa !important;
  padding: 12px 16px;
  margin: 0;
  border-radius: 0 0 8px 8px;
  overflow-x: auto;
}

.message-text :deep(.code-block-wrapper .shiki code) {
  display: block;
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.5;
}

.message-text :deep(.code-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f1f3f5;
  padding: 10px 16px;
  border-radius: 8px 8px 0 0;
  min-height: 40px;
  border: 1px solid #e1e4e8;
  border-bottom: none;
}

.message-text :deep(.code-lang) {
  font-size: 12px;
  color: #57606a;
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
  background: #ffffff;
  border: 1px solid #d0d7de;
  border-radius: 6px;
  color: #57606a;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  height: 28px;
}

.message-text :deep(.code-copy-btn:hover) {
  background: #f3f4f6;
  border-color: #8c959f;
  color: #24292e;
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

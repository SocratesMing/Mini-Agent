<template>
  <div class="chat-input-container">
    <div v-if="uploadedFiles.length > 0" class="uploaded-files">
      <div 
        v-for="(file, index) in uploadedFiles" 
        :key="index" 
        class="uploaded-file"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="file-icon">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <span class="file-name">{{ file.filename }}</span>
        <button @click="removeFile(index)" class="remove-file-btn">×</button>
      </div>
    </div>
    <div class="chat-input-wrapper">
      <label v-if="!isStreaming" class="upload-btn" :disabled="disabled">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>
        <input 
          type="file" 
          @change="handleFileSelect" 
          multiple 
          :disabled="disabled"
          hidden
        />
      </label>
      <textarea
        ref="textareaRef"
        v-model="message"
        @keydown.enter.exact.prevent="send"
        @input="autoResize"
        placeholder="输入消息，按 Enter 发送，Shift+Enter 换行..."
        :disabled="disabled"
        rows="1"
      ></textarea>
      <button 
        v-if="!isStreaming"
        @click="send" 
        class="send-btn"
        :disabled="(!message.trim() && uploadedFiles.length === 0) || disabled"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="22" y1="2" x2="11" y2="13"></line>
          <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>
      </button>
      <button 
        v-else
        @click="stop" 
        class="stop-btn"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2"></rect>
        </svg>
      </button>
    </div>
    <div class="input-hint">AI 助手可以帮你完成各种任务</div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  },
  sessionId: {
    type: String,
    default: null
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['send', 'stop'])

const message = ref('')
const textareaRef = ref(null)
const uploadedFiles = ref([])
let abortController = null

async function handleFileSelect(event) {
  const files = Array.from(event.target.files)
  
  for (const file of files) {
    uploadedFiles.value.push({
      file: file,
      filename: file.name,
      size: file.size
    })
  }
  
  event.target.value = ''
}

function removeFile(index) {
  uploadedFiles.value.splice(index, 1)
}

async function send() {
  const hasContent = message.value.trim()
  const hasFiles = uploadedFiles.value.length > 0
  
  if ((hasContent || hasFiles) && !props.disabled) {
    abortController = new AbortController()
    
    const filesToSend = uploadedFiles.value.map(f => ({
      filename: f.filename,
      size: f.size,
      file: f.file
    }))
    
    emit('send', message.value.trim(), filesToSend, abortController.signal)
    
    message.value = ''
    uploadedFiles.value = []
    nextTick(() => autoResize())
  }
}

function stop() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  emit('stop')
}

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 200) + 'px'
  }
}

watch(() => props.disabled, (val) => {
  if (!val && textareaRef.value) {
    textareaRef.value.focus()
  }
})

onUnmounted(() => {
  if (abortController) {
    abortController.abort()
  }
})
</script>

<style scoped>
.chat-input-container {
  padding: 16px 24px;
  background: #ffffff;
  border-top: 1px solid #e2e8f0;
}

.uploaded-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.uploaded-file {
  display: flex;
  align-items: center;
  gap: 6px;
  background: #f1f5f9;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  color: #475569;
}

.file-icon {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.file-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.remove-file-btn {
  width: 18px;
  height: 18px;
  border: none;
  background: #e2e8f0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 14px;
  color: #64748b;
  transition: all 0.2s;
}

.remove-file-btn:hover {
  background: #cbd5e1;
  color: #ef4444;
}

.chat-input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 8px 12px;
  transition: all 0.2s;
}

.chat-input-wrapper:focus-within {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
}

.upload-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #f1f5f9;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.upload-btn:hover:not([disabled]) {
  background: #e2e8f0;
}

.upload-btn[disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-btn svg {
  width: 20px;
  height: 20px;
  color: #64748b;
}

.chat-input-wrapper textarea {
  flex: 1;
  border: none;
  background: transparent;
  resize: none;
  font-size: 14px;
  line-height: 1.5;
  color: #1e293b;
  max-height: 200px;
  min-height: 24px;
  padding: 6px 0;
  outline: none;
}

.chat-input-wrapper textarea::placeholder {
  color: #94a3b8;
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #0ea5e9;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  background: #0284c7;
  transform: scale(1.05);
}

.send-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.send-btn svg {
  width: 18px;
  height: 18px;
  color: white;
}

.stop-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #ef4444;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.stop-btn:hover {
  background: #dc2626;
  transform: scale(1.05);
}

.stop-btn svg {
  width: 18px;
  height: 18px;
  color: white;
}

.input-hint {
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 8px;
}
</style>

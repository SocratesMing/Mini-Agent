<template>
  <div class="chat-input-container">
    <div class="input-box">
      <div v-if="uploadedFiles.length > 0" class="uploaded-files">
        <div 
          v-for="(file, index) in uploadedFiles" 
          :key="index" 
          class="uploaded-file"
        >
          <div class="file-icon-wrapper">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.filename }}</span>
            <span class="file-size">{{ formatSize(file.size) }}</span>
          </div>
          <button @click="removeFile(index)" class="remove-file-btn">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
      </div>
      
      <div class="input-row">
        <div class="input-field">
          <textarea
            ref="textareaRef"
            v-model="message"
            @keydown.enter.exact.prevent="send"
            @input="autoResize"
            placeholder="请输入你的需求，按「Enter」发送"
            :disabled="disabled"
            rows="1"
          ></textarea>
        </div>
      </div>
      
      <div class="input-actions">
        <div class="left-actions">
          <label class="action-btn upload-btn" :class="{ disabled: isStreaming || disabled }">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
            </svg>
            <input 
              type="file" 
              @change="handleFileSelect" 
              multiple 
              :disabled="isStreaming || disabled"
              hidden
            />
          </label>
          
          <span class="divider">|</span>
          
          <button 
            class="deep-think-btn" 
            :class="{ active: enableDeepThink, disabled: isStreaming || disabled }"
            :disabled="isStreaming || disabled"
            @click="enableDeepThink = !enableDeepThink"
            title="深度思考"
          >
            <svg class="deep-think-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"></path>
              <path fill-rule="evenodd" d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" clip-rule="evenodd"></path>
            </svg>
            <span class="deep-think-label">深度思考</span>
          </button>
        </div>
        
        <div class="right-actions">
          <button 
            v-if="!isStreaming"
            @click="send" 
            class="action-btn send-btn"
            :class="{ active: canSend }"
            :disabled="!canSend || disabled"
            title="发送"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="5" y1="12" x2="19" y2="12"></line>
              <polyline points="12 5 19 12 12 19"></polyline>
            </svg>
          </button>
          <button 
            v-else
            @click="stop" 
            class="action-btn stop-btn"
            title="停止"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2"></rect>
            </svg>
          </button>
        </div>
      </div>
    </div>
    
    <div class="input-footer">
      <span class="footer-text">CQ-Agent 可能会犯错，请核查重要信息</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

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
const enableDeepThink = ref(true)
let abortController = null

const canSend = computed(() => {
  return message.value.trim() || uploadedFiles.value.length > 0
})

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

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
  if (!canSend.value || props.disabled) return
  
  abortController = new AbortController()
  
  const filesToSend = uploadedFiles.value.map(f => ({
    filename: f.filename,
    size: f.size,
    file: f.file
  }))
  
  emit('send', message.value.trim(), filesToSend, abortController.signal, enableDeepThink.value)
  
  message.value = ''
  uploadedFiles.value = []
  nextTick(() => autoResize())
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
    textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 150) + 'px'
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
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 24px 24px;
  background: linear-gradient(to top, #ffffff 0%, #f8fafc 100%);
}

.input-box {
  width: 80%;
  max-width: 900px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  transition: all 0.3s ease;
  overflow: hidden;
}

.input-box:focus-within {
  border-color: #0ea5e9;
  box-shadow: 0 2px 12px rgba(14, 165, 233, 0.15);
}

.uploaded-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #f1f5f9;
}

.uploaded-file {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  padding: 8px 12px;
  border-radius: 12px;
  max-width: 200px;
}

.file-icon-wrapper {
  width: 32px;
  height: 32px;
  background: #f1f5f9;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.file-icon-wrapper svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 13px;
  font-weight: 500;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 11px;
  color: #64748b;
}

.remove-file-btn {
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.remove-file-btn:hover {
  background: rgba(14, 165, 233, 0.1);
}

.remove-file-btn svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.remove-file-btn:hover svg {
  color: #ef4444;
}

.input-row {
  padding: 12px 16px;
  background: transparent;
}

.input-field {
  width: 100%;
}

.input-field textarea {
  width: 100%;
  border: none;
  background: transparent;
  resize: none;
  font-size: 15px;
  line-height: 1.6;
  color: #1e293b;
  max-height: 150px;
  min-height: 24px;
  padding: 0;
  outline: none;
}

.input-field textarea::placeholder {
  color: #94a3b8;
  font-size: 14px;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 12px;
  border-top: none;
  background: #fefefe;
}

.left-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.divider {
  color: #e2e8f0;
  font-size: 14px;
  user-select: none;
}

.deep-think-btn {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 12px;
  height: auto;
  min-height: 32px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.deep-think-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.deep-think-btn svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.deep-think-btn:hover:not(.disabled) svg {
  color: #0ea5e9;
}

.deep-think-btn.active svg {
  color: white;
}

.deep-think-label {
  font-size: 12px;
  color: #64748b;
}

.deep-think-btn:hover:not(.disabled) {
  background: rgba(14, 165, 233, 0.1);
  border-color: transparent;
}

.deep-think-btn:hover:not(.disabled) svg,
.deep-think-btn:hover:not(.disabled) .deep-think-label {
  color: #0ea5e9;
}

.deep-think-btn.active {
  background: #0ea5e9;
  border-color: #0ea5e9;
  border-radius: 6px;
}

.deep-think-btn.active svg,
.deep-think-btn.active .deep-think-label {
  color: white;
}

.deep-think-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.right-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.action-btn svg {
  width: 18px;
  height: 18px;
  color: #64748b;
}

.action-btn:hover {
  background: #f1f5f9;
}

.action-btn:hover svg {
  color: #0ea5e9;
}

.send-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #f1f5f9;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.send-btn svg {
  width: 18px;
  height: 18px;
  color: #64748b;
  transition: all 0.2s;
}

.send-btn.active {
  background: #0ea5e9;
}

.send-btn.active svg {
  color: white;
}

.send-btn.active:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.3);
}

.send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.stop-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: #ef4444;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.stop-btn svg {
  width: 18px;
  height: 18px;
  color: white;
}

.stop-btn:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.upload-btn svg {
  width: 18px;
  height: 18px;
  color: #64748b;
  transition: all 0.2s;
}

.upload-btn:hover:not(.disabled) {
  background: #f1f5f9;
}

.upload-btn:hover:not(.disabled) svg {
  color: #0ea5e9;
}

.upload-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.copy-btn svg {
  width: 18px;
  height: 18px;
  color: #64748b;
  transition: all 0.2s;
}

.copy-btn:hover:not(.disabled) {
  background: #f1f5f9;
}

.copy-btn:hover:not(.disabled) svg {
  color: #0ea5e9;
}

.copy-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.input-footer {
  margin-top: 12px;
  text-align: center;
}

.footer-text {
  font-size: 12px;
  color: #94a3b8;
}
</style>

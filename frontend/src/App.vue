<template>
  <div class="app-container">
    <SessionList
      v-show="!isSidebarCollapsed"
      :sessions="sessions"
      :currentSessionId="currentSessionId"
      @createSession="handleCreateSession"
      @selectSession="handleSelectSession"
      @deleteSession="handleDeleteSession"
      @renameSession="handleRenameSession"
      @toggleSidebar="toggleSidebar"
      @showAssets="handleShowAssets"
    />
    
    <button 
      v-if="isSidebarCollapsed"
      class="expand-sidebar-btn"
      @click="toggleSidebar"
      title="展开侧边栏"
    >
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
        <line x1="9" y1="3" x2="9" y2="21"></line>
      </svg>
    </button>
    
    <AssetsPanel v-if="showAssets" @close="showAssets = false" />
    
    <Chat
      v-else
      :messages="messages"
      :currentSessionId="currentSessionId"
      :isStreaming="isStreaming"
      @sendMessage="handleSendMessage"
      @stop="handleStop"
    />
    
    <div v-if="error" class="error-toast">
      {{ error }}
      <button @click="error = null">×</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import SessionList from './components/SessionList.vue'
import Chat from './components/Chat.vue'
import AssetsPanel from './components/AssetsPanel.vue'
import { createSession, listSessions, getChatHistory, deleteSession, sendMessage, renameSession } from './api/chat.js'
import { uploadFile } from './api/files.js'

const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const isStreaming = ref(false)
const error = ref(null)
const isSidebarCollapsed = ref(false)
const showAssets = ref(false)

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
}

function handleShowAssets() {
  showAssets.value = !showAssets.value
}

async function loadSessions() {
  try {
    const data = await listSessions()
    sessions.value = Array.isArray(data) ? data : (data.sessions || [])
  } catch (e) {
    console.error('加载会话列表失败:', e)
    error.value = '加载会话列表失败'
  }
}

async function ensureCurrentSession(initialTitle = '') {
  if (!currentSessionId.value) {
    const newSession = await createSession('')
    currentSessionId.value = newSession.session_id
    sessions.value.unshift({
      session_id: newSession.session_id,
      title: initialTitle || '新会话',
      created_at: new Date().toISOString()
    })
  }
  return currentSessionId.value
}

async function handleCreateSession() {
  showAssets.value = false
  try {
    await ensureCurrentSession()
    messages.value = []
  } catch (e) {
    console.error('创建会话失败:', e)
    error.value = '创建会话失败'
  }
}

async function handleSelectSession(sessionId) {
  showAssets.value = false
  currentSessionId.value = sessionId
  isStreaming.value = true
  
  try {
    const history = await getChatHistory(sessionId)
    messages.value = history.messages || []
  } catch (e) {
    console.error('加载聊天历史失败:', e)
    error.value = '加载聊天历史失败'
  } finally {
    isStreaming.value = false
  }
}

async function handleDeleteSession(sessionId) {
  try {
    await deleteSession(sessionId)
    sessions.value = sessions.value.filter(s => s.session_id !== sessionId)
    
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = sessions.value[0]?.session_id || null
      messages.value = []
    }
  } catch (e) {
    console.error('删除会话失败:', e)
    error.value = '删除会话失败'
  }
}

async function handleRenameSession(sessionId, newTitle) {
  try {
    await renameSession(sessionId, newTitle)
    const idx = sessions.value.findIndex(s => s.session_id === sessionId)
    if (idx !== -1) {
      sessions.value[idx] = { ...sessions.value[idx], title: newTitle }
    }
  } catch (e) {
    console.error('重命名会话失败:', e)
    error.value = '重命名会话失败'
  }
}

async function handleSendMessage(message, files = [], signal) {
  try {
    const title = message.substring(0, 5) || '新会话'
    await ensureCurrentSession(title)
  } catch (e) {
    console.error('创建会话失败:', e)
    error.value = '创建会话失败'
    return
  }

  const userMsgId = `user-${Date.now()}`

  let contentWithFiles = message
  if (files && files.length > 0) {
    for (const f of files) {
      try {
        await uploadFile(currentSessionId.value, f.file)
        contentWithFiles += `\n[文件已上传: ${f.filename}]`
      } catch (e) {
        console.error('文件上传失败:', e)
        contentWithFiles += `\n[文件上传失败: ${f.filename}]`
      }
    }
  }

  const userMessage = {
    id: userMsgId,
    role: 'user',
    content: contentWithFiles,
    created_at: new Date().toISOString()
  }

  messages.value.push(userMessage)

  const assistantMsgId = `assistant-${Date.now()}`
  const assistantMessage = {
    id: assistantMsgId,
    role: 'assistant',
    content: '',
    created_at: null,
    thinking: ''
  }

  messages.value.push(assistantMessage)

  let currentContent = ''
  let currentThinking = ''

  isStreaming.value = true

  try {
    await sendMessage(currentSessionId.value, message, (data) => {
      const eventType = data.type || ''

      if (eventType === 'thinking') {
        currentThinking += data.content || ''
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = { ...messages.value[idx], thinking: currentThinking }
        }
      } else if (eventType === 'content') {
        currentContent += data.content || ''
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = { ...messages.value[idx], content: currentContent }
        }
      } else if (eventType === 'done') {
        const finalContent = data.content || currentContent
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = {
            ...messages.value[idx],
            content: finalContent,
            created_at: new Date().toISOString()
          }
        }
      }
    }, signal)
  } catch (e) {
    if (e.name === 'AbortError') {
      return
    }
    console.error('发送消息失败:', e)
    messages.value = messages.value.filter(m => m.id !== assistantMsgId)
    error.value = e.message || '发送消息失败'
  } finally {
    isStreaming.value = false
    await loadSessions()
  }
}

function handleStop() {
  isStreaming.value = false
  error.value = '已停止生成'
  setTimeout(() => {
    error.value = null
  }, 2000)
}

onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  width: 100vw;
  background: #f8fafc;
  position: relative;
}

.expand-sidebar-btn {
  position: absolute;
  left: 16px;
  top: 16px;
  width: 40px;
  height: 40px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 100;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.expand-sidebar-btn:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.expand-sidebar-btn svg {
  width: 20px;
  height: 20px;
  color: #64748b;
}

.error-toast {
  position: fixed;
  bottom: 100px;
  left: 50%;
  transform: translateX(-50%);
  background: #fee2e2;
  color: #dc2626;
  padding: 12px 20px;
  border-radius: 10px;
  font-size: 14px;
  display: flex;
  align-items: center;
  gap: 12px;
  animation: slideUp 0.3s ease-out;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.2);
}

.error-toast button {
  background: transparent;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: #dc2626;
  padding: 0;
  line-height: 1;
}

@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
}
</style>

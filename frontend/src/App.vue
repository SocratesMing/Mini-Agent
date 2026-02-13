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
    const newSession = await createSession(initialTitle || '新会话')
    currentSessionId.value = newSession.session_id
    const existingIndex = sessions.value.findIndex(s => s.session_id === newSession.session_id)
    if (existingIndex === -1) {
      sessions.value.unshift({
        session_id: newSession.session_id,
        title: newSession.title || initialTitle || '新会话',
        created_at: newSession.created_at || new Date().toISOString()
      })
    }
  }
  return currentSessionId.value
}

async function handleCreateSession() {
  showAssets.value = false
  currentSessionId.value = null
  messages.value = []
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

async function handleSendMessage(message, files = [], signal, enableDeepThink = false) {
  if (!currentSessionId.value) {
    currentSessionId.value = null
  }

  const userMsgId = `user-${Date.now()}`

  let contentWithFiles = message
  if (files && files.length > 0) {
    for (const f of files) {
      try {
        if (currentSessionId.value) {
          await uploadFile(currentSessionId.value, f.file)
        }
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
    thinking: '',
    tool_calls: [],
    blocks: []
  }

  messages.value.push(assistantMessage)

  let currentThinking = ''
  let currentContent = ''
  let currentToolCalls = []
  let currentBlock = null

  function addBlock(type, data) {
    if (!currentBlock || currentBlock.type !== type) {
      currentBlock = { type, content: '', ...data }
      const idx = messages.value.findIndex(m => m.id === assistantMsgId)
      if (idx !== -1) {
        messages.value[idx].blocks.push(currentBlock)
      }
    } else {
      currentBlock.content = (currentBlock.content || '') + (data.content || '')
      if (data.tool_name) currentBlock.tool_name = data.tool_name
      if (data.arguments) currentBlock.arguments = data.arguments
      if (data.result !== undefined) currentBlock.result = data.result
      if (data.success !== undefined) currentBlock.success = data.success
    }
    const idx = messages.value.findIndex(m => m.id === assistantMsgId)
    if (idx !== -1) {
      messages.value[idx] = { ...messages.value[idx] }
    }
  }

  isStreaming.value = true

  try {
    await sendMessage(currentSessionId.value, message, (data) => {
      const eventType = data.type || ''

      if (eventType === 'error') {
        error.value = data.content || '发送消息失败'
      } else if (eventType === 'start') {
        if (data.session_id) {
          currentSessionId.value = data.session_id
          const existingIdx = sessions.value.findIndex(s => s.session_id === data.session_id)
          if (existingIdx === -1) {
            sessions.value.unshift({
              session_id: data.session_id,
              title: message.substring(0, 5) + '...' || '新会话',
              created_at: new Date().toISOString()
            })
          }
        }
      } else if (eventType === 'thinking') {
        currentThinking += data.content || ''
        addBlock('thinking', { content: data.content || '' })
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = { ...messages.value[idx], thinking: currentThinking }
        }
      } else if (eventType === 'content') {
        currentContent += data.content || ''
        addBlock('content', { content: data.content || '' })
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = { ...messages.value[idx], content: currentContent }
        }
      } else if (eventType === 'tool_call') {
        const toolCall = {
          tool_name: data.tool_name || '',
          arguments: data.arguments || {},
          result: '',
          success: true
        }
        currentToolCalls.push(toolCall)
        addBlock('tool_call', { 
          tool_name: data.tool_name || '', 
          arguments: data.arguments || {},
          content: ''
        })
        const idx = messages.value.findIndex(m => m.id === assistantMsgId)
        if (idx !== -1) {
          messages.value[idx] = { ...messages.value[idx], tool_calls: [...currentToolCalls] }
        }
      } else if (eventType === 'tool_result') {
        if (currentToolCalls.length > 0) {
          const lastTool = currentToolCalls[currentToolCalls.length - 1]
          lastTool.result = data.result || ''
          lastTool.success = data.success !== false
          addBlock('tool_result', { 
            tool_name: data.tool_name || '',
            result: data.result || '',
            success: data.success !== false,
            content: data.result || ''
          })
          const idx = messages.value.findIndex(m => m.id === assistantMsgId)
          if (idx !== -1) {
            messages.value[idx] = { ...messages.value[idx], tool_calls: [...currentToolCalls] }
          }
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
        if (data.session_id) {
          currentSessionId.value = data.session_id
          const existingIdx = sessions.value.findIndex(s => s.session_id === data.session_id)
          if (existingIdx === -1) {
            sessions.value.unshift({
              session_id: data.session_id,
              title: message.substring(0, 5) + '...' || '新会话',
              created_at: new Date().toISOString()
            })
          }
        }
      }
    }, signal, enableDeepThink)
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

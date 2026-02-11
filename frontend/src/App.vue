<template>
  <div class="app-container">
    <SessionList
      :sessions="sessions"
      :currentSessionId="currentSessionId"
      @createSession="handleCreateSession"
      @selectSession="handleSelectSession"
      @deleteSession="handleDeleteSession"
    />
    
    <Chat
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
import { createSession, listSessions, getChatHistory, deleteSession, sendMessage } from './api/chat.js'
import { uploadFile } from './api/files.js'

const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const isStreaming = ref(false)
const error = ref(null)

async function loadSessions() {
  try {
    const data = await listSessions()
    sessions.value = Array.isArray(data) ? data : (data.sessions || [])
  } catch (e) {
    console.error('加载会话列表失败:', e)
    error.value = '加载会话列表失败'
  }
}

async function handleCreateSession() {
  try {
    const newSession = await createSession('')
    currentSessionId.value = newSession.session_id
    messages.value = []
  } catch (e) {
    console.error('创建会话失败:', e)
    error.value = '创建会话失败'
  }
}

async function handleSelectSession(sessionId) {
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

async function handleSendMessage(message, files = [], signal) {
  if (!currentSessionId.value) return

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
  color: #dc2626;
  font-size: 20px;
  cursor: pointer;
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

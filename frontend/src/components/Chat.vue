<template>
  <div class="chat-container">
    <div class="chat-messages" ref="messagesRef">
      <div v-if="messages.length === 0" class="welcome-screen">
        <div class="welcome-icon">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M3 3v18h18"></path>
            <path d="M7 16l4-4 4 4 5-6"></path>
            <circle cx="20" cy="10" r="2"></circle>
          </svg>
        </div>
        <h2>我是 CQ-Agent</h2>
        <p>请输入策略需求或因子需求</p>
      </div>
      
      <ChatMessage
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
      />
    </div>
    
    <ChatInput
      @send="handleSend"
      :disabled="isStreaming"
      :isStreaming="isStreaming"
      @stop="handleStop"
    />
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import ChatMessage from './ChatMessage.vue'
import ChatInput from './ChatInput.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  },
  currentSessionId: {
    type: String,
    default: null
  },
  isStreaming: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['sendMessage', 'stop'])
const messagesRef = ref(null)

function handleSend(message, files, signal) {
  emit('sendMessage', message, files, signal)
}

function handleStop() {
  emit('stop')
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

watch(() => props.messages.length, scrollToBottom)

watch(() => props.messages, () => {
  if (props.isStreaming) {
    scrollToBottom()
  }
}, { deep: true })
</script>

<style scoped>
.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scroll-behavior: smooth;
  display: flex;
  flex-direction: column;
}

.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #64748b;
}

.welcome-icon {
  width: 88px;
  height: 88px;
  background: linear-gradient(135deg, #1e3a5f 0%, #0d7377 50%, #14a085 100%);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  box-shadow: 0 8px 32px rgba(13, 115, 119, 0.3);
}

.welcome-icon svg {
  width: 44px;
  height: 44px;
  color: white;
}

.welcome-screen h2 {
  font-size: 24px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 8px 0;
}

.welcome-screen p {
  font-size: 14px;
  color: #94a3b8;
  margin: 0;
}
</style>

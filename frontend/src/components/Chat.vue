<template>
  <div class="chat-container">
    <div class="chat-messages" ref="messagesRef">
      <div v-if="messages.length === 0" class="welcome-screen">
        <div class="welcome-icon">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        </div>
        <h2>开始对话</h2>
        <p>输入消息开始与 AI 助手交流</p>
      </div>
      
      <ChatMessage
        v-for="msg in messages"
        :key="msg.id"
        :message="msg"
      />
      
      <div v-if="isStreaming" class="streaming-indicator">
        <div class="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <span class="streaming-text">AI 正在思考...</span>
      </div>
    </div>
    
    <ChatInput
      @send="handleSend"
      :disabled="isStreaming || !currentSessionId"
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

function handleSend(message, files) {
  emit('sendMessage', message, files)
}

function handleStop() {
  emit('stop')
}

watch(() => props.messages.length, () => {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
})
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
  width: 80px;
  height: 80px;
  background: linear-gradient(135deg, #0ea5e9 0%, #8b5cf6 100%);
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}

.welcome-icon svg {
  width: 40px;
  height: 40px;
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

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: rgba(14, 165, 233, 0.1);
  border-radius: 12px;
  margin-top: 16px;
  width: fit-content;
}

.typing-indicator {
  display: flex;
  gap: 4px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #0ea5e9;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) {
  animation-delay: -0.32s;
}

.typing-indicator span:nth-child(2) {
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

.streaming-text {
  font-size: 14px;
  color: #0ea5e9;
  font-weight: 500;
}
</style>

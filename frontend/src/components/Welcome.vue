<template>
  <div class="welcome-overlay">
    <div class="welcome-modal">
      <div class="welcome-header">
        <div class="logo">
          <CqLogo :size="36" />
        </div>
        <h1>欢迎使用 CQ-Agent</h1>
        <p>请完善您的个人信息以开始使用</p>
      </div>

      <form @submit.prevent="handleSubmit" class="welcome-form">
        <div class="form-group">
          <label for="username">
            用户名 <span class="required">*</span>
          </label>
          <input
            id="username"
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            required
            ref="usernameInput"
          />
        </div>

        <div class="form-group">
          <label for="organization">机构ID</label>
          <input
            id="organization"
            v-model="form.organization_id"
            type="text"
            placeholder="请输入机构ID（选填）"
          />
        </div>

        <div class="form-group">
          <label for="email">用户邮箱</label>
          <input
            id="email"
            v-model="form.email"
            type="email"
            placeholder="请输入用户邮箱（选填）"
          />
        </div>

        <div v-if="error" class="error-message">
          {{ error }}
        </div>

        <button type="submit" class="submit-btn" :disabled="submitting || !form.username.trim()">
          {{ submitting ? '登录中...' : '开始使用' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { updateUserProfile } from '../api/files.js'
import CqLogo from './CqLogo.vue'

const emit = defineEmits(['completed'])

const usernameInput = ref(null)
const submitting = ref(false)
const error = ref('')

const form = ref({
  username: '',
  organization_id: '',
  email: ''
})

async function handleSubmit() {
  if (!form.value.username.trim()) {
    error.value = '请输入用户名'
    return
  }

  submitting.value = true
  error.value = ''

  try {
    await updateUserProfile({
      username: form.value.username.trim(),
      organization_id: form.value.organization_id.trim(),
      email: form.value.email.trim()
    })
    emit('completed', {
      username: form.value.username.trim(),
      organization_id: form.value.organization_id.trim(),
      email: form.value.email.trim()
    })
  } catch (e) {
    error.value = e.message || '登录失败，请重试'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  nextTick(() => {
    usernameInput.value?.focus()
  })
})
</script>

<style scoped>
.welcome-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.welcome-modal {
  background: white;
  border-radius: 20px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.welcome-header {
  text-align: center;
  padding: 40px 32px 24px;
}

.logo {
  margin: 0 auto 20px;
}

.welcome-header h1 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: #1e293b;
}

.welcome-header p {
  margin: 0;
  font-size: 14px;
  color: #64748b;
}

.welcome-form {
  padding: 0 32px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group label {
  font-size: 14px;
  font-weight: 500;
  color: #475569;
}

.required {
  color: #ef4444;
}

.form-group input {
  padding: 14px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  font-size: 15px;
  color: #1e293b;
  transition: all 0.2s;
  outline: none;
}

.form-group input:focus {
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
}

.form-group input::placeholder {
  color: #94a3b8;
}

.error-message {
  padding: 12px 16px;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 10px;
  font-size: 14px;
}

.submit-btn {
  padding: 14px 24px;
  border: none;
  background: linear-gradient(135deg, #0ea5e9 0%, #8b5cf6 100%);
  color: white;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  margin-top: 8px;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}

.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}
</style>

<template>
  <div class="tasks-panel">
    <div class="tasks-header">
      <div class="header-left">
        <button @click="$emit('close')" class="back-btn">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
        </button>
        <h2>定时任务</h2>
      </div>
      <button @click="showCreateDialog = true" class="create-btn">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="12" y1="5" x2="12" y2="19"></line>
          <line x1="5" y1="12" x2="19" y2="12"></line>
        </svg>
        新建任务
      </button>
    </div>

    <div class="tasks-content">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>

      <div v-else-if="tasks.length === 0" class="empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"></circle>
          <polyline points="12 6 12 12 16 14"></polyline>
        </svg>
        <h3>暂无定时任务</h3>
        <p>点击"新建任务"创建定时任务</p>
      </div>

      <div v-else class="tasks-list">
        <div
          v-for="item in tasks"
          :key="item.task.task_id"
          class="task-card"
          :class="{ disabled: !item.task.enabled }"
        >
          <div class="task-header">
            <div class="task-info">
              <h3 class="task-name">{{ item.task.name }}</h3>
              <p class="task-description">{{ item.task.description || '暂无描述' }}</p>
              <div class="task-meta">
                <span class="task-cron">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                  {{ item.task.cron_expression }}
                </span>
                <span class="task-status" :class="{ enabled: item.task.enabled }">
                  {{ item.task.enabled ? '已启用' : '已禁用' }}
                </span>
              </div>
            </div>
            <div class="task-actions">
              <button @click="toggleTask(item)" class="action-btn" :title="item.task.enabled ? '禁用' : '启用'">
                <svg v-if="item.task.enabled" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
              </button>
              <button @click="editTask(item.task)" class="action-btn" title="编辑">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                </svg>
              </button>
              <button @click="confirmDelete(item.task)" class="action-btn delete" title="删除">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="3 6 5 6 21 6"></polyline>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
              </button>
            </div>
          </div>
          
          <div class="executions-section" v-if="item.recent_executions && item.recent_executions.length > 0">
            <div class="executions-header">
              <span>执行记录</span>
              <span class="execution-count">{{ item.recent_executions.length }} 条</span>
            </div>
            <div class="executions-list">
              <div
                v-for="execution in item.recent_executions"
                :key="execution.execution_id"
                class="execution-item"
                :class="execution.status"
              >
                <div class="execution-time">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                  {{ formatTime(execution.started_at) }}
                </div>
                <div class="execution-status" :class="execution.status">
                  <span class="status-dot"></span>
                  {{ getStatusText(execution.status) }}
                </div>
                <div class="execution-result" v-if="execution.result">
                  {{ execution.result }}
                </div>
                <div class="execution-error" v-if="execution.error_message">
                  {{ execution.error_message }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog">
        <div class="dialog-header">
          <h3>{{ editingTask ? '编辑任务' : '新建任务' }}</h3>
          <button @click="closeDialog" class="close-btn">×</button>
        </div>
        <div class="dialog-body">
          <div class="form-group">
            <label>任务名称</label>
            <input v-model="taskForm.name" type="text" placeholder="输入任务名称" />
          </div>
          <div class="form-group">
            <label>任务描述</label>
            <textarea v-model="taskForm.description" placeholder="输入任务描述" rows="3"></textarea>
          </div>
          <div class="form-group">
            <label>Cron 表达式</label>
            <input v-model="taskForm.cronExpression" type="text" placeholder="例如: 0 0 * * *" />
            <p class="form-hint">格式: 分 时 日 月 周 (例如: 0 0 * * * 表示每天零点)</p>
          </div>
        </div>
        <div class="dialog-footer">
          <button @click="closeDialog" class="btn-cancel">取消</button>
          <button @click="saveTask" class="btn-confirm">{{ editingTask ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDeleteConfirm" class="dialog-overlay" @click.self="showDeleteConfirm = false">
      <div class="dialog dialog-small">
        <div class="dialog-header">
          <h3>确认删除</h3>
        </div>
        <div class="dialog-body">
          <p>确定要删除任务 "{{ taskToDelete?.name }}" 吗？此操作不可恢复。</p>
        </div>
        <div class="dialog-footer">
          <button @click="showDeleteConfirm = false" class="btn-cancel">取消</button>
          <button @click="deleteTask" class="btn-danger">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { listScheduledTasks, createScheduledTask, updateScheduledTask, deleteScheduledTask } from '../api/tasks.js'

const props = defineProps({
  visible: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['close'])

const loading = ref(false)
const tasks = ref([])
const showCreateDialog = ref(false)
const showDeleteConfirm = ref(false)
const editingTask = ref(null)
const taskToDelete = ref(null)

const taskForm = ref({
  name: '',
  description: '',
  cronExpression: '0 0 * * *'
})

async function refreshTasks() {
  loading.value = true
  try {
    tasks.value = await listScheduledTasks()
  } catch (e) {
    console.error('获取定时任务失败:', e)
  } finally {
    loading.value = false
  }
}

function formatTime(timeStr) {
  if (!timeStr) return '-'
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function getStatusText(status) {
  const statusMap = {
    'running': '执行中',
    'success': '成功',
    'failed': '失败',
    'pending': '等待中'
  }
  return statusMap[status] || status
}

function editTask(task) {
  editingTask.value = task
  taskForm.value = {
    name: task.name,
    description: task.description,
    cronExpression: task.cron_expression
  }
  showCreateDialog.value = true
}

function confirmDelete(task) {
  taskToDelete.value = task
  showDeleteConfirm.value = true
}

async function toggleTask(item) {
  try {
    await updateScheduledTask(
      item.task.task_id,
      item.task.name,
      item.task.description,
      item.task.cron_expression,
      !item.task.enabled
    )
    await refreshTasks()
  } catch (e) {
    console.error('更新任务失败:', e)
  }
}

async function saveTask() {
  try {
    if (editingTask.value) {
      await updateScheduledTask(
        editingTask.value.task_id,
        taskForm.value.name,
        taskForm.value.description,
        taskForm.value.cronExpression,
        editingTask.value.enabled
      )
    } else {
      await createScheduledTask(
        taskForm.value.name,
        taskForm.value.description,
        taskForm.value.cronExpression
      )
    }
    closeDialog()
    await refreshTasks()
  } catch (e) {
    console.error('保存任务失败:', e)
  }
}

async function deleteTask() {
  try {
    await deleteScheduledTask(taskToDelete.value.task_id)
    showDeleteConfirm.value = false
    await refreshTasks()
  } catch (e) {
    console.error('删除任务失败:', e)
  }
}

function closeDialog() {
  showCreateDialog.value = false
  editingTask.value = null
  taskForm.value = {
    name: '',
    description: '',
    cronExpression: '0 0 * * *'
  }
}

onMounted(() => {
  refreshTasks()
})

watch(() => props.visible, (newVal) => {
  if (newVal) {
    refreshTasks()
  }
})
</script>

<style scoped>
.tasks-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  height: 100%;
}

.tasks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
}

.back-btn:hover {
  background: #f1f5f9;
}

.back-btn svg {
  width: 20px;
  height: 20px;
}

.tasks-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

.create-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.create-btn:hover {
  background: #2563eb;
}

.create-btn svg {
  width: 16px;
  height: 16px;
}

.tasks-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #64748b;
}

.empty-state svg {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0 0 8px;
  font-size: 16px;
  color: #334155;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.tasks-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.task-card {
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.task-card.disabled {
  opacity: 0.6;
}

.task-header {
  display: flex;
  justify-content: space-between;
  padding: 16px;
}

.task-info {
  flex: 1;
}

.task-name {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.task-description {
  margin: 0 0 8px;
  font-size: 14px;
  color: #64748b;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.task-cron {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}

.task-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f1f5f9;
  color: #64748b;
}

.task-status.enabled {
  background: #dcfce7;
  color: #166534;
}

.task-actions {
  display: flex;
  gap: 8px;
}

.task-actions .action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
}

.task-actions .action-btn:hover {
  background: #f1f5f9;
}

.task-actions .action-btn svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}

.task-actions .action-btn.delete:hover {
  background: #fee2e2;
}

.task-actions .action-btn.delete:hover svg {
  color: #dc2626;
}

.executions-section {
  border-top: 1px solid #e2e8f0;
  padding: 12px 16px;
  background: #f8fafc;
}

.executions-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: #64748b;
}

.execution-count {
  font-size: 11px;
}

.executions-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.execution-item {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 8px;
  background: white;
  border-radius: 6px;
  font-size: 12px;
}

.execution-time {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #64748b;
}

.execution-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.execution-status.success .status-dot {
  background: #22c55e;
}

.execution-status.failed .status-dot {
  background: #ef4444;
}

.execution-status.running .status-dot {
  background: #f59e0b;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.execution-result {
  width: 100%;
  color: #64748b;
  white-space: pre-wrap;
  word-break: break-all;
}

.execution-error {
  width: 100%;
  color: #ef4444;
  white-space: pre-wrap;
}

.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.dialog {
  background: white;
  border-radius: 12px;
  width: 90%;
  max-width: 480px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
}

.dialog-small {
  max-width: 360px;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.close-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  font-size: 20px;
  color: #64748b;
  cursor: pointer;
  border-radius: 6px;
}

.close-btn:hover {
  background: #f1f5f9;
}

.dialog-body {
  padding: 20px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group:last-child {
  margin-bottom: 0;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 14px;
  box-sizing: border-box;
}

.form-group input:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #64748b;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid #e2e8f0;
}

.btn-cancel,
.btn-confirm,
.btn-danger {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-cancel {
  border: 1px solid #e2e8f0;
  background: white;
  color: #64748b;
}

.btn-cancel:hover {
  background: #f8fafc;
}

.btn-confirm {
  border: none;
  background: #3b82f6;
  color: white;
}

.btn-confirm:hover {
  background: #2563eb;
}

.btn-danger {
  border: none;
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>

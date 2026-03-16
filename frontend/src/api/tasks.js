const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function listScheduledTasks() {
  const response = await fetch(`${API_BASE_URL}/api/tasks`)
  if (!response.ok) {
    throw new Error('获取定时任务列表失败')
  }
  return response.json()
}

export async function createScheduledTask(name, description, cronExpression) {
  const params = new URLSearchParams({
    name,
    description,
    cron_expression: cronExpression
  })
  const response = await fetch(`${API_BASE_URL}/api/tasks?${params}`, {
    method: 'POST'
  })
  if (!response.ok) {
    throw new Error('创建定时任务失败')
  }
  return response.json()
}

export async function getScheduledTask(taskId) {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}`)
  if (!response.ok) {
    throw new Error('获取定时任务详情失败')
  }
  return response.json()
}

export async function updateScheduledTask(taskId, name, description, cronExpression, enabled) {
  const params = new URLSearchParams({
    name,
    description,
    cron_expression: cronExpression,
    enabled: enabled.toString()
  })
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}?${params}`, {
    method: 'PUT'
  })
  if (!response.ok) {
    throw new Error('更新定时任务失败')
  }
  return response.json()
}

export async function deleteScheduledTask(taskId) {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}`, {
    method: 'DELETE'
  })
  if (!response.ok) {
    throw new Error('删除定时任务失败')
  }
  return response.json()
}

export async function getTaskExecutions(taskId, limit = 50) {
  const response = await fetch(`${API_BASE_URL}/api/tasks/${taskId}/executions?limit=${limit}`)
  if (!response.ok) {
    throw new Error('获取执行记录失败')
  }
  return response.json()
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function uploadFile(sessionId, file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '文件上传失败')
  }

  return await response.json()
}

export async function getSessionFiles(sessionId) {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/files`)

  if (!response.ok) {
    throw new Error('获取文件列表失败')
  }

  return await response.json()
}

export async function getAllFiles() {
  const response = await fetch(`${API_BASE_URL}/api/files/all`)

  if (!response.ok) {
    throw new Error('获取所有文件失败')
  }

  return await response.json()
}

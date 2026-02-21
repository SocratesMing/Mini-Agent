const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function uploadFile(sessionId, file, onProgress) {
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('file', file)

    const xhr = new XMLHttpRequest()

    xhr.upload.addEventListener('progress', (progressEvent) => {
      if (onProgress && progressEvent.lengthComputable) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percentCompleted)
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText)
          resolve(response)
        } catch (error) {
          reject(new Error('Invalid response format'))
        }
      } else {
        try {
          const error = JSON.parse(xhr.responseText)
          reject(new Error(error.detail || '文件上传失败'))
        } catch {
          reject(new Error('文件上传失败'))
        }
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error('网络错误，文件上传失败'))
    })

    xhr.open('POST', `${API_BASE_URL}/api/sessions/${sessionId}/upload`)
    xhr.send(formData)
  })
}

export async function getSessionFiles(sessionId) {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/files`)

  if (!response.ok) {
    throw new Error('获取文件列表失败')
  }

  return await response.json()
}

export async function getAllFiles() {
  const response = await fetch(`${API_BASE_URL}/api/sessions/files/all`)

  if (!response.ok) {
    throw new Error('获取所有文件失败')
  }

  return await response.json()
}

export async function deleteFile(sessionId, file) {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/files/${file.id}`, {
    method: 'DELETE'
  })

  if (!response.ok) {
    throw new Error('删除文件失败')
  }

  return await response.json()
}

export async function getUserProfile() {
  const response = await fetch(`${API_BASE_URL}/api/user/profile`)

  if (!response.ok) {
    throw new Error('获取用户资料失败')
  }

  return await response.json()
}

export async function updateUserProfile(data) {
  const response = await fetch(`${API_BASE_URL}/api/user/profile`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || '更新用户资料失败')
  }

  return await response.json()
}

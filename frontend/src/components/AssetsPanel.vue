<template>
  <div class="assets-panel">
    <div class="assets-header">
      <h2>我的资产</h2>
      <button @click="refreshAssets" class="refresh-btn" :disabled="loading">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ spinning: loading }">
          <polyline points="23 4 23 10 17 10"></polyline>
          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
        </svg>
        刷新
      </button>
    </div>

    <div class="tabs">
      <button
        v-for="(count, category) in categoryCounts"
        :key="category"
        class="tab"
        :class="{ active: activeTab === category }"
        @click="activeTab = category"
      >
        <span class="tab-icon">{{ getCategoryIcon(category) }}</span>
        <span class="tab-name">{{ category }}</span>
        <span class="tab-count">{{ count }}</span>
      </button>
    </div>

    <div class="assets-content">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>

      <div v-else-if="totalFiles === 0" class="empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
        </svg>
        <h3>暂无文件</h3>
        <p>在会话中上传文件后，将在这里显示</p>
      </div>

      <div v-else class="files-grid">
        <div
          v-for="file in currentFiles"
          :key="file.file_path"
          class="file-card"
        >
          <div class="file-icon" :class="getCategoryClass(file.category)">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
          <div class="file-info">
            <div class="file-name" :title="file.filename">{{ file.filename }}</div>
            <div class="file-meta">
              <span class="file-size">{{ formatSize(file.size) }}</span>
              <span class="file-session" v-if="file.session_title">{{ file.session_title }}</span>
            </div>
          </div>
          <button class="file-action" @click="copyPath(file.file_path)" title="复制路径">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { getAllFiles } from '../api/files.js'

const loading = ref(false)
const allFiles = ref([])
const activeTab = ref('全部')
const emit = defineEmits(['close'])

const categories = ['全部', '文档', '图片', '代码', '数据', '其他']

const categoryIcons = {
  '全部': '📁',
  '文档': '📄',
  '图片': '🖼️',
  '代码': '💻',
  '数据': '📊',
  '其他': '📎'
}

function getCategoryIcon(category) {
  return categoryIcons[category] || '📎'
}

function getCategoryClass(category) {
  const classes = {
    '文档': 'doc',
    '图片': 'image',
    '代码': 'code',
    '数据': 'data',
    '其他': 'other'
  }
  return classes[category] || 'other'
}

function getFileCategory(filename) {
  const ext = filename.split('.').pop().toLowerCase()
  const categoryMap = {
    '文档': ['pdf', 'doc', 'docx', 'txt', 'md', 'xls', 'xlsx', 'ppt', 'pptx', 'rtf', 'odt'],
    '图片': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp', 'ico', 'tiff'],
    '代码': ['py', 'js', 'ts', 'vue', 'html', 'css', 'json', 'xml', 'java', 'go', 'rs', 'c', 'cpp', 'h', 'sh', 'bat'],
    '数据': ['csv', 'sql', 'db', 'sqlite', 'parquet', 'avro'],
  }
  
  for (const [cat, exts] of Object.entries(categoryMap)) {
    if (exts.includes(ext)) return cat
  }
  return '其他'
}

const filesWithCategory = computed(() => {
  return allFiles.value.map(file => ({
    ...file,
    category: getFileCategory(file.filename)
  }))
})

const categoryCounts = computed(() => {
  const counts = { '全部': allFiles.value.length }
  for (const file of filesWithCategory.value) {
    counts[file.category] = (counts[file.category] || 0) + 1
  }
  return counts
})

const totalFiles = computed(() => allFiles.value.length)

const currentFiles = computed(() => {
  if (activeTab.value === '全部') {
    return filesWithCategory.value
  }
  return filesWithCategory.value.filter(f => f.category === activeTab.value)
})

async function refreshAssets() {
  loading.value = true
  try {
    const data = await getAllFiles()
    allFiles.value = data.files || []
  } catch (e) {
    console.error('获取资产失败:', e)
  } finally {
    loading.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function copyPath(path) {
  try {
    await navigator.clipboard.writeText(path)
  } catch (e) {
    console.error('复制失败:', e)
  }
}

onMounted(() => {
  refreshAssets()
})
</script>

<style scoped>
.assets-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  height: 100%;
}

.assets-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
}

.assets-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
}

.refresh-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 8px;
  font-size: 14px;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover:not(:disabled) {
  background: #f1f5f9;
}

.refresh-btn svg {
  width: 16px;
  height: 16px;
}

.refresh-btn svg.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.tabs {
  display: flex;
  gap: 8px;
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  overflow-x: auto;
}

.tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid #e2e8f0;
  background: white;
  border-radius: 8px;
  font-size: 14px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.tab:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.tab.active {
  background: #0ea5e9;
  border-color: #0ea5e9;
  color: white;
}

.tab-icon {
  font-size: 16px;
}

.tab-name {
  font-weight: 500;
}

.tab-count {
  background: rgba(0, 0, 0, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.tab.active .tab-count {
  background: rgba(255, 255, 255, 0.2);
}

.assets-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #94a3b8;
  gap: 16px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e2e8f0;
  border-top-color: #0ea5e9;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: #94a3b8;
}

.empty-state svg {
  width: 64px;
  height: 64px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 500;
  color: #64748b;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  transition: all 0.2s;
}

.file-card:hover {
  border-color: #cbd5e1;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.file-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.file-icon svg {
  width: 24px;
  height: 24px;
  color: white;
}

.file-icon.doc {
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
}

.file-icon.image {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.file-icon.code {
  background: linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%);
}

.file-icon.data {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.file-icon.other {
  background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%);
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.file-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #94a3b8;
}

.file-session {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-action {
  width: 32px;
  height: 32px;
  border: none;
  background: transparent;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s;
}

.file-card:hover .file-action {
  opacity: 1;
}

.file-action:hover {
  background: #f1f5f9;
}

.file-action svg {
  width: 16px;
  height: 16px;
  color: #64748b;
}
</style>

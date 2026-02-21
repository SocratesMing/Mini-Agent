import requests
import json
import time

# 创建一个新的会话
print('Creating a new session...')
session_url = 'http://localhost:8000/api/sessions'
session_data = {'title': 'Test Session'}
session_response = requests.post(session_url, json=session_data)
print('Session creation status code:', session_response.status_code)
session_info = session_response.json()
session_id = session_info['session_id']
print('Created session ID:', session_id)

# 创建一个测试文件
with open('test.txt', 'w') as f:
    f.write('test content')

# 模拟前端的文件上传操作
print('\nTesting file upload...')
upload_url = f'http://localhost:8000/api/sessions/{session_id}/upload'
files = {'file': open('test.txt', 'rb')}

start_time = time.time()
response = requests.post(upload_url, files=files)
end_time = time.time()

print('Upload status code:', response.status_code)
print('Upload response:', response.text)
print('Upload time:', end_time - start_time, 'seconds')

# 检查文件是否上传成功
print('\nChecking uploaded files...')
files_url = f'http://localhost:8000/api/sessions/{session_id}/files'
files_response = requests.get(files_url)
print('Files status code:', files_response.status_code)
print('Files response:', files_response.text)

# 关闭文件
files['file'].close()

print('\nTest completed!')

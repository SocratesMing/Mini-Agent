import requests
import json

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

# 使用有效的会话ID测试文件上传
url = f'http://localhost:8000/api/sessions/{session_id}/upload'
files = {'file': open('test.txt', 'rb')}

print('\nTesting file upload to:', url)
try:
    response = requests.post(url, files=files)
    print('Status code:', response.status_code)
    print('Response:', response.text)
    if response.status_code == 200:
        print('File uploaded successfully!')
    else:
        print('Error:', response.json())
except Exception as e:
    print('Exception:', str(e))
finally:
    files['file'].close()

# 获取会话的文件列表
files_url = f'http://localhost:8000/api/sessions/{session_id}/files'
print('\nGetting session files from:', files_url)
try:
    response = requests.get(files_url)
    print('Status code:', response.status_code)
    print('Response:', response.text)
except Exception as e:
    print('Exception:', str(e))

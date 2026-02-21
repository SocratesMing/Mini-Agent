import requests

# 创建一个测试文件
with open('test.txt', 'w') as f:
    f.write('test content')

# 测试文件上传
url = 'http://localhost:8000/api/sessions/test/upload'
files = {'file': open('test.txt', 'rb')}

print('Testing file upload to:', url)
try:
    response = requests.post(url, files=files)
    print('Status code:', response.status_code)
    print('Response:', response.text)
    if response.status_code != 200:
        print('Error:', response.json())
except Exception as e:
    print('Exception:', str(e))
finally:
    files['file'].close()

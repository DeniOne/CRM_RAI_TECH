import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient
import re

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Создаю задачу
resp = client.post('/leads/1/tasks', data={'title': 'Тест удаления', 'priority': '2'})
print('Create:', resp.status_code)

# Нахожу ID задачи
match = re.search(r'id="task-(\d+)"', resp.text)
if match:
    task_id = match.group(1)
    print('Task ID:', task_id)
    
    # Удаляю задачу
    resp2 = client.delete(f'/api/tasks/{task_id}')
    print('Delete:', resp2.status_code)
    print('Response empty:', resp2.text == '')
else:
    print('Task ID not found in response')
    print('Response:', resp.text[:300])

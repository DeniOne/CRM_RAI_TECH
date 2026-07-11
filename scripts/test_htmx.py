import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

resp = client.get('/kanban')

# Ищу все select элементы с hx-get
import re
selects = re.findall(r'<select[^>]*>', resp.text)
print('All select elements:')
for s in selects:
    print(s[:200])
    print()

# Проверяю загрузку HTMX
if 'htmx.org' in resp.text:
    print('HTMX script: FOUND')
else:
    print('HTMX script: NOT FOUND')

# Проверяю что kanban-board div существует
if 'id="kanban-board"' in resp.text:
    print('kanban-board div: FOUND')
else:
    print('kanban-board div: NOT FOUND')

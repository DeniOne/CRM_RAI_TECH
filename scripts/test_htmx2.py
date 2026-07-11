import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Имитирую HTMX запрос как в браузере
headers = {
    'HX-Request': 'true',
    'HX-Trigger': 'region',
    'HX-Target': 'kanban-board',
    'HX-Current-URL': 'http://localhost:8000/kanban',
}

resp = client.get('/kanban?region=3', headers=headers)
print('Status:', resp.status_code)
print('Response is fragment:', '<html' not in resp.text.lower() and '<body' not in resp.text.lower())
print('Has columns:', 'kanban-column' in resp.text)

# Проверяю заголовки ответа
print('\nResponse headers:')
for k, v in resp.headers.items():
    if 'hx' in k.lower() or 'content' in k.lower():
        print(f'  {k}: {v}')

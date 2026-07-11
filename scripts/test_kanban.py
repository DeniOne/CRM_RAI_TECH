import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient
import re

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Полный запрос (не HTMX) - страница канбана
resp = client.get('/kanban')
print('Full page status:', resp.status_code)

# Проверяю есть ли hx-get в select элементах
selects = re.findall(r'<select[^>]*name="([^"]+)"[^>]*hx-get="([^"]+)"', resp.text)
print('Selects with hx-get:', selects)

# Проверяю target
targets = re.findall(r'hx-target="([^"]+)"', resp.text)
print('HTMX targets:', set(targets))

# HTMX запрос с фильтром
resp2 = client.get('/kanban?assigned_manager=1', headers={'HX-Request': 'true', 'HX-Trigger': 'assigned_manager'})
print('\nHTMX response status:', resp2.status_code)
print('Response length:', len(resp2.text))
print('Has kanban-column:', 'kanban-column' in resp2.text)
print('First 500 chars:')
print(resp2.text[:500])

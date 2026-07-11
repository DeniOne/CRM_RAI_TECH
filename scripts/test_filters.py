import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient
import re

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Test full page
resp = client.get('/kanban')
print('Page:', resp.status_code)

# Check form has hx-get
if 'hx-get="/kanban"' in resp.text:
    print('Form has hx-get: YES')
else:
    print('Form has hx-get: NO')

# Check selects are inside form
form_match = re.search(r'<form[^>]*id="kanban-filters"[^>]*>(.*?)</form>', resp.text, re.DOTALL)
if form_match:
    form_content = form_match.group(1)
    selects = re.findall(r'<select[^>]*name="([^"]+)"', form_content)
    print('Selects in form:', selects)
else:
    print('Form not found')

# Test HTMX filter request
resp2 = client.get('/kanban?region=3', headers={'HX-Request': 'true'})
print('\nFilter region=3:', resp2.status_code)
cards = len(re.findall(r'data-lead-id', resp2.text))
print('Cards:', cards)

# Test level filter
resp3 = client.get('/kanban?level=A', headers={'HX-Request': 'true'})
print('\nFilter level=A:', resp3.status_code)
cards3 = len(re.findall(r'data-lead-id', resp3.text))
print('Cards:', cards3)

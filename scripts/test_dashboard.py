from app.main import app
from fastapi.testclient import TestClient
import re

client = TestClient(app)

# Login
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Dashboard
resp = client.get('/')
text = resp.text

# Check for data
total_match = re.search(r'text-blue-600">(\d+)', text)
if total_match:
    print('Total leads:', total_match.group(1))

region_count = text.count('<tr class="border-t">')
print('Region rows:', region_count)

# Check stages
for stage_name in ['Сырые', 'В работе', 'Потерян']:
    if stage_name in text:
        print(f'Found stage: {stage_name}')

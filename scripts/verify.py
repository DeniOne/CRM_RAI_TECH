import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from fastapi.testclient import TestClient
import re

client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})
resp = client.get('/')

total_match = re.search(r'text-blue-600">(\d+)', resp.text)
if total_match:
    print('Total leads:', total_match.group(1))

region_count = resp.text.count('<tr class="border-t">')
print('Region rows:', region_count)

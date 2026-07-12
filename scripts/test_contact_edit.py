import sys
sys.path.insert(0, '.')
from app.main import app
from fastapi.testclient import TestClient
client = TestClient(app)
client.post('/login', data={'email': 'admin@crm.local', 'password': 'admin'})

# Test edit form
resp = client.get('/leads/1/contacts/1/edit')
print('Edit form:', resp.status_code)
print('Has phone input:', 'phone' in resp.text)
print('Has save button:', 'Сохранить' in resp.text)

# Test update
resp2 = client.put('/leads/1/contacts/1', data={
    'name': 'Test Name',
    'phone': '1234567890',
    'email': 'test@test.com',
    'position': 'Manager',
})
print('Update:', resp2.status_code)
print('Has updated name:', 'Test Name' in resp2.text)
print('Has updated phone:', '1234567890' in resp2.text)

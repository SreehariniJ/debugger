import urllib.request
import urllib.parse
import json

# Get token
login_data = urllib.parse.urlencode({'username': 'admin', 'password': 'password123'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/auth/login', data=login_data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
try:
    resp = urllib.request.urlopen(req)
    token = json.loads(resp.read())['access_token']
except Exception as e:
    print(f"Login failed: {e}")
    exit(1)

# Debug
debug_data = json.dumps({'code': 'print(1/0)', 'mode': 'fast'}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/debug_snippet', data=debug_data, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
try:
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read())
    print("Success:", data.get('success'))
    print("Fixed Code:")
    print(data.get('fixed_code'))
    print("Explanation:")
    print(data.get('explanation'))
except Exception as e:
    print(f"Debug failed: {e}")

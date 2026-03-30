import urllib.request
import json

API_URL = "http://127.0.0.1:8001"

def get_auth_token():
    url = f"{API_URL}/auth/login"
    payload = {"username": "testuser_validation", "password": "password"}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))['access_token']
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def test_semantic_noop():
    token = get_auth_token()
    original = "def add(a, b):\n    return a + b\n"
    noop_fixed = "def add(a, b):\n    # just added a comment\n    return a + b\n"
    
    url = f"{API_URL}/validate_fix"
    payload = {"original": original, "fixed": noop_fixed}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }, method='POST')
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            print(json.dumps(res, indent=2))
            with open("noop_result.json", "w") as f:
                json.dump({"semantic_noop": res}, f)
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_semantic_noop()

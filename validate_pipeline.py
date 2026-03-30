import urllib.request
import urllib.error
import json
import time

API_URL = "http://127.0.0.1:8001"

def get_auth_token():
    url = f"{API_URL}/auth/register"
    payload = {"username": "testuser_validation", "password": "password", "display_name": "Test User"}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))['access_token']
    except urllib.error.HTTPError as e:
        if e.code == 409: # Already registered
            url = f"{API_URL}/auth/login"
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))['access_token']
        raise

TOKEN = None

def post_json(endpoint, payload):
    global TOKEN
    if not TOKEN:
        TOKEN = get_auth_token()
        
    url = f"{API_URL}{endpoint}"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {TOKEN}'
    }, method='POST')
    
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"HTTPError on {url}: {e.code}")
        body = e.read().decode('utf-8')
        print(body)
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": body}

def print_result(name, result):
    print(f"\n{'='*50}\n[TEST] {name}\n{'='*50}")
    print(json.dumps(result, indent=2))

def test_chained_exceptions():
    code = """def failing_code():
    try:
        1 / 0
    except ZeroDivisionError:
        "a" + 1

failing_code()
"""
    print(f"⏳ Running test_chained_exceptions (Full Mode)...")
    res = post_json("/debug_snippet", {"code": code, "mode": "full"})
    print_result("Chained Exceptions", res)
    return res

def test_semantic_noop():
    original = "def add(a, b):\\n    return a + b\\n"
    noop_fixed = "def add(a, b):\\n    # just added a comment\\n    return a + b\\n"
    
    print(f"⏳ Running test_semantic_noop (/validate_fix)...")
    res = post_json("/validate_fix", {
        "file_path": "/tmp/test.py", 
        "original": original, 
        "fixed": noop_fixed
    })
    print_result("Semantic No-Op Edits", res)
    return res

def test_large_snippet():
    # Adding padding to make it "large"
    padding = "\\n".join([f"    def dummy_{i}(self): return {i}" for i in range(50)])
    code = f"""class ComplexSystem:
    def __init__(self):
        self.state = {{}}
    
{padding}
        
    def process(self):
        for i in range(10):
            self.do_step(i)
            
    def do_step(self, x):
        self.undefined_method(x)

ComplexSystem().process()
"""
    print(f"⏳ Running test_large_snippet (Full Mode)...")
    res = post_json("/debug_snippet", {"code": code, "mode": "full"})
    print_result("Large Snippet Orchestration", res)
    return res

def test_fast_mode():
    code = "print('Hello World'"
    print(f"⏳ Running test_fast_mode (Fast Mode)...")
    res = post_json("/debug_snippet", {"code": code, "mode": "fast"})
    print_result("Fast Mode Debugging", res)
    return res

def main():
    print("🚀 Starting Pipeline Validation...")
    results = {}
    
    started = time.time()
    results['chained_exceptions'] = test_chained_exceptions()
    results['semantic_noop'] = test_semantic_noop()
    results['large_snippet'] = test_large_snippet()
    results['fast_mode'] = test_fast_mode()
    elapsed = time.time() - started
    
    results['total_validation_time'] = elapsed
    
    with open("validation_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"✅ Validation completed in {elapsed:.2f} seconds. Results saved to validation_results.json")

if __name__ == "__main__":
    main()

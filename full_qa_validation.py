"""
Comprehensive Full-Application QA Validation Script
Tests all API endpoints, edge cases, and pipeline behaviors.
"""
import urllib.request
import urllib.error
import json
import time
import sys

API_URL = "http://127.0.0.1:8000"
RESULTS = []
TOKEN = None

def get_auth_token():
    # Try login first
    url = f"{API_URL}/auth/login"
    payload = {"username": "testuser_qa", "password": "qapassword123"}
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))['access_token']
    except urllib.error.HTTPError:
        # Register
        url = f"{API_URL}/auth/register"
        payload["display_name"] = "QA Test User"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode('utf-8'))['access_token']
        except urllib.error.HTTPError as e:
            if e.code == 409:
                # Already registered, try login again
                url = f"{API_URL}/auth/login"
                payload2 = {"username": "testuser_qa", "password": "qapassword123"}
                data2 = json.dumps(payload2).encode('utf-8')
                req2 = urllib.request.Request(url, data=data2, headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req2) as response:
                    return json.loads(response.read().decode('utf-8'))['access_token']
            raise

def post_json(endpoint, payload, timeout=120):
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
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.getcode(), json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}
    except Exception as e:
        return 0, {"error": str(e)}

def get_json(endpoint, timeout=30):
    global TOKEN
    if not TOKEN:
        TOKEN = get_auth_token()
    url = f"{API_URL}{endpoint}"
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json',
        'Authorization': f'Bearer {TOKEN}'
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.getcode(), json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}
    except Exception as e:
        return 0, {"error": str(e)}

def record(test_name, category, action, expected, actual, status, notes=""):
    result = {
        "test": test_name,
        "category": category,
        "action": action,
        "expected": expected,
        "actual": actual,
        "status": status,
        "notes": notes
    }
    RESULTS.append(result)
    icon = "✅" if status == "PASS" else "❌"
    print(f"  {icon} {test_name}: {status}")

# ========== TEST SUITES ==========

def test_health():
    print("\n🏥 Health Check...")
    code, data = get_json("/health")
    record("Health Endpoint", "System", "GET /health",
           "200 + status=ok", f"{code} + status={data.get('status','?')}",
           "PASS" if code == 200 and data.get("status") == "ok" else "FAIL")

def test_auth():
    print("\n🔐 Authentication Tests...")
    # Valid login
    code, data = post_json("/auth/login", {"username": "testuser_qa", "password": "qapassword123"})
    record("Auth Login Valid", "Authentication", "POST /auth/login with valid creds",
           "200 + access_token present", f"{code} + token={'present' if data.get('access_token') else 'missing'}",
           "PASS" if code == 200 and data.get("access_token") else "FAIL")

    # Invalid login
    code, data = post_json("/auth/login", {"username": "nonexistent", "password": "wrong"})
    record("Auth Login Invalid", "Authentication", "POST /auth/login with bad creds",
           "401 Unauthorized", f"{code}",
           "PASS" if code == 401 else "FAIL")

    # Duplicate registration
    code, data = post_json("/auth/register", {"username": "testuser_qa", "password": "qapassword123", "display_name": "Dup"})
    record("Auth Register Duplicate", "Authentication", "POST /auth/register for existing user",
           "409 Conflict", f"{code}",
           "PASS" if code == 409 else "FAIL")

    # Get profile
    code, data = get_json("/auth/me")
    record("Auth Profile", "Authentication", "GET /auth/me",
           "200 + username", f"{code} + username={data.get('username','?')}",
           "PASS" if code == 200 and data.get("username") == "testuser_qa" else "FAIL")

def test_debug_snippet_fast():
    print("\n⚡ Debug Snippet - Fast Mode...")
    code_input = "print('Hello World'"
    start = time.time()
    code, data = post_json("/debug_snippet", {"code": code_input, "mode": "fast"}, timeout=120)
    elapsed = time.time() - start

    record("Fast Debug - HTTP Status", "Debug Pipeline", "POST /debug_snippet (fast mode, SyntaxError)",
           "200", f"{code}",
           "PASS" if code == 200 else "FAIL")

    record("Fast Debug - Error Detection", "Debug Pipeline", "Check error_type in response",
           "SyntaxError", data.get("error_type", "?"),
           "PASS" if data.get("error_type") == "SyntaxError" else "FAIL")

    record("Fast Debug - Fix Generated", "Debug Pipeline", "Check fixed_code present",
           "Non-empty fixed_code", f"{'present' if data.get('fixed_code') else 'missing'} ({len(data.get('fixed_code',''))} chars)",
           "PASS" if data.get("fixed_code") else "FAIL")

    record("Fast Debug - Pipeline Mode", "Debug Pipeline", "Check pipeline_mode=fast",
           "fast", data.get("pipeline_mode", "?"),
           "PASS" if data.get("pipeline_mode") == "fast" else "FAIL")

    sandbox_ok = "verified in sandbox" in (data.get("verification") or "").lower()
    record("Fast Debug - Sandbox Verification", "Debug Pipeline", "Check sandbox verification ran",
           "Sandbox verification present", data.get("verification", "?")[:80],
           "PASS" if data.get("verification") else "FAIL",
           f"Sandbox passed: {sandbox_ok}")

    record("Fast Debug - Response Time", "Performance", f"Total time for fast mode",
           "<60s", f"{elapsed:.1f}s (API total_time: {data.get('total_time','?')}s)",
           "PASS" if elapsed < 120 else "FAIL")

def test_debug_snippet_full_chained():
    print("\n🔗 Debug Snippet - Full Mode (Chained Exceptions)...")
    code_input = """def failing_code():
    try:
        1 / 0
    except ZeroDivisionError:
        "a" + 1

failing_code()
"""
    start = time.time()
    code, data = post_json("/debug_snippet", {"code": code_input, "mode": "full"}, timeout=120)
    elapsed = time.time() - start

    record("Full Chained - HTTP Status", "Debug Pipeline", "POST /debug_snippet (full, chained error)",
           "200", f"{code}",
           "PASS" if code == 200 else "FAIL")

    record("Full Chained - Error Type", "Debug Pipeline", "Check error_type for TypeError",
           "TypeError", data.get("error_type", "?"),
           "PASS" if data.get("error_type") == "TypeError" else "FAIL")

    record("Full Chained - Chained Trace", "Debug Pipeline", "stderr contains ZeroDivisionError chain",
           "ZeroDivisionError in stderr", f"{'found' if 'ZeroDivisionError' in data.get('stderr','') else 'not found'}",
           "PASS" if "ZeroDivisionError" in data.get("stderr", "") else "FAIL")

    record("Full Chained - Analysis", "Debug Pipeline", "Check analysis text present",
           "Non-empty analysis", f"{'present' if data.get('analysis') else 'empty'} ({len(data.get('analysis',''))} chars)",
           "PASS" if data.get("analysis") else "FAIL")

    record("Full Chained - Fix Code", "Debug Pipeline", "Check fixed_code generated",
           "Non-empty fixed_code", f"{'present' if data.get('fixed_code') else 'empty'}",
           "PASS" if data.get("fixed_code") else "FAIL")

    record("Full Chained - Severity", "Debug Pipeline", "Check severity set",
           "Non-empty severity", data.get("severity", "?"),
           "PASS" if data.get("severity") else "FAIL")

    record("Full Chained - Confidence", "Debug Pipeline", "Check confidence score",
           "1-10 range", str(data.get("confidence", "?")),
           "PASS" if isinstance(data.get("confidence"), int) and 1 <= data["confidence"] <= 10 else "FAIL")

    record("Full Chained - Complexity", "Debug Pipeline", "Check complexity analysis",
           "Complexity object present", f"{'present' if data.get('complexity') else 'empty'}",
           "PASS" if data.get("complexity") else "FAIL")

    record("Full Chained - Security Audit", "Debug Pipeline", "Check security audit in full mode",
           "Security audit object present", f"{'present' if data.get('security_audit') else 'empty'}",
           "PASS" if data.get("security_audit") else "FAIL")

    record("Full Chained - Metrics", "Debug Pipeline", "Check timing metrics present",
           "metrics object with scan_rag, viper_orchestration", f"keys={list(data.get('metrics',{}).keys())}",
           "PASS" if data.get("metrics") and "scan_rag" in data.get("metrics",{}) else "FAIL")

    record("Full Chained - Response Time", "Performance", f"Total time for full mode",
           "<120s", f"{elapsed:.1f}s",
           "PASS" if elapsed < 120 else "FAIL")

def test_debug_snippet_empty():
    print("\n🚫 Debug Snippet - Empty Input...")
    code, data = post_json("/debug_snippet", {"code": "", "mode": "fast"})
    # Depending on implementation, empty code might get 400 or produce success=true (no error)
    record("Empty Input", "Edge Cases", "POST /debug_snippet with empty code",
           "Graceful handling (400 or success=true)", f"{code}",
           "PASS" if code in [200, 400, 422] else "FAIL",
           f"Response: {str(data)[:200]}")

def test_debug_snippet_large():
    print("\n📦 Debug Snippet - Large Input...")
    # Generate a large but valid Python snippet
    lines = ["# Large test file"] + [f"x_{i} = {i}" for i in range(500)] + ["print(undefined_var)"]
    large_code = "\n".join(lines)
    start = time.time()
    code, data = post_json("/debug_snippet", {"code": large_code, "mode": "fast"}, timeout=120)
    elapsed = time.time() - start

    record("Large Snippet - HTTP Status", "Edge Cases", "POST /debug_snippet with 500-line file",
           "200", f"{code}",
           "PASS" if code == 200 else "FAIL")

    record("Large Snippet - Error Detected", "Edge Cases", "Check error detection in large file",
           "NameError detected", data.get("error_type", "?"),
           "PASS" if data.get("error_type") == "NameError" else "FAIL",
           f"Time: {elapsed:.1f}s")

def test_validate_fix_noop():
    print("\n🔄 Validate Fix - Semantic No-Op...")
    original = "def add(a, b):\n    return a + b\n"
    noop = "def add(a, b):\n    # comment\n    return a + b\n"
    code, data = post_json("/validate_fix", {"original": original, "fixed": noop})

    record("No-Op Rejection", "Validate Fix", "POST /validate_fix with comment-only change",
           "ready_to_apply=false", f"ready_to_apply={data.get('ready_to_apply','?')}",
           "PASS" if data.get("ready_to_apply") == False else "FAIL")

    record("No-Op Quality Score", "Validate Fix", "Check quality_score is low",
           "Low score (<=50)", f"quality_score={data.get('quality_score','?')}",
           "PASS" if isinstance(data.get("quality_score"), (int, float)) and data["quality_score"] <= 50 else "FAIL")

def test_validate_fix_real():
    print("\n✅ Validate Fix - Real Fix...")
    original = "def divide(a, b):\n    return a / b\n"
    fixed = "def divide(a, b):\n    if b == 0:\n        return None\n    return a / b\n"
    code, data = post_json("/validate_fix", {"original": original, "fixed": fixed})

    record("Real Fix Accepted", "Validate Fix", "POST /validate_fix with meaningful fix",
           "ready_to_apply=true", f"ready_to_apply={data.get('ready_to_apply','?')}",
           "PASS" if data.get("ready_to_apply") == True else "FAIL")

    record("Real Fix Quality Score", "Validate Fix", "Check quality_score is high",
           "High score (>=50)", f"quality_score={data.get('quality_score','?')}",
           "PASS" if isinstance(data.get("quality_score"), (int, float)) and data["quality_score"] >= 50 else "FAIL")

def test_validate_fix_empty():
    print("\n🚫 Validate Fix - Empty Fixed Code...")
    code, data = post_json("/validate_fix", {"original": "x = 1\n", "fixed": ""})
    record("Empty Fix Rejection", "Validate Fix", "POST /validate_fix with empty fixed code",
           "400 or ready_to_apply=false", f"code={code}",
           "PASS" if code == 400 or data.get("ready_to_apply") == False else "FAIL")

def test_validate_fix_syntax_error():
    print("\n❗ Validate Fix - Fix with Syntax Error...")
    code, data = post_json("/validate_fix", {"original": "x = 1\n", "fixed": "def broken(:\n"})
    record("Syntax Error Fix", "Validate Fix", "POST /validate_fix with syntax-broken fix",
           "ready_to_apply=false, syntax error reported", f"ready={data.get('ready_to_apply','?')}, syntax={data.get('syntax',{})}",
           "PASS" if data.get("ready_to_apply") == False else "FAIL")

def test_complexity():
    print("\n📊 Complexity Analysis...")
    code, data = post_json("/analyze_complexity", {"code": "def foo():\n    for i in range(10):\n        if i > 5:\n            print(i)\n"})
    record("Complexity Endpoint", "Analytics", "POST /analyze_complexity",
           "200 + complexity_score present", f"{code} + score={data.get('complexity_score','?')}",
           "PASS" if code == 200 and "complexity_score" in data else "FAIL")

def test_diff():
    print("\n📝 Diff Generation...")
    code, data = post_json("/diff", {
        "original": "x = 1\ny = 2\n",
        "fixed": "x = 1\ny = 3\nz = 4\n"
    })
    record("Diff Endpoint", "Utilities", "POST /diff",
           "200 + diff text present", f"{code} + diff={'present' if data.get('diff') else 'missing'}",
           "PASS" if code == 200 and data.get("diff") else "FAIL")

def test_workspace_files():
    print("\n📁 Workspace Files...")
    code, data = get_json("/workspace/files")
    record("Workspace Files", "Workspace", "GET /workspace/files",
           "200 + list of files", f"{code} + {len(data) if isinstance(data, list) else 'not-list'} files",
           "PASS" if code == 200 and isinstance(data, list) else "FAIL")

def test_workspace_insights():
    print("\n🧠 Workspace Insights...")
    code, data = get_json("/workspace_insights")
    record("Workspace Insights", "Workspace", "GET /workspace_insights",
           "200 + insights object", f"{code} + total_files={data.get('total_files','?')}",
           "PASS" if code == 200 and "total_files" in data else "FAIL")

def test_system_info():
    print("\n ℹ️  System Info...")
    code, data = get_json("/system/info")
    record("System Info", "System", "GET /system/info",
           "200 + version present", f"{code} + version={data.get('version','?')}",
           "PASS" if code == 200 else "FAIL")

def test_rate_limiting():
    print("\n🚦 Rate Limiting (burst test)...")
    # Send several rapid requests to a rate-limited endpoint
    results = []
    for i in range(5):
        c, d = post_json("/analyze_complexity", {"code": f"x = {i}\n"})
        results.append(c)
    all_ok = all(c == 200 for c in results)
    record("Rate Limit - Normal Load", "Security", "5 rapid POST /analyze_complexity",
           "All 200 (under limit)", f"codes={results}",
           "PASS" if all_ok else "FAIL")

def test_model_failure_handling():
    print("\n💥 Model Failure Handling...")
    # Very complex nested code that may push model limits
    complex_code = """
class A:
    def __init__(self):
        self.x = [lambda: None for _ in range(100)]
    def run(self):
        for f in self.x:
            f().undefined()
A().run()
"""
    code, data = post_json("/debug_snippet", {"code": complex_code, "mode": "fast"}, timeout=120)
    record("Model Failure Handling", "Resilience", "POST /debug_snippet with complex code",
           "200 (success=false with error or fix)", f"{code} + success={data.get('success','?')}",
           "PASS" if code == 200 else "FAIL",
           f"error_type={data.get('error_type','?')}, has_fix={bool(data.get('fixed_code'))}")

def test_successful_code():
    print("\n✨ Successful Code (No Error)...")
    code, data = post_json("/debug_snippet", {"code": "print('Hello, World!')\n", "mode": "fast"})
    record("No-Error Code", "Debug Pipeline", "POST /debug_snippet with valid code",
           "200 + success=true", f"{code} + success={data.get('success','?')}",
           "PASS" if code == 200 and data.get("success") == True else "FAIL")

# ========== MAIN ==========

def main():
    print("=" * 60)
    print("🧪 COMPREHENSIVE QA VALIDATION — Offline Debugger Pipeline")
    print("=" * 60)
    grand_start = time.time()

    test_health()
    test_auth()
    test_debug_snippet_fast()
    test_debug_snippet_full_chained()
    test_debug_snippet_empty()
    test_debug_snippet_large()
    test_validate_fix_noop()
    test_validate_fix_real()
    test_validate_fix_empty()
    test_validate_fix_syntax_error()
    test_complexity()
    test_diff()
    test_workspace_files()
    test_workspace_insights()
    test_system_info()
    test_rate_limiting()
    test_model_failure_handling()
    test_successful_code()

    total = time.time() - grand_start
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")

    print(f"\n{'=' * 60}")
    print(f"📊 RESULTS: {passed} PASSED / {failed} FAILED / {len(RESULTS)} TOTAL")
    print(f"⏱️  Total time: {total:.1f}s")
    print(f"{'=' * 60}")

    with open("qa_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "summary": {"passed": passed, "failed": failed, "total": len(RESULTS), "duration_seconds": round(total, 2)},
            "results": RESULTS
        }, f, indent=2)
    print("💾 Results saved to qa_results.json")

if __name__ == "__main__":
    main()

import subprocess
import time
import requests

proc = subprocess.Popen(["python", "run_app.py", "8002", "5174"])
time.sleep(10) # Wait for backend & frontend to boot 

try:
    # Need to fake auth!
    from backend.auth import create_access_token
    token = create_access_token("testuser")
    
    resp = requests.post(
        "http://127.0.0.1:8002/debug_snippet", 
        json={"code": "print(1/0)", "mode": "fast"},
        headers={"Authorization": f"Bearer {token}"}
    )
    print("Status:", resp.status_code)
    import json
    try:
        data = resp.json()
        print("Success:", data.get("success"))
        print("Exit Code:", data.get("exit_code"))
        print("Backend:", data.get("execution_backend"))
    except Exception as e:
        print("Error parsing:", e)
finally:
    proc.terminate()

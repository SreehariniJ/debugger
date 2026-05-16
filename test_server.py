import subprocess
import time
import requests

# Start the server on port 8001
proc = subprocess.Popen(["python", "-m", "uvicorn", "main:app", "--port", "8001"])
time.sleep(3) # Wait for it to boot

try:
    resp = requests.post("http://127.0.0.1:8001/debug_snippet", json={"code": "print(1/0)", "mode": "fast"})
    print("Status:", resp.status_code)
    import json
    try:
        data = resp.json()
        print("Success:", data.get("success"))
        print("Exit Code:", data.get("exit_code"))
        print("Backend:", data.get("execution_backend"))
        print("Result:", json.dumps(data, indent=2))
    except Exception as e:
        print("Error parsing:", e)
finally:
    proc.terminate()

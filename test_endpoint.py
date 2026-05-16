import requests

resp = requests.post("http://127.0.0.1:8000/debug_snippet", json={"code": "print(1/0)", "mode": "fast"})
print(resp.status_code)
print(resp.json())

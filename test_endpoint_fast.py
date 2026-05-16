import asyncio
import httpx
from main import app

async def test():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/debug_snippet", json={"code": "print(1/0)", "mode": "fast", "file_path": ""})
        print("Status code:", resp.status_code)
        import json
        try:
            print(json.dumps(resp.json(), indent=2))
        except:
            print("Response:", resp.text)

asyncio.run(test())

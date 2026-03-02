import webview
import threading
import time
import os
import requests
import uvicorn
from app import app
import sys

# Ensure UTF-8 for console output
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def run_backend():
    print("Starting Integrated Backend (API + UI)...")
    try:
        # Bind to 127.0.0.1 for local privacy and speed
        uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")
    except Exception as e:
        print(f"❌ Backend Crash: {e}")

def wait_for_backend(url, timeout=30):
    print(f"Waiting for backend to warm up at {url}...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                print("✅ Backend is online and ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return False

def main():
    backend_url = "http://127.0.0.1:8000"
    
    # 1. Start the backend in a daemon thread
    t = threading.Thread(target=run_backend, daemon=True)
    t.name = "FastAPI-Backend"
    t.start()
    
    # 2. Synchronize
    if not wait_for_backend(backend_url):
        print("❌ Error: Integrated engine failed to initialize in time (30s timeout).")
        print("Tip: Check if another process is using port 8000.")
        sys.exit(1)
        
    # 3. Launch UI
    print("🚀 Launching Debugger Elite window...")
    try:
        # Create WebView window
        # We'll try to use the most stable engine for Windows (WebView2)
        window = webview.create_window(
            'Debugger Elite', 
            backend_url,
            width=1300,
            height=900,
            min_size=(900, 700),
            background_color='#09090b',
        )
        # webview.start is a blocking call.
        webview.start(debug=False)
    except Exception as e:
        print(f"❌ Window Launch Error: {e}")
        print("\nFallback: You can still access the app at http://localhost:8000 in your browser.")
    finally:
        print("\n👋 Application closed.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Shutdown requested.")

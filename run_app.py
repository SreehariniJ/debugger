import subprocess
import time
import sys
import os
import signal

# Ensure UTF-8 for emojis/special chars if possible
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def start_services():
    print("Starting Offline Debugger Web App...")
    
    # 1. Start Backend
    print("Launching FastAPI Backend (Port 8000)...")
    backend_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"],
        # stdout=subprocess.PIPE,
        # stderr=subprocess.STDOUT,
        # text=True
    )
    
    # 2. Give backend a moment to start
    time.sleep(3)
    
    # 3. Launch Frontend
    print("Launching Vite Frontend (Port 5173)...")
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="frontend",
        shell=True if os.name == 'nt' else False
    )
    
    print("\n" + "="*50)
    print("Offline Debugger is running!")
    print("Frontend: http://localhost:5173")
    print("Backend API: http://localhost:8000")
    print("Press Ctrl+C to stop both services.")
    print("="*50 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping services...")
        backend_process.terminate()
        frontend_process.terminate()
        print("Goodbye!")

if __name__ == "__main__":
    start_services()

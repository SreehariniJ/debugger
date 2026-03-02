# 🛡️ Offline Debugger Pro
> **Zero-Trust, High-Context AI Debugging for Enterprise Environments.**

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![100% Local](https://img.shields.io/badge/Privacy-100%25_Local-success.svg)
![Powered by Qwen](https://img.shields.io/badge/AI-Qwen_1.5B-orange.svg)

**Offline Debugger Pro** is a privacy-first AI debugging suite designed for developers who cannot send their code to the cloud. It acts as an autonomous agent on your machine: executing your code, catching tracebacks, analyzing context, and writing the fix—all in milliseconds, securely on your hardware.

## ⚔️ Why Offline Debugger Pro? (The Pitch)

In enterprise or highly regulated environments, tools like GitHub Copilot or ChatGPT are often banned due to IP leakage concerns.
**We solve this.**

| Feature | Offline Debugger Pro | Cloud AI (Copilot/ChatGPT) |
| :--- | :--- | :--- |
| **Data Privacy** | 🟢 **100% Local (Zero-Trust)** | 🔴 Sends IP to 3rd Party Servers |
| **Execution** | 🟢 **Dynamic (Runs Code)** | 🔴 Static Analysis Only |
| **Latency** | 🟢 **Millisecond Response** | 🟡 Dependant on API Limits/Ping |
| **Cost** | 🟢 **Free / Open Source** | 🔴 Monthly Subscription |

## 🌟 Pro Features
* **Zero-Latency Metrics**: UI displays exact execution times for parsing, RAG, and AI generation.
* **Multi-Agent Pipeline**: Specialized agents (Analyzer, Explainer, Verifier, Fixer) work in parallel.
* **Enterprise Dark UI**: A distraction-free, high-contrast interface designed for long coding sessions.
* **Autonomous File Repair**: Applies fixed code directly to your files with a single click.
Because AI model files are very large, they are not stored directly in this repository. You must download the "brain" of the debugger before use:

1. **Automatic Download**: Simply run the provided script:
   ```bash
   python3 download_model.py
## 🛠️ Project Structure
* `src/`: Core engine including agents and RAG logic.
* `knowledge_base/`: Local JSON error-solution database.
* `test_logic.py`: Sample file for demonstration.

## 🚀 Usage

### 1. Initial Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Download the AI Model
python3 download_model.py

# Install Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Launching the App
```bash
# Start both Backend and Frontend with one command
python3 run_app.py
```

## ✅ Submission Checklist
* [ ] **Local Model**: Ensure `models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` is downloaded.
* [ ] **Backend Health**: Verify API is reachable at `http://localhost:8000/health`.
* [ ] **Knowledge Base**: Check that `knowledge_base/` contains the JSON repair rules.
* [ ] **Offline Check**: Disable internet and verify the debugger still operates (it will!).

---
*Developed with focus on Privacy, Performance, and Developer Experience.*

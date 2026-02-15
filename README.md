# 🚀 Dynamic Multi-Agent Offline Debugger

A privacy-first, fully offline AI debugging suite. This tool **executes** Python code to capture real-time runtime errors and utilizes a **Multi-Agent RAG pipeline** to provide intelligent explanations and automated code repairs.

## 🌟 Key Features
* **Dynamic Execution**: Captures live Python Tracebacks by running code in a controlled environment.
* **Multi-Agent Pipeline**: Specialized agents (Analyzer, Explainer, Verifier, Fixer) work together.
* **Offline RAG**: Queries a local JSON Knowledge Base for context-aware fixes.
* **Autonomous Repair**: Generates a corrected `.py` file automatically.
## 📦 Prerequisites: The AI Model
Because AI model files are very large, they are not stored directly in this repository. You must download the "brain" of the debugger before use:

1. **Automatic Download**: Simply run the provided script:
   ```bash
   python3 download_model.py
## 🛠️ Project Structure
* `src/`: Core engine including agents and RAG logic.
* `knowledge_base/`: Local JSON error-solution database.
* `test_logic.py`: Sample file for demonstration.

## 🚀 Usage
```bash
python3 src/main.py test_logic.py

# 🚀 Dynamic Multi-Agent Offline Debugger

A privacy-first, fully offline AI debugging suite designed for local development. This tool **executes** Python code to capture real-time runtime errors and utilizes a **Multi-Agent RAG pipeline** to provide intelligent explanations and automated code repairs.

## 🌟 Key Features
* **Dynamic Execution**: Executes the target script in a controlled environment to capture live Python Tracebacks (Runtime errors).
* **Multi-Agent Pipeline**: Specialized agents work in sequence to analyze, explain, verify, and fix bugs.
* **Offline RAG (Retrieval-Augmented Generation)**: Queries a local JSON Knowledge Base to provide context-aware fixes without an internet connection.
* **Autonomous Repair**: Generates a corrected `.py` file automatically based on the AI's verification logic.

## 🧠 Technical Workflow
1.  **Scanner**: Executes the script and detects live failures.
2.  **RAG Engine**: Performs a local lookup in `kb.json` for documented solutions.
3.  **Analysis Agent**: Identifies the root cause of the crash.
4.  **Verification Agent**: Checks the proposed fix for logic and safety.
5.  **Fixer Agent**: Rewrites the source code with the implemented correction.

## 🛠️ Project Structure
* `src/`: Core engine including agents and RAG logic.
* `knowledge_base/`: Local JSON error-solution database.
* `models/`: Directory for GGUF LLM weights (e.g., Qwen 2.5).
* `test_logic.py`: Sample file for demonstration and testing.

## 🚀 Setup & Usage

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt

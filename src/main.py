import os
import sys
import subprocess

# Adding the 'src' directory to the system path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from scanner import CodeScanner
from rag_engine import LocalRAGEngine
from agents import DebuggingAgents

def run_target_code(file_path):
    """
    DYNAMIC FEATURE: Runs the target file and captures the actual Traceback.
    This makes the debugger 'live'.
    """
    try:
        result = subprocess.run(['python3', file_path], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return None  # No error
        # Get the last line of the error message
        error_line = result.stderr.strip().splitlines()[-1]
        return error_line
    except Exception as e:
        return str(e)

def run_tech_voyagers(target_file):
    print("\n" + "="*50)
    print("🚀 TECHVOYAGERS: DYNAMIC OFFLINE DEBUGGER")
    print("="*50)

    # --- STEP 0: DYNAMIC ERROR DETECTION ---
    print(f"📡 [STEP 0] Executing {target_file} to catch live errors...")
    error_msg = run_target_code(target_file)
    
    if not error_msg:
        print("✅ No errors detected! Your code is already working.")
        return

    print(f"⚠️  Caught Error: {error_msg}")

    # --- STEP 1: SCANNER ---
    print(f"🔍 [STEP 1] Scanning project for: {target_file}")
    scanner = CodeScanner(".")
    code_context = scanner.get_context_for_file(target_file)
    if not code_context or "Error reading file" in code_context:
        print("❌ Error: Could not read the target file.")
        return

    # --- STEP 2: RAG ENGINE ---
    print(f"📚 [STEP 2] Querying local knowledge base...")
    rag = LocalRAGEngine(data_dir="knowledge_base")
    local_knowledge = rag.query_docs(error_msg)

    # --- STEP 3: MULTI-AGENT AI ---
    print("🧠 [STEP 3] Initializing Offline AI Agents...")
    agents = DebuggingAgents()
    
    if agents.llm is None:
        print("❌ AI Error: Model file missing.")
        return

    print("🤖 Analyzer is identifying the bug...")
    analysis_results = agents.analyzer_agent(error_msg, code_context)

    print("📖 Explainer is drafting educational guide...")
    explanation_results = agents.explainer_agent(analysis_results, local_knowledge)

    print("🛡️  Verifier is checking the solution...")
    verification_results = agents.verifier_agent(explanation_results)

    # --- FINAL REPORT OUTPUT ---
    print("\n" + "-"*50)
    print("🎯 FINAL DEBUGGING REPORT")
    print("-" * 50)
    print(f"🕵️  ANALYSIS:\n{analysis_results.strip()}")
    print(f"\n💡 EXPLANATION:\n{explanation_results.strip()}")
    print(f"\n✅ VERIFICATION:\n{verification_results.strip()}")
    print("="*50 + "\n")

    # --- DYNAMIC AUTO-FIX FEATURE ---
    choice = input("🚀 Would you like to generate the auto-fixed code file? (yes/no): ").strip().lower()

    if choice == 'yes':
        print("🛠️  AI is rewriting your code dynamically...")
        try:
            # Using the code_fixer_agent we added to agents.py
            fixed_code_raw = agents.code_fixer_agent(code_context, error_msg)
            
            # Clean any Markdown artifacts from the AI response
            clean_code = fixed_code_raw.replace("```python", "").replace("```", "").strip()
            
            fixed_filename = f"fixed_{target_file}"
            with open(fixed_filename, "w") as f:
                f.write(clean_code)
        
            print(f"✅ Success! '{fixed_filename}' has been generated.")
            print(f"📁 Run it with: python3 {fixed_filename}")
        except Exception as e:
            print(f"❌ Failed to generate fix: {e}")
    else:
        print("👋 Fix skipped. Good luck with your debugging!")

if __name__ == "__main__":
    # Now you can handle any file! 
    # If you run: python3 main.py test.py, it will debug test.py
    if len(sys.argv) > 1:
        run_tech_voyagers(sys.argv[1])
    else:
        # Default back to demo_bug.py if no file is provided
        run_tech_voyagers("demo_bug.py")

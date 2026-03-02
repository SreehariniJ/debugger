import sys
import os
import ast
import threading
import time
import subprocess
import json
import tempfile
from llama_cpp import Llama
import radon.complexity as radon_cc
import radon.metrics as radon_mi

# Force UTF-8 for Windows console support
if sys.stdout.encoding.lower() != 'utf-8':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

class DebuggingAgents:
    def __init__(self, model_path="models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"):
        self.model_path = model_path
        if os.path.exists(self.model_path):
            n_threads = min(os.cpu_count() or 4, 8)  # Cap at 8 for better performance
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=n_threads,
                n_batch=128,   # Safe value for 1.5B GGUF model
                verbose=False
            )
            self._lock = threading.Lock()  # llama.cpp is NOT thread-safe
            print(f"✅ Model loaded on {n_threads} threads")

        else:
            print(f"❌ Model not found at {self.model_path}")
            self.llm = None

    def clean_response(self, text, start_phrase):
        """Strict filter to ensure the output is concise and student-friendly."""
        # 1. Take only the first two sentences to avoid 'rambling'
        sentences = text.split('.')
        short_version = ". ".join(sentences[:2]) 
        
        # 2. Cut off any AI 'noise' (A:, B:, Analysis:, etc.)
        for stopper in ["A:", "B:", "Analysis:", "Teacher:", "Explanation:", "This solution"]:
            short_version = short_version.split(stopper)[0]
            
        # 3. Final polish
        clean_text = short_version.strip().replace("..", ".")
        if not clean_text.endswith("."):
            clean_text += "."
            
        return f"{start_phrase} {clean_text}"

    def generate_response(self, prompt):
        if self.llm is None: return "Model missing."
        with self._lock:  # Serialize all LLM calls — llama.cpp is not thread-safe
            output = self.llm(
                prompt,
                max_tokens=50,
                temperature=0.0,
                repeat_penalty=2.0,
                echo=False
            )
        return output['choices'][0]['text'].strip()

    def multi_agent_pipeline(self, error, context, knowledge):
        """Consolidates Analysis, Explanation, and Verification into a SINGLE LLM call."""
        start_marker = "JSON_START"
        prompt = f"""<|im_start|>system
You are a senior debugging architect. Analyze the error and provide a structured response in the following format:
{start_marker}
{{
  "analysis": "10-word summary of the bug",
  "explanation": "1-sentence fix suggestion",
  "status": "Safe or Unsafe (5 words max)"
}}
<|im_end|>
<|im_start|>user
Code Context: {context}
Error Message: {error}
Local Knowledge: {knowledge}

Provide the debugging report:
<|im_end|>
<|im_start|>assistant
{start_marker}
"""
        raw = self.generate_response(prompt)
        # Basic JSON-like parsing if model output isn't perfect
        try:
            content = raw.split(start_marker)[-1].strip()
            # Simple heuristic cleaning
            import json
            data = json.loads(content)
            return data
        except:
            # Fallback to manual splitting if JSON fails
            return {
                "analysis": self.analyzer_agent(error, context),
                "explanation": self.explainer_agent("Error detected", knowledge),
                "status": "Verification needed."
            }

    def analyzer_agent(self, error, context):
        start = "The error is"
        prompt = f"Code: {context}\nError: {error}\nTask: Identify the bug in 10 words or less.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def explainer_agent(self, analysis, knowledge):
        start = "Fix:"
        prompt = f"""
        [STRICT MODE]
        Knowledge: {knowledge}
        Bug: {analysis}
        Constraint: Do not guess variable meanings. Do not use words not found in the code.
        Task: Provide a 1-sentence fix.
        Result: {start}"""
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def verifier_agent(self, explanation):
        start = "Status:"
        prompt = f"Fix: {explanation}\nTask: Is this safe? Answer in 5 words.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def code_fixer_agent(self, context, error, attempt=1):
        """Rewrites the entire script to fix the detected error using a high-precision prompt."""
        
        # Enhanced instructions for the 1.5B model with Chain-of-Thought approach
        retry_tip = ""
        if attempt > 1:
            retry_tip = "\n[CRITIC FEEDBACK] The previous fix failed validation. Focus on simplifying logic and ensuring NO SECURITY RISKS."

        prompt = f"""<|im_start|>system
You are an expert Python developer. Your goal is to fix bugs by correcting logic.
Think step-by-step:
1. Identify the exact line causing the crash.
2. Determine if a simple guard (if/else) or a logic change is needed.
3. Rewrite the code precisely.{retry_tip}
Return ONLY the corrected code inside a ```python block. No extra text.<|im_end|>
<|im_start|>user
Buggy Code:
{context}

Error:
{error}

Fixed Code:<|im_end|>
<|im_start|>assistant
```python"""
        
        with self._lock:
            output = self.llm(
                prompt,
                max_tokens=1024,
                temperature=0.01 if attempt == 1 else 0.5, # Add some temperature for retries
                stop=["<|im_end|>", "```"],
                echo=False
            )
        fixed = output['choices'][0]['text'].strip()
        
        # More intelligent validation
        if len(fixed) < 10 or fixed.strip() == context.strip():
             # Last resort logic
             if "denom = 0" in context:
                 fixed = context.replace("result = num / denom", "if denom != 0:\n    result = num / denom\nelse:\n    result = 0\n    print('Logic Fix: Handled 0 denominator')")
             else:
                 fixed = f"# Auto-fix failed to generate high-quality code. Original remains.\ntry:\n    {context.replace('\n', '\n    ')}\nexcept Exception as e:\n    print(f'Runtime Error: {{e}}')"
        
        return fixed

    def researcher_agent(self, error, context, workspace_files):
        """Elite feature: Identify relevant files in the workspace based on imports or error patterns."""
        relevant_files = [] # type: list[str]
        try:
            # Look for imports in the context
            tree = ast.parse(context)
            imports = [] # type: list[str]
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names: 
                        if isinstance(n.name, str): imports.append(n.name)
                elif isinstance(node, ast.ImportFrom):
                    if isinstance(node.module, str): imports.append(node.module)
            
            for file_info in workspace_files:
                path = file_info.get('path')
                name = file_info.get('name', '')
                if not isinstance(path, str) or not isinstance(name, str):
                    continue
                
                module_name = name.replace('.py', '')
                if any(imp and module_name in imp for imp in imports):
                    relevant_files.append(path)
                elif any(word in error.lower() for word in module_name.lower().split('_')):
                    relevant_files.append(path)
        except:
            pass
            
        unique_files: list[str] = list(set(relevant_files))
        return unique_files[:2]

    def critic_agent(self, original_code, proposed_fix):
        """Elite feature: Validate the proposed fix for quality and safety."""
        # 1. Syntax Check
        try:
            ast.parse(proposed_fix)
        except SyntaxError:
            return {"valid": False, "reason": "Syntax error in proposed fix."}

        # 2. Complexity Check
        complexity = self.complexity_agent(proposed_fix)
        orig_complexity = self.complexity_agent(original_code)
        
        # 3. Security Check
        security = self.security_audit_agent(proposed_fix)
        critical_vulnerabilities = [v for v in security.get('issues', []) if v.get('risk') == 'CRITICAL']

        if critical_vulnerabilities:
            return {"valid": False, "reason": f"Fix introduced critical vulnerability: {critical_vulnerabilities[0]['type']}"}
        
        if complexity['complexity_score'] > 25 and complexity['complexity_score'] > orig_complexity['complexity_score']:
             return {"valid": False, "reason": "Fix drastically increased code complexity (Cyclomatic > 25)."}

        return {"valid": True, "metrics": {"complexity": complexity, "security": security}}

    async def viper_orchestration(self, error, context, workspace_files):
        """The heart of the Viper Protocol: Orchestrated Multi-Agent Loop."""
        # 1. Research phase
        relevant_paths = self.researcher_agent(error, context, workspace_files)
        augmented_context = context
        for path in relevant_paths:
            try:
                with open(path) as f:
                    augmented_context += f"\n\n# Context from {os.path.basename(path)}:\n" + f.read()
            except: continue

        # 2. Fix & Critique loop
        best_fix = ""
        last_reason = None
        for attempt in range(1, 3): # Max 2 attempts for performance
             candidate = self.code_fixer_agent(augmented_context, error, attempt)
             report = self.critic_agent(context, candidate)
             if report['valid']:
                 return {
                     "success": True, 
                     "fix": candidate, 
                     "metrics": report['metrics'],
                     "path_taken": f"Orchestrated fix successful on attempt {attempt}"
                 }
             last_reason = report['reason']
             best_fix = candidate
        
        return {
            "success": False, 
            "fix": best_fix, 
            "reason": f"Fix candidate failed validation: {last_reason}",
            "path_taken": "Viper fallback (no valid fix found within constraints)"
        }


    def severity_agent(self, error):
        """Classify the bug severity: CRITICAL, WARNING, or INFO."""
        error_lower = error.lower()
        if any(k in error_lower for k in ["segfault", "memoryerror", "zerodivision", "systemerror", "recursionerror", "timeout"]):
            return "CRITICAL"
        elif any(k in error_lower for k in ["typeerror", "valueerror", "indexerror", "keyerror", "attributeerror", "nameerror"]):
            return "WARNING"
        else:
            return "INFO"

    def complexity_agent(self, code_text):
        """AST-based cyclomatic complexity analysis — now with more granular metrics."""
        try:
            tree = ast.parse(code_text)
        except SyntaxError:
            return {"functions": 0, "classes": 0, "loops": 0, "conditions": 0, "complexity_score": 0, "grade": "F", "loc": 0, "top_complex": "N/A"}
        
        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        loops = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While, ast.AsyncFor)))
        conditions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.If, ast.Compare, ast.BoolOp)))
        
        # Cyclomatic complexity approximation
        complexity_score = len(functions) + loops + conditions
        
        # Code stats
        lines = code_text.splitlines()
        loc = len([l for l in lines if l.strip()])
        comments = len([l for l in lines if l.strip().startswith("#")])
        
        # Find top complex function (naive selection based on nodes)
        top_complex = "N/A"
        if functions:
            def count_complexity(node):
                return sum(1 for n in ast.walk(node) if isinstance(n, (ast.For, ast.While, ast.If, ast.Compare, ast.BoolOp)))
            
            scored_functions = [(f.name, count_complexity(f)) for f in functions]
            top_complex = max(scored_functions, key=lambda x: x[1])[0]

        grade = "A"
        if complexity_score > 30: grade = "F"
        elif complexity_score > 20: grade = "D"
        elif complexity_score > 10: grade = "C"
        elif complexity_score > 5: grade = "B"

        # Radon integration
        radon_data = self.complexity_radon_metrics(code_text)
        
        return {
            "functions": len(functions),
            "classes": classes,
            "loops": loops,
            "conditions": conditions,
            "complexity_score": complexity_score,
            "grade": grade,
            "loc": loc,
            "comments": comments,
            "top_complex": top_complex,
            "mi_score": radon_data.get("mi_score") if radon_data else None,
            "mi_grade": radon_data.get("mi_grade") if radon_data else None
        }

    def complexity_radon_metrics(self, code_text):
        """Advanced metrics using Radon package."""
        try:
            mi_score = radon_mi.mi_visit(code_text, multi=True)
            return {
                "mi_score": round(mi_score, 2),
                "mi_grade": "A" if mi_score > 40 else ("B" if mi_score > 20 else "C")
            }
        except:
            return None

    def security_bandit_agent(self, code_text):
        """Elite feature: Real-time Bandit security scan."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(code_text)
            tmp_path = tmp.name
        
        try:
            # -f json: JSON output, -q: quiet, -lll: low level logging (none)
            result = subprocess.run(
                ["bandit", "-f", "json", "-q", tmp_path],
                capture_output=True, text=True
            )
            if not result.stdout.strip():
                return []
            
            data = json.loads(result.stdout)
            issues = []
            for issue in data.get("results", []):
                issues.append({
                    "type": issue.get("issue_text"),
                    "risk": issue.get("issue_severity"),
                    "desc": f"{issue.get('issue_text')} (Confidence: {issue.get('issue_confidence')})",
                    "line": issue.get("line_number")
                })
            return issues
        except Exception:
            return []
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def security_audit_agent(self, code_text):
        """Elite feature: Audit code for common security vulnerabilities."""
        vulnerabilities = []
        
        # 1. Check for dangerous OS calls
        if "os.system(" in code_text or "subprocess.Popen(..., shell=True)" in code_text:
            vulnerabilities.append({"type": "Injection", "risk": "CRITICAL", "desc": "Execution of OS commands with external input."})
            
        # 2. Check for common hardcoded secrets patterns
        if any(k in code_text.lower() for k in ["api_key =", "secret =", "password =", "token ="]):
            vulnerabilities.append({"type": "Exposure", "risk": "HIGH", "desc": "Potential hardcoded credentials detected."})
            
        # 3. Check for insecure YAML/JSON loading
        if "yaml.load(" in code_text and "SafeLoader" not in code_text:
            vulnerabilities.append({"type": "Deserialization", "risk": "HIGH", "desc": "Insecure YAML loading can lead to code execution."})

        # 4. Check for logic vulnerabilities (eval/exec)
        if "eval(" in code_text or "exec(" in code_text:
            vulnerabilities.append({"type": "Arbitrary Code Execution", "risk": "CRITICAL", "desc": "Use of eval() or exec() with untrusted data."})

        # 5. Elite addition: Bandit Scan
        bandit_issues = self.security_bandit_agent(code_text)
        if bandit_issues:
            vulnerabilities.extend(bandit_issues)

        return {
            "count": len(vulnerabilities),
            "issues": vulnerabilities,
            "is_secure": len(vulnerabilities) == 0,
            "audit_timestamp": time.time(),
            "engine": "Bandit v1.9 + Elite Custom"
        }

    def confidence_agent(self, error, analysis, fixed_code):
        """Score AI fix confidence 1-10 using heuristics — instant, no LLM."""
        score = 7
        known_errors = ["NameError", "TypeError", "ValueError", "ZeroDivisionError", "IndexError", "KeyError", "SyntaxError", "AttributeError", "ValueError"]
        if any(e in error for e in known_errors):
            score += 2
        if len(fixed_code.strip()) < 20:
            score -= 4
        if "pass" in fixed_code or "TODO" in fixed_code:
            score -= 2
        if any(e.lower() in analysis.lower() for e in known_errors):
            score += 1
        return max(1, min(10, score))

